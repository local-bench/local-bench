from __future__ import annotations

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
        value
        for record in definition_objects
        if record["category"] == "long-context-needle"
        for value in [record.get("target_tokens")]
        if isinstance(value, int)
    ]
    assert needles == [8192, 16384, 24576]


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
