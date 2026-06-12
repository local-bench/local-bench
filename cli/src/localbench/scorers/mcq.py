"""Multiple-choice answer extraction and scoring."""

from __future__ import annotations

import re
from typing import Final

_LETTERS: Final = "ABCDEFGHIJ"
_TAIL_CHARS: Final = 600

_PATTERN_GROUPS: Final = (
    (r"\bfinal\s+answer\s*(?:is\s*)?(?::|=)?\s*[\(\[]?\s*([A-J])\s*[\)\]]?(?![A-Z])", None),
    (r"\banswer\s*(?:is\s*)?(?::|=)?\s*[\(\[]?\s*([A-J])\s*[\)\]]?(?![A-Z])", None),
    (r"\\boxed\s*\{\s*([A-J])\s*\}", None),
    (r"\*\*\s*([A-J])\s*\*\*", None),
    (r"(?m)^\s*[\(\[]?\s*([A-J])\s*[\)\]\.]?\s*$", None),
    (r"\(([A-J])\)", _TAIL_CHARS),
)


def extract_choice(text: str, n_options: int) -> str | None:
    """Extract the final MCQ letter from model output."""
    if not text or n_options < 1 or n_options > len(_LETTERS):
        return None

    allowed = set(_LETTERS[:n_options])
    for pattern, tail_chars in _PATTERN_GROUPS:
        source = text if tail_chars is None else text[-tail_chars:]
        candidates = _matching_letters(pattern, source, allowed)
        if not candidates:
            continue
        distinct = set(candidates)
        if len(distinct) == 1:
            return candidates[-1]
        return None
    return None


def score_mcq(text: str, gold_letter: str, n_options: int) -> bool:
    """Return whether extracted MCQ answer matches the gold letter."""
    extracted = extract_choice(text, n_options)
    if extracted is None:
        return False
    return extracted == gold_letter.strip().upper()


def _matching_letters(pattern: str, source: str, allowed: set[str]) -> list[str]:
    return [
        match.group(1).upper()
        for match in re.finditer(pattern, source, flags=re.IGNORECASE)
        if match.group(1).upper() in allowed
    ]
