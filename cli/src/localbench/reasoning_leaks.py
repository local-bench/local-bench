from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final

from localbench._types import JsonValue

THINK_OPEN: Final = "<think>"
THINK_CLOSE: Final = "</think>"
THINK_BLOCK_RE: Final = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
HARMONY_MESSAGE_MARKERS: Final = (
    "<|message|>",
    "<|start|>assistant<|channel|>final<|message|>",
)
HARMONY_REASONING_MARKERS: Final = ("<|channel|>analysis", "<|channel|>commentary")
GEMMA_EMPTY_THOUGHT_SCAFFOLD_RE: Final = re.compile(
    r"^(?:\s*<\|channel>thought\r?\n<channel\|>\s*)+",
    flags=re.IGNORECASE,
)
CANONICAL_REASONING_LEAK_REGEXES: Final[tuple[str, ...]] = (
    r"</?think\b",
    r"</?thinking\b",
    r"</?thought\b",
    r"</?reason(?:ing)?\b",
    r"</?scratchpad\b",
    r"◁think▷",
    r"<\|/?think(?:ing)?\|>",
    r"<\|/?(?:begin|end)_of_thought\|>",
    r"<\|channel\|>analysis",
    r"<\|channel\|>commentary",
    r"<\|message\|>",
    r"<\|channel>",
    r"<channel\|>",
)


def has_reasoning_leak(
    response_text: str | None,
    extra_regexes: Sequence[str] = (),
) -> bool:
    if not response_text:
        return False
    return _leak_detector(extra_regexes).search(response_text) is not None


def registry_leak_regexes(conformance: Mapping[str, JsonValue]) -> tuple[str, ...]:
    raw: JsonValue | tuple[str, ...] | None = conformance.get("leak_regexes")
    if isinstance(raw, tuple):
        return tuple(item for item in raw if isinstance(item, str))
    if isinstance(raw, list):
        return tuple(item for item in raw if isinstance(item, str))
    return ()


def strip_leading_gemma_empty_thought_scaffolds(text: str) -> str:
    return GEMMA_EMPTY_THOUGHT_SCAFFOLD_RE.sub("", text)


def _leak_detector(extra_regexes: Sequence[str]) -> re.Pattern[str]:
    if not extra_regexes:
        return _CANONICAL_REASONING_LEAK_RE
    return _compile_reasoning_leak_regex((*CANONICAL_REASONING_LEAK_REGEXES, *extra_regexes))


def _compile_reasoning_leak_regex(regexes: Sequence[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{regex})" for regex in regexes), re.IGNORECASE)


_CANONICAL_REASONING_LEAK_RE: Final = _compile_reasoning_leak_regex(
    CANONICAL_REASONING_LEAK_REGEXES,
)
