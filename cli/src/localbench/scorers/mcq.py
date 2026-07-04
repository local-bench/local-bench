"""Multiple-choice answer extraction and scoring."""

from __future__ import annotations

import re
from typing import Final, TypedDict

_LETTERS: Final = "ABCDEFGHIJ"
_TAIL_CHARS: Final = 600

# Capture the answer letter immediately after the marker (group 1) plus an OPTIONAL adjacent
# alternative letter (group 2) joined by or/and/slash. Only an adjacent alternation ("A or B")
# is treated as ambiguous; a letter mentioned later in trailing explanation ("A because B is wrong",
# "G, not A") does NOT block extraction of the stated answer.
# An optional `**...**` may wrap the marker's letter ("Final answer: **C** because ...") — the
# letter is a stated answer in marker context, so accept the bold delimiters here (distinct from a
# bold letter mid-reasoning with no marker, which the end-anchored fallback still rejects).
_MARKER_PATTERNS: Final = (
    r"\bfinal\s+answer\s*(?:is\s*)?(?::|=)?\s*(?:\*\*)?\s*[\(\[]?\s*([A-J])(?![A-Za-z])\s*[\)\]]?\s*(?:\*\*)?(?:\s*(?:or|and|/)\s*[\(\[]?\s*([A-J])(?![A-Za-z]))?",
    r"\banswer\s*(?:is\s*)?(?::|=)?\s*(?:\*\*)?\s*[\(\[]?\s*([A-J])(?![A-Za-z])\s*[\)\]]?\s*(?:\*\*)?(?:\s*(?:or|and|/)\s*[\(\[]?\s*([A-J])(?![A-Za-z]))?",
)
_PATTERN_GROUPS: Final = (
    (r"\\boxed\s*\{\s*([A-J])\s*\}", None, False),
    # A bold letter counts as the answer only when it ENDS the response ("...the answer is
    # **C**"), optionally with trailing punctuation. A bold letter embedded in prose with
    # text after it ("still weighing **G** here") is mid-reasoning, not an answer — the old
    # match-anywhere bold fallback credited those, a false positive on hedged/truncated output.
    (r"\*\*\s*([A-J])\s*\*\*[\s.):\]]*\Z", None, True),
    (r"(?m)^\s*[\(\[]?\s*([A-J])\s*[\)\]\.]?\s*$", None, True),
    (r"\(([A-J])\)", _TAIL_CHARS, True),
)
# A terminal comma-separated letter list after the marker ("Final answer: A, B" / "answer: A, B, C")
# is genuinely ambiguous — multiple answers for a single-choice MCQ. It is distinguished from an
# explanatory clause ("A, B is wrong") by requiring the list to run to end-of-line (optional period).
_TERMINAL_LIST_RE: Final = re.compile(
    r"\b(?:final\s+answer|answer)\s*(?:is\s*)?(?::|=)?\s*"
    r"([\(\[]?\s*[A-J]\s*[\)\]]?(?:\s*,\s*[\(\[]?\s*[A-J]\s*[\)\]]?)+)\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_BOXED_CONTENT_RE: Final = re.compile(
    r"\\boxed\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
    re.IGNORECASE | re.DOTALL,
)
_BOXED_PREFIX_RE: Final = re.compile(
    r"^\s*(?:\\text\s*\{\s*)?([A-J])(?=\s*(?:\}|[.)]|\s*$))",
    re.IGNORECASE,
)
_BOXED_LETTER_TOKEN_RE: Final = re.compile(r"(?<![A-Za-z])([A-J])(?![A-Za-z])", re.IGNORECASE)


class MCQScore(TypedDict):
    extracted: str | None
    correct: bool


def extract_choice(text: str, n_options: int) -> str | None:
    """Extract the final MCQ letter from model output."""
    if not text or n_options < 1 or n_options > len(_LETTERS):
        return None

    allowed = set(_LETTERS[:n_options])
    if _terminal_letter_list_is_ambiguous(text, allowed):
        return None
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
    return _extract_latex_boxed_choice(text, allowed)


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


def _terminal_letter_list_is_ambiguous(text: str, allowed: set[str]) -> bool:
    for match in _TERMINAL_LIST_RE.finditer(text):
        letters = {letter.upper() for letter in re.findall(r"[A-Ja-j]", match.group(1))} & allowed
        if len(letters) > 1:
            return True
    return False


def _extract_latex_boxed_choice(text: str, allowed: set[str]) -> str | None:
    boxed_letter: str | None = None
    for match in _BOXED_CONTENT_RE.finditer(text):
        content = match.group(1)
        prefix = _BOXED_PREFIX_RE.match(content)
        if prefix is None:
            continue
        first = prefix.group(1).upper()
        if first not in allowed:
            continue
        letters = {letter.upper() for letter in _BOXED_LETTER_TOKEN_RE.findall(content)} & allowed
        if letters != {first}:
            continue
        boxed_letter = first
    return boxed_letter
