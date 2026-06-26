from __future__ import annotations

import re
from typing import Final

_THINK_OPEN: Final = "<think>"
_THINK_CLOSE: Final = "</think>"
_THINK_BLOCK_RE: Final = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_HARMONY_MESSAGE_MARKERS: Final = ("<|message|>", "<|start|>assistant<|channel|>final<|message|>")
_HARMONY_REASONING_MARKERS: Final = ("<|channel|>analysis", "<|channel|>commentary")


def strip_reasoning(text: str) -> str:
    lowered = text.lower()
    has_think_open = _THINK_OPEN in lowered
    has_think_close = _THINK_CLOSE in lowered
    has_harmony = any(marker in lowered for marker in _HARMONY_REASONING_MARKERS)
    if not has_think_open and not has_think_close and not has_harmony:
        return text

    if has_think_close:
        close_index = lowered.rfind(_THINK_CLOSE)
        candidate = text[close_index + len(_THINK_CLOSE) :]
        return _THINK_BLOCK_RE.sub("", candidate)

    if has_think_open:
        # A truncated reasoning block has no reliable final answer boundary; score it as absent.
        return ""

    return _strip_harmony_reasoning(text)


def _strip_harmony_reasoning(text: str) -> str:
    lowered = text.lower()
    message_index = max(lowered.rfind(marker) for marker in _HARMONY_MESSAGE_MARKERS)
    if message_index < 0:
        return text
    marker = next(
        item
        for item in _HARMONY_MESSAGE_MARKERS
        if lowered.startswith(item, message_index)
    )
    return text[message_index + len(marker) :]
