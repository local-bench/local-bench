from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import InvalidOperation
from tokenize import TokenError
from typing import Final

from math_verify import ExprExtractionConfig, LatexExtractionConfig, parse, verify
from sympy import E, Basic, Interval, exp, pi, simplify, sqrt
from sympy.core.sympify import SympifyError
from sympy.parsing.sympy_parser import convert_xor, implicit_multiplication_application, parse_expr, standard_transformations

_REL_TOLERANCE: Final = 1e-4
_MARKER_RE: Final = re.compile(r"\b(?:final\s+answer|answer(?:\s+is)?)\b\s*(?:is\s*)?(?::|=)?", flags=re.IGNORECASE)
_NUMBER_CORE: Final = r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_NUMBER_RE: Final = re.compile(rf"\$?\s*(?:{_NUMBER_CORE}\s*/\s*{_NUMBER_CORE}|{_NUMBER_CORE})")
_MATH_VERIFY_CONFIG: Final = (LatexExtractionConfig(), ExprExtractionConfig())
_SYMPY_TRANSFORMATIONS: Final = standard_transformations + (implicit_multiplication_application, convert_xor)
_SYMPY_LOCALS: Final = {"E": E, "e": E, "exp": exp, "pi": pi, "sqrt": sqrt}
_PARSE_ERRORS: Final = (ArithmeticError, InvalidOperation, SyntaxError, SympifyError, TokenError, TypeError, ValueError)


@dataclass(frozen=True, slots=True)
class _Ratio:
    terms: tuple[Basic, ...]


_ParsedMath = Basic | Interval | _Ratio | tuple[Basic, ...] | frozenset[Basic]


def extract_math_answer(text: str) -> str | None:
    if not text:
        return None

    boxed = _last_boxed_content(text)
    if boxed is not None:
        return boxed

    for marker in reversed(list(_MARKER_RE.finditer(text))):
        candidate = _clean_candidate(text[marker.end() :])
        if _is_answer_candidate(candidate):
            return candidate

    numbers = [_clean_candidate(match.group(0)) for match in _NUMBER_RE.finditer(text)]
    return numbers[-1] if numbers else None


def verify_math(response_text: str, gold: str) -> bool:
    answer = extract_math_answer(response_text)
    if answer is None:
        return False
    return _equivalent(answer, gold)


def _equivalent(answer: str, gold: str) -> bool:
    if _verify_with_math_verify(answer, gold):
        return True

    parsed_answer = _parse_candidate(answer)
    parsed_gold = _parse_candidate(gold)
    if parsed_answer is None or parsed_gold is None:
        return False
    return _parsed_equivalent(parsed_answer, parsed_gold)


def _verify_with_math_verify(answer: str, gold: str) -> bool:
    parsed_answer = _parse_math_verify(answer)
    parsed_gold = _parse_math_verify(gold)
    if not parsed_answer or not parsed_gold:
        return False
    return verify(parsed_gold, parsed_answer, float_rounding=4, numeric_precision=15, strict=False, allow_set_relation_comp=True, timeout_seconds=0, raise_on_error=False)


def _parse_math_verify(value: str) -> list[Basic | str]:
    return parse(value, extraction_config=_MATH_VERIFY_CONFIG, parsing_timeout=0, raise_on_error=False)


def _parsed_equivalent(left: _ParsedMath, right: _ParsedMath) -> bool:
    if isinstance(left, _Ratio) and isinstance(right, _Ratio):
        return _ratios_equivalent(left.terms, right.terms)
    if isinstance(left, tuple) and isinstance(right, tuple):
        return len(left) == len(right) and all(_sympy_equivalent(left_item, right_item) for left_item, right_item in zip(left, right, strict=True))
    if isinstance(left, frozenset) and isinstance(right, frozenset):
        return _sets_equivalent(left, right)
    if isinstance(left, Interval) and isinstance(right, Interval):
        return left == right
    if isinstance(left, Basic) and isinstance(right, Basic):
        return _sympy_equivalent(left, right)
    return False


def _sympy_equivalent(left: Basic, right: Basic) -> bool:
    if left == right:
        return True
    if left.is_number and right.is_number:
        return _numeric_equivalent(left, right)
    try:
        simplified = simplify(left - right)
    except (ArithmeticError, TypeError, ValueError, SympifyError):
        return False
    return bool(simplified == 0)


def _numeric_equivalent(left: Basic, right: Basic) -> bool:
    try:
        left_float = float(left.evalf(20))
        right_float = float(right.evalf(20))
    except (ArithmeticError, TypeError, ValueError):
        return False
    scale = max(abs(left_float), abs(right_float), 1.0)
    return abs(left_float - right_float) <= _REL_TOLERANCE * scale


def _ratios_equivalent(left: tuple[Basic, ...], right: tuple[Basic, ...]) -> bool:
    if len(left) != len(right) or not left or not right:
        return False
    left_base = left[0]
    right_base = right[0]
    return all(_sympy_equivalent(left_item * right_base, right_item * left_base) for left_item, right_item in zip(left[1:], right[1:], strict=True))


def _sets_equivalent(left: frozenset[Basic], right: frozenset[Basic]) -> bool:
    if len(left) != len(right):
        return False
    remaining = list(right)
    for left_item in left:
        match_index = next((index for index, right_item in enumerate(remaining) if _sympy_equivalent(left_item, right_item)), None)
        if match_index is None:
            return False
        remaining.pop(match_index)
    return not remaining


def _parse_candidate(value: str) -> _ParsedMath | None:
    token = _normalize_latex(value)
    for parser in (_parse_ratio, _parse_interval, _parse_set, _parse_tuple):
        parsed = parser(token)
        if parsed is not None:
            return parsed
    return _parse_expr(token)


def _is_answer_candidate(candidate: str) -> bool:
    if not candidate:
        return False
    if _parse_candidate(candidate) is not None:
        return True
    return _NUMBER_RE.search(candidate) is not None


def _parse_ratio(token: str) -> _Ratio | None:
    parts = _split_top_level(token, ":")
    if len(parts) < 2:
        return None
    parsed = _parse_expr_parts(parts)
    return _Ratio(parsed) if parsed is not None else None


def _parse_interval(token: str) -> Interval | None:
    if len(token) < 5 or token[0] not in "[(" or token[-1] not in "])":
        return None
    left_open = token[0] == "("
    right_open = token[-1] == ")"
    if token[0] != "[" and token[-1] != "]":
        return None
    parsed = _parse_expr_parts(_split_top_level(token[1:-1], ","))
    if parsed is None or len(parsed) != 2:
        return None
    return Interval(parsed[0], parsed[1], left_open=left_open, right_open=right_open)


def _parse_set(token: str) -> frozenset[Basic] | None:
    if not token.startswith("{") or not token.endswith("}"):
        return None
    parsed = _parse_expr_parts(_split_top_level(token[1:-1], ","))
    return frozenset(parsed) if parsed is not None else None


def _parse_tuple(token: str) -> tuple[Basic, ...] | None:
    if not token.startswith("(") or not token.endswith(")"):
        return None
    parts = _split_top_level(token[1:-1], ",")
    if len(parts) < 2:
        return None
    return _parse_expr_parts(parts)


def _parse_expr_parts(parts: list[str]) -> tuple[Basic, ...] | None:
    parsed = tuple(_parse_expr(part) for part in parts)
    return None if any(part is None for part in parsed) else parsed


def _parse_expr(token: str) -> Basic | None:
    if not token:
        return None
    try:
        parsed = parse_expr(token, local_dict=_SYMPY_LOCALS, transformations=_SYMPY_TRANSFORMATIONS, evaluate=False)
    except _PARSE_ERRORS:
        return None
    return parsed if isinstance(parsed, Basic) else None


def _normalize_latex(value: str) -> str:
    token = _clean_candidate(value)
    for old, new in ((r"\left", ""), (r"\right", ""), (r"\,", ""), (r"\!", ""), (r"\cdot", "*"), (r"\times", "*"), (r"\pi", "pi"), (r"\{", "{"), (r"\}", "}")):
        token = token.replace(old, new)
    token = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", token)
    while True:
        updated = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", token)
        if updated == token:
            break
        token = updated
    return token.strip()


def _last_boxed_content(text: str) -> str | None:
    contents: list[str] = []
    for match in re.finditer(r"\\boxed\s*\{", text, flags=re.IGNORECASE):
        content = _balanced_content(text, match.end() - 1)
        if content:
            contents.append(_clean_candidate(content))
    return contents[-1] if contents else None


def _balanced_content(text: str, opening_brace_index: int) -> str | None:
    depth = 0
    escaped = False
    start = opening_brace_index + 1
    for index, character in enumerate(text[opening_brace_index:], start=opening_brace_index):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return None


def _clean_candidate(value: str) -> str:
    token = value.splitlines()[0].strip()
    token = re.sub(r"\s+", " ", token)
    token = token.removeprefix("$").removesuffix("$").strip()
    if token.startswith(r"\(") and token.endswith(r"\)"):
        token = token[2:-2].strip()
    if token.startswith(r"\[") and token.endswith(r"\]"):
        token = token[2:-2].strip()
    return token.rstrip(" .,:;")


def _split_top_level(token: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    escaped = False
    for index, character in enumerate(token):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == separator and depth == 0:
            parts.append(token[start:index].strip())
            start = index + 1
    parts.append(token[start:].strip())
    return parts
