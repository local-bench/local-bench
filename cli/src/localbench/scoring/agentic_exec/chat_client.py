from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.request
from dataclasses import dataclass, replace
from typing import Final
from urllib.parse import urlsplit

from localbench._response import parse_server_timings
from localbench._types import ChatMessage
from localbench.scoring.agentic_exec.model_client import (
    GenerationParams,
    ModelTransportError,
    ModelTransportTimeout,
    ModelResponse,
)

# finish_reason the client stamps on a malformed response turn. Distinct from the
# server's own "length"/"stop" so the diagnostic can tell a CLIENT-side failure apart from a
# model token-cap hit. The loop treats any turn it cannot parse a block from as a format
# failure regardless of this string; the string is for human-readable diagnostics.
ERROR_FINISH_REASON = "error"
_MIN_REQUEST_TIMEOUT_S: Final = 600.0
_MIN_GENERATION_TOKENS_PER_SECOND: Final = 2.0
_TASK_WATCHDOG_S: Final = 1800.0
_FINALIZE_TEARDOWN_RESERVE_S: Final = 180.0
_DEFAULT_TASK_TRANSPORT_BUDGET_S: Final = _TASK_WATCHDOG_S - _FINALIZE_TEARDOWN_RESERVE_S


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
    timeout_s: float = _MIN_REQUEST_TIMEOUT_S
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
        timeout_s: float = _MIN_REQUEST_TIMEOUT_S,
        *,
        chat_path: str = "/v1/chat/completions",
        chat_template_kwargs: dict[str, object] | None = None,
    ) -> None:
        base = base_url.rstrip("/")
        resolved_chat_path = chat_path
        if base.endswith("/v1") and chat_path == "/v1/chat/completions":
            # Callers across localbench pass the OpenAI-style base INCLUDING /v1 (the serve
            # orchestrator does exactly that), while the default chat_path also carries /v1.
            # Collapse the overlap so BOTH conventions yield ROOT/v1/chat/completions — a
            # double /v1 404s on every call and, because complete() never raises, silently
            # burns the whole turn cap as empty turns (found by the 2026-07-03 shakeout).
            resolved_chat_path = "/chat/completions"
        self._config = ChatClientConfig(
            base_url=base,
            model=model,
            api_key=api_key,
            timeout_s=timeout_s,
            chat_path=resolved_chat_path,
            chat_template_kwargs=chat_template_kwargs,
        )
        self._deadline: float | None = None
        self._attempt_timeout_s: float | None = None
        self._cancelled = threading.Event()
        self._connection_lock = threading.Lock()
        self._active_connection: http.client.HTTPConnection | None = None

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

    def set_task_deadline(self, deadline: float) -> None:
        """Pin one monotonic transport deadline shared by every attempt and loop turn."""
        self._deadline = deadline

    def cancel(self) -> None:
        """Cancel the live task request; safe to call from the watchdog thread."""
        self._cancelled.set()
        with self._connection_lock:
            connection = self._active_connection
            if connection is not None and connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()

    # -- transport (overridable for tests) ------------------------------------------------------
    def _post(self, payload: dict[str, object]) -> tuple[int, str]:
        """POST the payload; return ``(status_code, body_text)``.

        Isolated so a unit test can monkeypatch THIS method with a mock transport (no live
        endpoint). Connection-level failures raise a typed transport exception; HTTP failures
        return their status and body for the recoverable-turn diagnostic.
        """
        endpoint = urlsplit(self.endpoint)
        if endpoint.scheme not in {"http", "https"} or endpoint.hostname is None:
            raise ModelTransportError(detail=f"unsupported chat endpoint: {self.endpoint!r}")
        path = endpoint.path or "/"
        if endpoint.query:
            path = f"{path}?{endpoint.query}"
        port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        connection_type = (
            http.client.HTTPSConnection
            if endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        timeout_s = self._attempt_timeout_s or self._request_timeout_s(payload)
        connection = connection_type(endpoint.hostname, port, timeout=timeout_s)
        with self._connection_lock:
            if self._cancelled.is_set():
                raise ModelTransportTimeout(detail="task transport cancelled")
            self._active_connection = connection
        try:
            connection.request(
                "POST",
                path,
                body=json.dumps(payload).encode("utf-8"),
                headers=headers,
            )
            response = connection.getresponse()
            return int(response.status), response.read().decode("utf-8", errors="replace")
        except (TimeoutError, socket.timeout) as exc:
            raise ModelTransportTimeout(detail=f"{type(exc).__name__}: {exc}") from exc
        except (OSError, http.client.HTTPException) as exc:
            if self._cancelled.is_set():
                raise ModelTransportTimeout(detail="task transport cancelled") from exc
            raise ModelTransportError(detail=f"{type(exc).__name__}: {exc}") from exc
        finally:
            with self._connection_lock:
                if self._active_connection is connection:
                    self._active_connection = None
            connection.close()

    def _request_timeout_s(self, payload: dict[str, object]) -> float:
        max_tokens = payload.get("max_tokens")
        output_tokens = max_tokens if isinstance(max_tokens, int) and not isinstance(max_tokens, bool) else 0
        # Fidelity fix: keep the raised 600s floor. Rows whose calls completed before the old
        # 120s timeout reproduce identically; only calls that crossed that old boundary change.
        generation_s = max(0, output_tokens) / _MIN_GENERATION_TOKENS_PER_SECOND
        return max(self._config.timeout_s, _MIN_REQUEST_TIMEOUT_S, generation_s)

    def _remaining_transport_s(self) -> float:
        if self._deadline is None:
            self._deadline = time.monotonic() + _DEFAULT_TASK_TRANSPORT_BUDGET_S
        return max(0.0, self._deadline - time.monotonic())

    # -- ModelClient.complete -------------------------------------------------------------------
    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        """POST one turn; parse the reply into a :class:`ModelResponse`.

        At most one HTTP request is made per protocol turn. A turn reached after the shared
        deadline is exhausted is still counted as a failed transport attempt, although it returns
        before issuing HTTP. Transport and HTTP failures become the same recoverable empty turn
        used by 0.3.0. Response parse problems remain recoverable protocol-format failures.
        """
        payload = self._build_payload(messages, params)
        remaining_s = self._remaining_transport_s()
        if remaining_s <= 0 or self._cancelled.is_set():
            return self._error_response(
                "task transport deadline exhausted",
                transport_failure=True,
                transport_failure_count=1,
                transport_attempt_count=1,
            )
        body = ""
        status = 0
        transport_errors: list[str] = []
        self._attempt_timeout_s = min(self._request_timeout_s(payload), remaining_s)
        try:
            status, body = self._post(payload)
        except ModelTransportError as error:
            transport_errors.append(str(error))
        finally:
            self._attempt_timeout_s = None
        if status != 200 and status != 0:
            transport_errors.append(f"http_status={status}: {_clip(body)}")
        if status != 200:
            return self._error_response(
                "; ".join(transport_errors) or "transport failure",
                transport_failure=True,
                transport_failure_count=len(transport_errors),
                transport_attempt_count=1,
            )
        try:
            data = json.loads(body)
        except (ValueError, TypeError) as exc:
            response = self._error_response(f"non_json_body: {exc}: {_clip(body)}")
        else:
            response = self._parse_response(data)
        return replace(
            response,
            transport_failure=bool(transport_errors),
            transport_failure_count=len(transport_errors),
            transport_attempt_count=1,
        )

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
            server_timings=parse_server_timings(data.get("timings")),
        )

    def _error_response(
        self,
        detail: str,
        *,
        transport_failure: bool = False,
        transport_failure_count: int = 0,
        transport_attempt_count: int = 0,
    ) -> ModelResponse:
        """A turn the loop will treat as a (recoverable) format failure.

        Empty text → block_parser yields a ``no_block`` format error → the loop injects a
        corrective observation and continues. ``error_detail`` carries the cause into the
        per-turn record so endpoint failures stay diagnosable (the 2026-07-03 shakeout burned
        144 silent turns partly because this detail used to be dropped).
        """
        return ModelResponse(
            text="",
            finish_reason=ERROR_FINISH_REASON,
            output_tokens=0,
            error_detail=detail,
            transport_failure=transport_failure,
            transport_failure_count=transport_failure_count,
            transport_attempt_count=transport_attempt_count,
        )


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
