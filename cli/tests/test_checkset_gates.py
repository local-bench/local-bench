from __future__ import annotations

import hashlib
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from localbench.checkset.gates import build_sanity_gates, determinism_canary_matches
from localbench.checkset.models import JsonObject, JsonValue


def test_authored_sanity_gates_match_the_locked_eighteen_item_taxonomy() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    module, metadata = build_sanity_gates(repo_root)

    definitions = metadata["definitions"]
    assert isinstance(definitions, list)
    definition_objects = [record for record in definitions if isinstance(record, dict)]
    assert len(definition_objects) == 18
    assert module.scored == 18
    assert len(module.items) == 18
    assert Counter(record["category"] for record in definition_objects) == {
        "stop-token": 3,
        "budget-control": 3,
        "template-canary": 3,
        "repetition": 3,
        "long-context-needle": 3,
        "determinism": 3,
    }
    needles = [
        (nominal, words, bound)
        for record in definition_objects
        if record["category"] == "long-context-needle"
        for nominal, words, bound in [
            (
                record.get("nominal_target_tokens"),
                record.get("pinned_word_count"),
                record.get("construction_tokens_per_word_bound"),
            )
        ]
    ]
    assert needles == [
        (8192, 5649, 1.45),
        (16384, 11299, 1.45),
        (24576, 16948, 1.45),
    ]


def test_long_context_needles_are_embedded_at_recorded_mid_context_depth() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _, metadata = build_sanity_gates(repo_root)
    definitions = metadata["definitions"]
    assert isinstance(definitions, list)
    needles = [
        record
        for record in definitions
        if isinstance(record, dict) and record.get("category") == "long-context-needle"
    ]

    for record in needles:
        prompt = record["prompt"]
        expected = record["expected"]
        embedding = record["needle_embedding"]
        assert isinstance(prompt, str) and isinstance(expected, dict) and isinstance(embedding, dict)
        context = prompt.split("<context>\n", maxsplit=1)[1].split("\n</context>", maxsplit=1)[0]
        context_words = context.split()
        needle_index = embedding["needle_word_index"]
        window_words = embedding["window_words"]
        depth_ratio = embedding["depth_ratio"]
        assert embedding["algorithm"] == "sha256-wordbank-padding-v1"
        assert isinstance(needle_index, int) and isinstance(window_words, int)
        assert isinstance(depth_ratio, float) and 0.4 <= depth_ratio <= 0.6
        assert len(context_words) == window_words == record["pinned_word_count"]
        assert context_words[needle_index] == f"NEEDLE={expected['answer']}"
        assert context_words.count(f"NEEDLE={expected['answer']}") == 1
        assert needle_index < len(context_words) - 1
        assert hashlib.sha256(context.encode("utf-8")).hexdigest() == embedding["window_sha256"]


def test_repetition_gates_pin_loop_detection_and_required_stop_contracts() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _, metadata = build_sanity_gates(repo_root)
    definitions = metadata["definitions"]
    assert isinstance(definitions, list)
    repetition = [
        record
        for record in definitions
        if isinstance(record, dict) and record.get("category") == "repetition"
    ]

    assert len(repetition) == 3
    for record in repetition:
        expected = record["expected"]
        assert isinstance(expected, dict)
        assert isinstance(expected["answer"], str)
        assert isinstance(expected["stop_marker"], str)
        assert expected["loop_detection"] in (
            {"max_occurrences": 2, "ngram_size": 2, "tokenization": "unicode-word-punctuation-v1"},
            {"max_occurrences": 1, "ngram_size": 2, "tokenization": "unicode-word-punctuation-v1"},
        )


def test_determinism_canary_requires_independent_restarts_and_exact_outputs() -> None:
    first: JsonObject = {
        "server_start_id": "start-a",
        "token_ids": [1, 7, 9],
        "finish_reason": "stop",
        "parsed_tool_calls": [{"name": "lookup", "arguments": {"id": "x"}}],
        "scorer_result": {"correct": True, "score": 1},
    }
    second: JsonObject = deepcopy(first)
    second["server_start_id"] = "start-b"

    assert determinism_canary_matches(first, second) is True

    replacements: tuple[tuple[str, JsonValue], ...] = (
        ("token_ids", [1, 7, 8]),
        ("finish_reason", "length"),
        ("parsed_tool_calls", []),
        ("scorer_result", {"correct": False, "score": 0}),
    )
    for field, replacement in replacements:
        changed = deepcopy(second)
        changed[field] = replacement
        assert determinism_canary_matches(first, changed) is False


@pytest.mark.parametrize("start_id", ("start-a", ""))
def test_determinism_canary_rejects_same_or_missing_restart_identity(start_id: str) -> None:
    record: JsonObject = {
        "server_start_id": "start-a",
        "token_ids": [1],
        "finish_reason": "stop",
        "parsed_tool_calls": [],
        "scorer_result": {"correct": True},
    }
    second: JsonObject = {**record, "server_start_id": start_id}

    assert determinism_canary_matches(record, second) is False
