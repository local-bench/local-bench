from __future__ import annotations

import re
import string
from collections import Counter
from collections.abc import Sequence
from typing import cast

from localbench._types import JsonObject, JsonValue
from localbench.checkset.gates import determinism_canary_matches
from localbench.checkset.stateful import score_trajectory
from localbench.coding_exec.sandbox import SandboxLimits, docker_run_argv
from localbench.scorers.bfcl import score_bfcl
from localbench.scorers.ifbench import score_ifbench
from localbench.scorers.math_symbolic import verify_math
from localbench.scorers.mcq import score_mcq_detailed
from localbench.scorers.tc_json_v1 import score_tc_json_v1
from localbench.scoring.signed_score import signed_score


def grade_response(
    module: str,
    source_item: JsonObject,
    generation: JsonObject,
    *,
    repeated_generation: JsonObject | None = None,
) -> JsonObject:
    text = generation.get("text")
    response_text = text if isinstance(text, str) else ""
    if module == "knowledge":
        choices = source_item.get("choices")
        answer_index = source_item.get("answer_index")
        if not isinstance(choices, list) or not choices or not isinstance(answer_index, int):
            return _result(False, chance=0.25, detail={"failure": "invalid-mcq-source"})
        if answer_index < 0 or answer_index >= len(choices) or len(choices) > len(string.ascii_uppercase):
            return _result(False, chance=1.0 / len(choices), detail={"failure": "invalid-mcq-answer"})
        detail = score_mcq_detailed(response_text, string.ascii_uppercase[answer_index], len(choices))
        return _result(detail["correct"], chance=1.0 / len(choices), detail=cast(JsonObject, dict(detail)))
    if module == "instruction":
        detail = score_ifbench(source_item, response_text)
        return _result(detail["strict"], detail=cast(JsonObject, dict(detail)))
    if module == "math":
        gold = source_item.get("answer", source_item.get("gold_answer"))
        finish_reason = generation.get("finish_reason")
        correct = isinstance(gold, str) and verify_math(
            response_text,
            gold,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )
        return _result(correct, detail={"verifier": "math-symbolic-v1"})
    if module == "coding":
        return _grade_coding(generation)
    if module == "tools-single":
        if "gold" in source_item and "match_policy" in source_item:
            detail = score_tc_json_v1(source_item, response_text)
        else:
            detail = score_bfcl(source_item, response_text)
        return _result(bool(detail["correct"]), detail=cast(JsonObject, dict(detail)))
    if module == "tools-stateful":
        raw_calls = generation.get("parsed_tool_calls")
        calls = _object_list(raw_calls)
        return _result(
            score_trajectory(source_item, calls),
            detail={"parsed_tool_calls": [dict(call) for call in calls], "scorer": "state-machine-exact"},
        )
    if module == "sanity-gates":
        return _grade_gate(source_item, generation, repeated_generation=repeated_generation)
    return _result(False, detail={"failure": f"unknown-module:{module}"})


def grade_mock_generation(generation: JsonObject) -> JsonObject:
    correct = generation.get("mock_correct") is True
    return _result(correct, detail={"scorer": "deterministic-dry-run-fixture"})


def sandbox_command(
    image_digest: str,
    command: Sequence[str],
    *,
    limits: SandboxLimits | None = None,
) -> list[str]:
    return docker_run_argv(image_digest, command, limits=limits)


def _grade_coding(generation: JsonObject) -> JsonObject:
    artifact = generation.get("code_artifact")
    if not isinstance(artifact, dict):
        return {**_result(False, detail={"failure": "missing-verifier-artifact"}), "trusted_verdict": False}
    verdict = artifact.get("verdict")
    image = artifact.get("image_digest")
    trusted = (
        artifact.get("verdict_source") == "verifier"
        and isinstance(verdict, dict)
        and isinstance(verdict.get("passed"), bool)
        and isinstance(image, str)
        and "@sha256:" in image
    )
    correct = trusted and isinstance(verdict, dict) and verdict.get("passed") is True
    return {
        **_result(correct, detail={"scorer": "bigcodebench-sandbox-v1"}),
        "trusted_verdict": trusted,
    }


def _grade_gate(
    source_item: JsonObject,
    generation: JsonObject,
    *,
    repeated_generation: JsonObject | None,
) -> JsonObject:
    category = source_item.get("category")
    expected = source_item.get("expected")
    text = generation.get("text")
    response = text if isinstance(text, str) else ""
    if not isinstance(expected, dict) or not isinstance(category, str):
        return _result(False, detail={"failure": "invalid-gate-source"})
    response_words = _word_sequence(response)
    correct = False
    loop_detected: bool | None = None
    if category == "stop-token":
        required = expected.get("required")
        stop_marker = expected.get("stop_marker")
        forbidden = expected.get("forbidden_suffix")
        if isinstance(required, str) and isinstance(stop_marker, str):
            required_words = _word_sequence(required)
            marker_words = _word_sequence(stop_marker)
            forbidden_words = _word_sequence(forbidden) if isinstance(forbidden, str) else ()
            required_end = len(required_words)
            tail = response_words[required_end:]
            forbidden_absent = not forbidden_words or not any(
                tail[index : index + len(forbidden_words)] == forbidden_words
                for index in range(len(tail) - len(forbidden_words) + 1)
            )
            correct = (
                bool(required_words)
                and bool(marker_words)
                and response_words[:required_end] == required_words
                and response_words[-len(marker_words) :] == marker_words
                and forbidden_absent
            )
    elif category == "template-canary":
        answer = expected.get("answer")
        correct = isinstance(answer, str) and response_words == _word_sequence(answer)
    elif category == "long-context-needle":
        answer = expected.get("answer")
        correct = isinstance(answer, str) and answer in response
    elif category == "budget-control":
        answer = expected.get("answer")
        think_budget = expected.get("think_budget")
        reasoning = generation.get("reasoning_text")
        usage = generation.get("usage")
        reasoning_tokens = usage.get("reasoning_tokens") if isinstance(usage, dict) else None
        protocol_flag = generation.get("protocol_flag")
        budget_respected = (
            isinstance(think_budget, int)
            and not isinstance(think_budget, bool)
            and isinstance(reasoning_tokens, int)
            and not isinstance(reasoning_tokens, bool)
            and 0 <= reasoning_tokens <= think_budget
            and (protocol_flag != "think-budget-exhausted" or reasoning_tokens == think_budget)
        )
        correct = (
            isinstance(answer, str)
            and answer in response
            and isinstance(reasoning, str)
            and bool(reasoning.strip())
            and protocol_flag in {None, "none", "think-budget-exhausted"}
            and budget_respected
        )
    elif category == "repetition":
        answer = expected.get("answer")
        stop_marker = expected.get("stop_marker")
        loop_detection = expected.get("loop_detection")
        if isinstance(answer, str) and isinstance(stop_marker, str) and isinstance(loop_detection, dict):
            ngram_size = loop_detection.get("ngram_size")
            max_occurrences = loop_detection.get("max_occurrences")
            tokenization = loop_detection.get("tokenization")
            if (
                isinstance(ngram_size, int)
                and ngram_size > 0
                and isinstance(max_occurrences, int)
                and max_occurrences > 0
                and tokenization == "unicode-word-punctuation-v1"
            ):
                loop_detected = _has_ngram_loop(
                    response,
                    ngram_size=ngram_size,
                    max_occurrences=max_occurrences,
                )
                answer_words = _word_sequence(answer)
                marker_words = _word_sequence(stop_marker)
                correct = (
                    response_words == answer_words
                    and bool(marker_words)
                    and response_words[-len(marker_words) :] == marker_words
                    and not loop_detected
                )
    elif category == "determinism":
        answer = expected.get("answer")
        tool = expected.get("tool")
        arguments = expected.get("arguments")
        primary_correct = isinstance(answer, str) and answer in response
        if isinstance(tool, str) and isinstance(arguments, dict):
            primary_correct = {"name": tool, "arguments": arguments} in _object_list(generation.get("parsed_tool_calls"))
        correct = (
            primary_correct
            and repeated_generation is not None
            and determinism_canary_matches(generation, repeated_generation)
        )
    detail: JsonObject = {
        "category": category,
        "gate_kind": source_item.get("gate_kind"),
        "scorer": "sanity-gates-exact",
    }
    if loop_detected is not None:
        detail["loop_detected"] = loop_detected
    return _result(correct, detail=detail)


def _has_ngram_loop(response: str, *, ngram_size: int, max_occurrences: int) -> bool:
    tokens = _word_sequence(response.casefold())
    if len(tokens) < ngram_size:
        return False
    ngrams = Counter(tuple(tokens[index : index + ngram_size]) for index in range(len(tokens) - ngram_size + 1))
    return any(count > max_occurrences for count in ngrams.values())


def _word_sequence(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", text, flags=re.UNICODE))


def _result(correct: bool, *, chance: float = 0.0, detail: JsonObject) -> JsonObject:
    raw = 1.0 if correct else 0.0
    return {
        "chance_corrected": signed_score(raw, chance=chance),
        "correct": correct,
        "detail": detail,
        "raw_score": raw,
    }


def _object_list(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
