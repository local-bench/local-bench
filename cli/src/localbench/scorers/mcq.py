"""Multiple-choice answer extraction and scoring."""

from __future__ import annotations

import re
from typing import Final, TypedDict

_LETTERS: Final = "ABCDEFGHIJ"
_TAIL_CHARS: Final = 600

# Capture the answer letter immediately after the marker (group 1) plus an OPTIONAL adjacent
# alternative letter (group 2) joined by or/and/comma/slash. Only an adjacent alternation ("A or B")
# is treated as ambiguous; a letter mentioned later in trailing explanation ("A because B is wrong",
# "G, not A") does NOT block extraction of the stated answer.
_MARKER_PATTERNS: Final = (
    r"\bfinal\s+answer\s*(?:is\s*)?(?::|=)?\s*[\(\[]?\s*([A-J])(?![A-Za-z])\s*[\)\]]?(?:\s*(?:or|and|,|/)\s*[\(\[]?\s*([A-J])(?![A-Za-z]))?",
    r"\banswer\s*(?:is\s*)?(?::|=)?\s*[\(\[]?\s*([A-J])(?![A-Za-z])\s*[\)\]]?(?:\s*(?:or|and|,|/)\s*[\(\[]?\s*([A-J])(?![A-Za-z]))?",
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
    for pattern in _MARKER_PATTERNS:
        marker_letter: str | None = None
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            first = match.group(1).upper()
            if first not in allowed:
                continue
            alternative = match.group(2)
            if alternative is not None and alternative.upper() in allowed and alternative.upper() != first:
                return None  # adjacent alternation like "A or B" is genuinely ambiguous
            marker_letter = first
        if marker_letter is not None:
            return marker_letter

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
