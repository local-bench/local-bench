from __future__ import annotations

from localbench.reasoning_leaks import (
    HARMONY_MESSAGE_MARKERS,
    HARMONY_REASONING_MARKERS,
    THINK_BLOCK_RE,
    THINK_CLOSE,
    THINK_OPEN,
    strip_leading_gemma_empty_thought_scaffolds,
)


def strip_reasoning(text: str) -> str:
    candidate = strip_leading_gemma_empty_thought_scaffolds(text)
    lowered = candidate.lower()
    has_think_open = THINK_OPEN in lowered
    has_think_close = THINK_CLOSE in lowered
    has_harmony = any(marker in lowered for marker in HARMONY_REASONING_MARKERS)
    if not has_think_open and not has_think_close and not has_harmony:
        return candidate

    if has_think_close:
        close_index = lowered.rfind(THINK_CLOSE)
        answer = candidate[close_index + len(THINK_CLOSE) :]
        return strip_leading_gemma_empty_thought_scaffolds(THINK_BLOCK_RE.sub("", answer))

    if has_think_open:
        # A truncated reasoning block has no reliable final answer boundary; score it as absent.
        return ""

    return strip_leading_gemma_empty_thought_scaffolds(_strip_harmony_reasoning(candidate))


def _strip_harmony_reasoning(text: str) -> str:
    lowered = text.lower()
    message_index = max(lowered.rfind(marker) for marker in HARMONY_MESSAGE_MARKERS)
    if message_index < 0:
        return text
    marker = next(
        item
        for item in HARMONY_MESSAGE_MARKERS
        if lowered.startswith(item, message_index)
    )
    return text[message_index + len(marker) :]
