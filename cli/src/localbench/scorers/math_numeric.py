"""Numeric answer extraction and equivalence scoring."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Final

_REL_TOLERANCE: Final = 1e-4
_NUMBER_CORE: Final = (
    r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?"
)
_NUMBER_RE: Final = re.compile(
    rf"\$?\s*(?:{_NUMBER_CORE}\s*/\s*{_NUMBER_CORE}|{_NUMBER_CORE})",
)
_BOXED_RE: Final = re.compile(r"\\boxed\s*\{([^{}]+)\}", flags=re.IGNORECASE)
_MARKER_RE: Final = re.compile(
    r"\b(?:final\s+answer|answer(?:\s+is)?)\b\s*(?:is\s*)?(?::|=)?",
    flags=re.IGNORECASE,
)
_MARKER_SCAN_CHARS: Final = 120


def extract_final_number(text: str) -> str | None:
    """Extract and normalize the final numeric answer from model output."""
    if not text:
        return None

    for match in reversed(list(_BOXED_RE.finditer(text))):
        normalized = _normalize_number(match.group(1))
        if normalized is not None:
            return normalized

    for marker in reversed(list(_MARKER_RE.finditer(text))):
        snippet = text[marker.end() : marker.end() + _MARKER_SCAN_CHARS]
        normalized = _first_number(snippet)
        if normalized is not None:
            return normalized

    numbers = [
        normalized
        for normalized in (_normalize_number(match.group(0)) for match in _NUMBER_RE.finditer(text))
        if normalized is not None
    ]
    if not numbers:
        return None
    return numbers[-1]


def equivalent(a: str, b: str) -> bool:
    """Return whether two numeric strings are equivalent for scoring."""
    left = _to_fraction(a)
    right = _to_fraction(b)
    if left is None or right is None:
        return False
    if left == right:
        return True
    left_float = float(left)
    right_float = float(right)
    scale = max(abs(left_float), abs(right_float), 1.0)
    return abs(left_float - right_float) <= _REL_TOLERANCE * scale


def score_math(text: str, gold: str) -> bool:
    """Return whether extracted numeric answer matches the gold value."""
    extracted = extract_final_number(text)
    if extracted is None:
        return False
    return equivalent(extracted, gold)


def _first_number(text: str) -> str | None:
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    return _normalize_number(match.group(0))


def _normalize_number(value: str) -> str | None:
    match = _NUMBER_RE.search(value.strip())
    if match is None:
        return None
    token = match.group(0).strip().replace("$", "").replace(",", "")
    token = re.sub(r"\s*/\s*", "/", token).lower()
    if "/" in token:
        left, right = token.split("/", 1)
        token = f"{_normalize_decimal(left)}/{_normalize_decimal(right)}"
    else:
        token = _normalize_decimal(token)
    if _fraction_from_normalized(token) is None:
        return None
    return token


def _normalize_decimal(value: str) -> str:
    token = value.strip()
    if token.startswith("+"):
        token = token[1:]
    if token.startswith("-."):
        return f"-0{token[1:]}"
    if token.startswith("."):
        return f"0{token}"
    return token


def _to_fraction(value: str) -> Fraction | None:
    normalized = _normalize_number(value)
    if normalized is None:
        return None
    return _fraction_from_normalized(normalized)


def _fraction_from_normalized(value: str) -> Fraction | None:
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            return Fraction(Decimal(numerator)) / Fraction(Decimal(denominator))
        return Fraction(Decimal(value))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None
