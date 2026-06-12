"""Multiple-choice answer extraction and scoring."""

from __future__ import annotations

import re
from typing import Final, TypedDict

_LETTERS: Final = "ABCDEFGHIJ"
_TAIL_CHARS: Final = 600

_MARKER_SPAN_PATTERNS: Final = (
    r"\bfinal\s+answer\s*(?:is\s*)?(?::|=)?\s*(.*?)(?=(?:\bfinal\s+answer\s*(?:is\s*)?(?::|=)?|\banswer\s*(?:is\s*)?(?::|=)?|\n|$))",
    r"\banswer\s*(?:is\s*)?(?::|=)?\s*(.*?)(?=(?:\bfinal\s+answer\s*(?:is\s*)?(?::|=)?|\banswer\s*(?:is\s*)?(?::|=)?|\n|$))",
)
_PATTERN_GROUPS: Final = (
    (r"\\boxed\s*\{\s*([A-J])\s*\}", None, False),
    (r"\*\*\s*([A-J])\s*\*\*", None, False),
    (r"(?m)^\s*[\(\[]?\s*([A-J])\s*[\)\]\.]?\s*$", None, True),
    (r"\(([A-J])\)", _TAIL_CHARS, True),
)


class MCQScore(TypedDict):
    extracted: str | None
    correct: bool


def extract_choice(text: str, n_options: int) -> str | None:
    """Extract the final MCQ letter from model output."""
    if not text or n_options < 1 or n_options > len(_LETTERS):
        return None

    allowed = set(_LETTERS[:n_options])
    for pattern in _MARKER_SPAN_PATTERNS:
        candidates = _matching_marker_letters(pattern, text, allowed)
        if candidates is None:
            return None
        if candidates:
            return candidates[-1]

    for pattern, tail_chars, conflict_on_distinct in _PATTERN_GROUPS:
        source = text if tail_chars is None else text[-tail_chars:]
        candidates = _matching_letters(pattern, source, allowed)
        if not candidates:
            continue
        if conflict_on_distinct and len(set(candidates)) > 1:
            return None
        return candidates[-1]
    return None


def score_mcq_detailed(text: str, gold_letter: str, n_options: int) -> MCQScore:
    """Return extracted MCQ answer and correctness."""
    extracted = extract_choice(text, n_options)
    return {
        "extracted": extracted,
        "correct": extracted is not None and extracted == gold_letter.strip().upper(),
    }


def score_mcq(text: str, gold_letter: str, n_options: int) -> bool:
    """Return whether extracted MCQ answer matches the gold letter."""
    return score_mcq_detailed(text, gold_letter, n_options)["correct"]


def _matching_letters(pattern: str, source: str, allowed: set[str]) -> list[str]:
    return [
        match.group(1).upper()
        for match in re.finditer(pattern, source, flags=re.IGNORECASE)
        if match.group(1).upper() in allowed
    ]


def _matching_marker_letters(pattern: str, source: str, allowed: set[str]) -> list[str] | None:
    candidates: list[str] = []
    for match in re.finditer(pattern, source, flags=re.IGNORECASE):
        span_letters = _matching_letters(
            r"(?<![A-Z])[\(\[]?\s*([A-J])\s*[\)\]]?(?![A-Z])",
            match.group(1),
            allowed,
        )
        if len(set(span_letters)) > 1:
            return None
        candidates.extend(span_letters)
    return candidates
