"""Deterministic RULER-style NIAH generator and exact-match scorer."""

from __future__ import annotations

import json
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, TypeAlias, TypedDict

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

TARGET_HAYSTACK_TOKENS: Final = 32_000
FILLER_CORPUS_ID: Final = "synthetic-ruler-local-v1"
DEFAULT_TEMPLATE: Final = (
    "You are evaluating long-context retrieval.\n\n"
    "Haystack:\n{haystack}\n\n"
    "Question:\n{question}\n\n"
    "Only return the requested value(s), in the requested order. Do not explain."
)
_FENCE_RE: Final = re.compile(r"```(?:json|text)?\s*\n(?P<body>.*?)```", re.DOTALL)
_FILLER_WORDS: Final = (
    "atlas",
    "binary",
    "cedar",
    "delta",
    "ember",
    "fable",
    "garden",
    "harbor",
    "isotope",
    "jasmine",
    "kernel",
    "lantern",
    "matrix",
    "nebula",
    "opal",
    "prairie",
    "quartz",
    "radial",
    "signal",
    "timber",
    "umbra",
    "vector",
    "willow",
    "xenon",
    "yonder",
    "zenith",
)


class RulerScore(TypedDict):
    correct: bool
    extracted: str | None


@dataclass(frozen=True, slots=True)
class RenderedRulerItem:
    haystack: str
    question: str
    answers: tuple[str, ...]
    canonical_answer: str
    haystack_token_estimate: int


def build_ruler_prompt(prompt_item: Mapping[str, JsonValue], template: str | None = None) -> str:
    """Regenerate the deterministic haystack and format the RULER prompt."""
    rendered = render_ruler_item(prompt_item)
    prompt_template = template if template is not None else DEFAULT_TEMPLATE
    return prompt_template.format(haystack=rendered.haystack, question=rendered.question)


def render_ruler_item(prompt_item: Mapping[str, JsonValue]) -> RenderedRulerItem:
    """Render a compact RULER seed+params row into its long haystack task."""
    seed = _required_int(prompt_item, "seed")
    target_tokens = _optional_int(prompt_item, "haystack_token_count", TARGET_HAYSTACK_TOKENS)
    depth_percent = _required_int(prompt_item, "target_depth_percent")
    task_type = _required_str(prompt_item, "task_type")
    needle_block = _needle_block(prompt_item, task_type)
    answers = _answers(prompt_item, task_type)
    filler_count = max(0, target_tokens - len(needle_block.split()))
    insert_index = round(filler_count * max(0, min(100, depth_percent)) / 100)
    filler_words = _filler_words(seed, filler_count)
    haystack_parts = [
        *filler_words[:insert_index],
        needle_block,
        *filler_words[insert_index:],
    ]
    haystack = " ".join(part for part in haystack_parts if part)
    return RenderedRulerItem(
        haystack=haystack,
        question=_question(prompt_item, task_type),
        answers=answers,
        canonical_answer=_canonical_answer(answers),
        haystack_token_estimate=len(haystack.split()),
    )


def score_ruler(prompt_item: Mapping[str, JsonValue], response_text: str) -> RulerScore:
    """Score by exact match against the regenerated needle value or values."""
    rendered = render_ruler_item(prompt_item)
    extracted = _extract_response(response_text, len(rendered.answers))
    return {
        "correct": extracted == rendered.canonical_answer,
        "extracted": extracted,
    }


def estimate_prompt_tokens(prompt: str) -> int:
    """Estimate prompt tokens for truncation checks using whitespace-tokenized text."""
    return len(prompt.split())


def _filler_words(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    return [_FILLER_WORDS[rng.randrange(len(_FILLER_WORDS))] for _ in range(count)]


def _needle_block(prompt_item: Mapping[str, JsonValue], task_type: str) -> str:
    match task_type:
        case "niah_single":
            key = _required_str(prompt_item, "needle_key")
            value = _required_str(prompt_item, "needle_value")
            return f"Needle record: key {key} stores value {value}."
        case "niah_multikey":
            keys = _string_list(prompt_item.get("needle_keys"))
            values = _string_list(prompt_item.get("needle_values"))
            return " ".join(
                f"Needle record: key {key} stores value {value}."
                for key, value in zip(keys, values, strict=True)
            )
        case _:
            raise TypeError(f"unsupported RULER task_type: {task_type}")


def _question(prompt_item: Mapping[str, JsonValue], task_type: str) -> str:
    match task_type:
        case "niah_single":
            return f"What is the value for key {_required_str(prompt_item, 'needle_key')}?"
        case "niah_multikey":
            keys = _string_list(prompt_item.get("target_keys"))
            return f"What are the values for keys {', '.join(keys)}, in that order?"
        case _:
            raise TypeError(f"unsupported RULER task_type: {task_type}")


def _answers(prompt_item: Mapping[str, JsonValue], task_type: str) -> tuple[str, ...]:
    match task_type:
        case "niah_single":
            return (_required_str(prompt_item, "needle_value"),)
        case "niah_multikey":
            return tuple(_string_list(prompt_item.get("answer_values")))
        case _:
            raise TypeError(f"unsupported RULER task_type: {task_type}")


def _extract_response(response_text: str, answer_count: int) -> str | None:
    candidate = _candidate_text(response_text)
    if not candidate:
        return None
    if answer_count == 1:
        return candidate
    json_values = _json_string_list(candidate)
    if json_values is not None:
        return _canonical_answer(json_values)
    parts = [part.strip() for part in re.split(r"[,;\n]+", candidate) if part.strip()]
    if len(parts) != answer_count:
        return candidate
    return _canonical_answer(tuple(parts))


def _candidate_text(response_text: str) -> str:
    stripped = response_text.strip()
    match = _FENCE_RE.fullmatch(stripped)
    if match is not None:
        return match.group("body").strip()
    return stripped


def _json_string_list(candidate: str) -> tuple[str, ...] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        return None
    return tuple(parsed)


def _canonical_answer(values: tuple[str, ...]) -> str:
    return ",".join(values)


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_int(row: Mapping[str, JsonValue], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_int(row: Mapping[str, JsonValue], key: str, default: int) -> int:
    value = row.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("expected a list of strings")
    return value
