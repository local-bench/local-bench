"""OpenAI-compatible chat-completions client implementing the ``ModelClient`` seam.

This is the ONLY new code the GPU run needs to swap the scripted agent for a real model: a
thin :class:`ChatCompletionsClient` that POSTs the Protocol C chat history to an
OpenAI-compatible ``/v1/chat/completions`` endpoint (e.g. a local ``llama-server`` on
``http://127.0.0.1:8000``) and parses the reply back into a :class:`ModelResponse` the loop
already understands. The loop, sandbox, diagnostics, and finalize seam are all unchanged
between the scripted run and the real run — only the ``model_factory`` swaps to build one of
these.

Design constraints (kept deliberately small):

  * **Stdlib only.** Uses ``urllib.request`` + ``json`` so the module is import-safe on every
    host (Windows 3.14, WSL 3.12, no httpx/openai SDK required). No heavy client, no async, no
    streaming — Protocol C turns are short and the loop is sequential.
  * **Determinism passthrough.** ``complete`` maps :class:`GenerationParams` onto the request
    body (``temperature``/``top_p``/``seed``/``max_tokens``) so a real server honours the LOCKED
    greedy + fixed-seed contract. (``seed`` support is server-dependent; llama-server honours it.)
  * **Graceful degradation (documented contract).** A network/timeout error, a non-200 status,
    or a malformed/missing-field response is NEVER raised out of ``complete``. Instead it is
    surfaced to the loop as a **format failure for that turn**: an empty-text
    ``ModelResponse(text="", finish_reason="error")``. The loop already treats a turn with no
    parseable code block as a (recoverable) format failure and injects a corrective observation,
    so a transient blip costs one turn rather than aborting the whole task. This keeps a single
    bad response from sinking a 96-task scored run, and the elevated ``format_failure_rate``
    diagnostic makes any endpoint flakiness visible after the fact. (Rationale: the LOCKED design
    has no per-call retry inside the loop; the funnel handles run-level reruns instead.)

Nothing here imports AppWorld, the sandbox, or a model SDK.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from localbench._types import ChatMessage
from localbench.scoring.agentic_exec.model_client import (
    GenerationParams,
    ModelResponse,
)

# finish_reason the client stamps on a degraded (network/parse) turn. Distinct from the
# server's own "length"/"stop" so the diagnostic can tell a CLIENT-side failure apart from a
# model token-cap hit. The loop treats any turn it cannot parse a block from as a format
# failure regardless of this string; the string is for human-readable diagnostics.
ERROR_FINISH_REASON = "error"


@dataclass(frozen=True, slots=True)
class ChatClientConfig:
    """Connection settings for :class:`ChatCompletionsClient`.

    ``base_url`` is the server root WITHOUT the ``/v1/chat/completions`` suffix (it is appended),
    e.g. ``http://127.0.0.1:8000``. ``model`` is the served model id the endpoint expects.
    ``api_key`` is optional (local llama-server ignores it; set it for hosted gateways).
    """

    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 120.0
    # Appended to base_url. Standard OpenAI path; overridable for non-standard gateways.
    chat_path: str = "/v1/chat/completions"
    # Extra chat-template kwargs forwarded VERBATIM in the request body (llama-server reads
    # `chat_template_kwargs`). This is how the agentic loop engages a model's NATIVE THINKING
    # per-request (e.g. {"enable_thinking": true} for Qwen3 / gemma) — robust + reproducible +
    # captured in the run manifest, rather than depending on a server launch flag. None -> omit.
    chat_template_kwargs: dict[str, object] | None = None


class ChatCompletionsClient:
    """A :class:`~localbench.scoring.agentic_exec.model_client.ModelClient` over HTTP chat.

    One instance is built per task by the benchmark's ``model_factory`` (mirroring how
    ``ScriptedSolverAgent`` is constructed per task), but it is stateless across calls — every
    ``complete`` is an independent POST, so reusing one instance for many tasks is equally fine.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 120.0,
        *,
        chat_path: str = "/v1/chat/completions",
        chat_template_kwargs: dict[str, object] | None = None,
    ) -> None:
        self._config = ChatClientConfig(
            base_url=base_url.rstrip("/"),
            model=model,
            api_key=api_key,
            timeout_s=timeout_s,
            chat_path=chat_path,
            chat_template_kwargs=chat_template_kwargs,
        )

    @property
    def config(self) -> ChatClientConfig:
        return self._config

    @property
    def endpoint(self) -> str:
        return f"{self._config.base_url}{self._config.chat_path}"

    # -- request building -----------------------------------------------------------------------
    def _build_payload(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> dict[str, object]:
        """The OpenAI-compatible request body for one turn.

        Kept as a pure method so the unit test can assert the exact request shape the loop will
        send a real server without touching the network.
        """
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": params.temperature,
            "top_p": params.top_p,
            "seed": params.seed,
            "max_tokens": params.max_output_tokens,
            # Greedy + non-streaming. We read the whole message at once.
            "stream": False,
        }
        if params.stop:
            payload["stop"] = list(params.stop)
        if self._config.chat_template_kwargs:
            # Forwarded verbatim; llama-server applies it to the jinja chat-template render for THIS
            # request (engages native thinking per-request, independent of server launch flags).
            payload["chat_template_kwargs"] = dict(self._config.chat_template_kwargs)
        return payload

    def _build_request(self, payload: dict[str, object]) -> urllib.request.Request:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return urllib.request.Request(  # noqa: S310 — fixed http(s) endpoint, not user input.
            self.endpoint, data=data, headers=headers, method="POST"
        )

    # -- transport (overridable for tests) ------------------------------------------------------
    def _post(self, payload: dict[str, object]) -> tuple[int, str]:
        """POST the payload; return ``(status_code, body_text)``.

        Isolated so a unit test can monkeypatch THIS method with a mock transport (no live
        endpoint). On a transport-level failure (timeout, DNS, connection refused, HTTP error)
        it returns a non-200 status with the error text rather than raising — ``complete``
        converts that into a format-failure ``ModelResponse``.
        """
        req = self._build_request(payload)
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_s) as resp:  # noqa: S310
                status = int(getattr(resp, "status", 200) or 200)
                body = resp.read().decode("utf-8", errors="replace")
                return status, body
        except urllib.error.HTTPError as exc:  # 4xx/5xx with a body
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — best-effort error body.
                body = str(exc)
            return int(exc.code), body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No HTTP status at all (timeout / refused / DNS). Use 0 as a sentinel "no response".
            return 0, f"{type(exc).__name__}: {exc}"

    # -- ModelClient.complete -------------------------------------------------------------------
    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        """POST one turn; parse the reply into a :class:`ModelResponse`.

        Never raises: any transport/status/parse problem becomes an empty-text format-failure
        response (``finish_reason="error"``) the loop treats as a recoverable bad turn.
        """
        payload = self._build_payload(messages, params)
        status, body = self._post(payload)
        if status != 200:
            return self._error_response(f"http_status={status}: {_clip(body)}")
        try:
            data = json.loads(body)
        except (ValueError, TypeError) as exc:
            return self._error_response(f"non_json_body: {exc}: {_clip(body)}")
        return self._parse_response(data)

    # -- response parsing -----------------------------------------------------------------------
    def _parse_response(self, data: object) -> ModelResponse:
        """Map an OpenAI chat-completions JSON object onto a :class:`ModelResponse`.

        Tolerant of missing optional fields: a missing ``finish_reason`` defaults to ``"stop"``,
        missing ``usage.completion_tokens`` defaults to ``None`` (the loop then estimates). A
        missing ``choices[0].message.content`` is a malformed response → format-failure.
        """
        if not isinstance(data, dict):
            return self._error_response("response_not_object")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._error_response("no_choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            return self._error_response("choice_not_object")

        message = choice.get("message")
        content: object = None
        if isinstance(message, dict):
            content = message.get("content")
        if content is None:
            # Some servers stream-collapse into "text"; tolerate it, else format-failure.
            content = choice.get("text")
        if not isinstance(content, str):
            return self._error_response("missing_message_content")

        finish_reason = choice.get("finish_reason")
        if not isinstance(finish_reason, str) or not finish_reason:
            finish_reason = "stop"

        output_tokens = _extract_completion_tokens(data.get("usage"))

        return ModelResponse(
            text=content,
            finish_reason=finish_reason,
            output_tokens=output_tokens,
        )

    def _error_response(self, detail: str) -> ModelResponse:
        """A turn the loop will treat as a (recoverable) format failure.

        Empty text → block_parser yields a ``no_block`` format error → the loop injects a
        corrective observation and continues. ``finish_reason`` carries the cause for diagnostics.
        """
        return ModelResponse(text="", finish_reason=ERROR_FINISH_REASON, output_tokens=0)


def _extract_completion_tokens(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    ct = usage.get("completion_tokens")
    if isinstance(ct, bool):  # guard: bool is an int subclass
        return None
    if isinstance(ct, int):
        return ct
    if isinstance(ct, float):
        return int(ct)
    return None


def _clip(text: str, limit: int = 300) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"
