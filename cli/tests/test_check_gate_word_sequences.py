from __future__ import annotations

from localbench._types import JsonObject
from localbench.check.grading import grade_response


def _grade(source: JsonObject, text: str) -> JsonObject:
    return grade_response(
        "sanity-gates",
        source,
        {"finish_reason": "stop", "text": text},
    )


def test_repetition_compares_case_preserving_words_without_punctuation() -> None:
    # Given the authored repetition answer and its Unicode word-token contract.
    source: JsonObject = {
        "category": "repetition",
        "gate_kind": "behavioral",
        "expected": {
            "answer": "LIME COBALT AMBER DONE",
            "loop_detection": {
                "max_occurrences": 1,
                "ngram_size": 2,
                "tokenization": "unicode-word-punctuation-v1",
            },
            "stop_marker": "DONE",
        },
    }

    # When punctuation varies but words and case match the expected sequence.
    observed = _grade(source, "LIME, COBALT, AMBER DONE;")
    missing = _grade(source, "LIME, COBALT DONE;")
    wrong_case = _grade(source, "Lime, COBALT, AMBER DONE;")

    # Then only the complete case-preserving word sequence passes.
    assert observed["correct"] is True
    assert missing["correct"] is False
    assert wrong_case["correct"] is False


def test_template_canary_compares_the_complete_word_sequence() -> None:
    # Given a template canary whose authored punctuation is not semantic.
    source: JsonObject = {
        "category": "template-canary",
        "gate_kind": "validity",
        "expected": {"answer": "CANARY-Q3", "template_role": "assistant"},
    }

    # When punctuation differs or a required word is missing.
    punctuation_variant = _grade(source, "CANARY, Q3;")
    missing = _grade(source, "CANARY;")
    decorated = _grade(source, "result CANARY-Q3")

    # Then punctuation is ignored while missing or extra words remain true misses.
    assert punctuation_variant["correct"] is True
    assert missing["correct"] is False
    assert decorated["correct"] is False


def test_stop_token_uses_word_sequence_for_required_marker_and_forbidden_suffix() -> None:
    # Given a stop-token gate with a continuation trap after the required sequence.
    source: JsonObject = {
        "category": "stop-token",
        "gate_kind": "validity",
        "expected": {
            "forbidden_suffix": "926",
            "required": "31415",
            "stop_marker": "<STOP>",
        },
    }

    # When punctuation varies or required stop semantics are violated.
    punctuation_variant = _grade(source, "31415, <STOP>;")
    missing_required = _grade(source, "<STOP>")
    missing_marker = _grade(source, "31415")
    forbidden_after_required = _grade(source, "31415 926 <STOP>")
    wrong_case_marker = _grade(source, "31415 <stop>")

    # Then only the required sequence ending in the exact-case marker passes.
    assert punctuation_variant["correct"] is True
    assert missing_required["correct"] is False
    assert missing_marker["correct"] is False
    assert forbidden_after_required["correct"] is False
    assert wrong_case_marker["correct"] is False


def test_long_context_needle_keeps_substring_comparison() -> None:
    # Given a needle gate whose surrounding recovery prose remains allowed.
    source: JsonObject = {
        "category": "long-context-needle",
        "gate_kind": "behavioral",
        "expected": {"answer": "BRISBANE-8192"},
    }

    # When the answer occurs inside additional text.
    result = _grade(source, "Recovered BRISBANE-8192 from the window.")

    # Then the existing needle comparison still passes.
    assert result["correct"] is True
