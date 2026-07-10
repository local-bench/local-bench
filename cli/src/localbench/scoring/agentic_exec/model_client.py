"""Model-interface contract for the Protocol C agent loop.

The Protocol C loop (``protocol_c_loop.py``) talks to a model ONLY through the tiny
``ModelClient`` protocol defined here. This is the single seam that keeps the loop module
model-free and GPU-free:

  * the **scripted** agent (``scripted_agent.py``) implements ``ModelClient`` with a
    deterministic hand-written policy — used to test the loop end-to-end with NO LLM, and
  * the **real benchmark** (a follow-up) implements ``ModelClient`` with an
    OpenAI-compatible chat-completions client — same interface, swapped object.

The loop never imports an HTTP client, never starts a server, and never loads weights; it
just calls ``client.complete(messages)`` and reads back text. Determinism (temperature 0,
fixed seed, per-turn token cap) is the *client's* responsibility — the loop passes the
sampling intent down via ``GenerationParams`` so a real client can honour it, while the
scripted client simply ignores it.

Nothing here imports AppWorld, the sandbox, or any provider SDK, so it is import-safe on
every host (Windows/Linux/WSL).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from localbench._types import ChatMessage, JsonObject


@dataclass(slots=True)
class ModelTransportError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


class ModelTransportTimeout(ModelTransportError):
    pass


@dataclass(frozen=True, slots=True)
class GenerationParams:
    """Decoding intent the loop hands to the model client for one turn.

    A real OpenAI-compatible client maps these onto the chat-completions request body
    (``temperature``/``seed``/``max_tokens``); the scripted client ignores them. Defaults
    encode the LOCKED determinism contract: greedy (temp 0), fixed seed, bounded output.
    """

    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 0
    max_output_tokens: int = 1024
    # ``stop`` sequences a real client may pass through; the loop relies on block fences /
    # the final-answer sentinel rather than stop strings, so this is advisory only.
    stop: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """One assistant turn returned by a model client.

    ``finish_reason`` mirrors the OpenAI convention so the loop can detect a per-turn token
    cap hit (``"length"``) deterministically without re-tokenising:

      * ``"stop"``   — the model finished a complete message,
      * ``"length"`` — generation hit ``max_output_tokens`` (treated as a turn-level
                        formatting failure: the block is almost certainly truncated),
      * ``"timeout"``/other — surfaced as a hard turn failure by the loop.

    ``output_tokens`` is the completion-token count for this turn when the client knows it
    (real client: from usage; scripted client: a deterministic word-ish estimate). It feeds
    the per-task token diagnostic, not the cap enforcement (the cap is enforced by the
    client via ``GenerationParams.max_output_tokens`` and surfaced via ``finish_reason``).
    """

    text: str
    finish_reason: str = "stop"
    output_tokens: int | None = None
    # Populated ONLY on client-degraded turns (finish_reason="error"): the transport/parse
    # cause (e.g. "http_status=404: ...", "URLError: refused") for per-turn diagnostics.
    error_detail: str | None = None
    server_timings: JsonObject | None = None


@runtime_checkable
class ModelClient(Protocol):
    """The ONLY thing the loop needs from a model: turn a chat history into one reply.

    Implementations MUST be deterministic given the same ``messages`` + ``params`` for the
    reproducibility contract (real client: temp 0 + fixed seed; scripted client: pure
    function of the history). The loop calls this once per turn and appends the returned
    text to the chat history as the assistant message.
    """

    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        """Return the assistant's reply for ``messages`` under ``params``."""
        ...
