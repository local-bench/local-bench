from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from localbench._types import JsonObject
from localbench.check.live_runner import LiveItem, select_fit_preflight_items
from localbench.check.smoke import write_smoke_record
from localbench.checkset.gates import build_sanity_gates
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file, write_json_file


def _definitions() -> dict[str, JsonObject]:
    repo_root = Path(__file__).resolve().parents[2]
    _, metadata = build_sanity_gates(repo_root)
    definitions = metadata["definitions"]
    assert isinstance(definitions, list)
    return {
        item_id: cast(JsonObject, record)
        for record in definitions
        if isinstance(record, dict)
        for item_id in [record.get("item_id")]
        if isinstance(item_id, str)
    }


def test_stop_token_three_names_its_marker() -> None:
    # Given the materialized authored gate set.
    definitions = _definitions()

    # When the third stop-token gate is inspected.
    gate = definitions["gate-stop-token-03"]

    # Then its prompt names the exact marker while the continuation trap stays pinned.
    assert gate["prompt"] == "Emit 31415 then stop at <STOP>."
    assert gate["expected"] == {
        "forbidden_suffix": "926",
        "required": "31415",
        "stop_marker": "<STOP>",
    }


def test_determinism_long_materializes_a_pinned_near_end_checksum_window() -> None:
    # Given the materialized long-context determinism canary.
    gate = _definitions()["gate-determinism-long"]

    # When its generated context and embedding record are audited.
    prompt = gate["prompt"]
    embedding = gate["checksum_embedding"]
    assert isinstance(prompt, str) and isinstance(embedding, dict)
    context = prompt.split("<context>\n", maxsplit=1)[1].split("\n</context>", maxsplit=1)[0]
    words = context.split()
    checksum_index = embedding["checksum_word_index"]

    # Then construction fields, checksum position, uniqueness, and digest are exact.
    assert gate["nominal_target_tokens"] == 24576
    assert gate["pinned_word_count"] == 16948
    assert gate["construction_tokens_per_word_bound"] == 1.45
    assert embedding["algorithm"] == "sha256-wordbank-padding-v1"
    padding = gate["padding"]
    assert isinstance(padding, dict)
    assert padding["depth_ppm"] == 950000
    assert isinstance(checksum_index, int)
    assert checksum_index == 16100
    assert embedding["prefix_words"] == checksum_index
    assert embedding["suffix_words"] == 847
    assert embedding["window_words"] == len(words) == 16948
    assert words[checksum_index] == "CHECKSUM=D3T-24576"
    assert words.count("CHECKSUM=D3T-24576") == 1
    assert hashlib.sha256(context.encode()).hexdigest() == embedding["window_sha256"]


def test_fit_preflight_selects_materialized_determinism_long() -> None:
    # Given fifteen shorter prompts plus the materialized determinism-long record.
    long_gate = _definitions()["gate-determinism-long"]
    items = tuple(
        LiveItem(f"short-{index:02d}", "sanity-gates", {"prompt": "x" * (100 + index)})
        for index in range(15)
    ) + (LiveItem("gate-determinism-long", "sanity-gates", long_gate),)

    # When the fit-preflight set is ranked by resolved prompt size.
    selected = select_fit_preflight_items(items)

    # Then determinism-long is explicitly covered before generation.
    assert "gate-determinism-long" in {item.item_id for item in selected}


def test_smoke_receipt_binds_both_determinism_restart_passes(tmp_path: Path) -> None:
    # Given two auditable canary generations from independent server starts.
    first: JsonObject = {
        "finish_reason": "stop",
        "parsed_tool_calls": [],
        "scorer_result": {"correct": True},
        "server_start_id": "restart-a",
        "text": "101",
        "token_ids": [101],
    }
    repeated: JsonObject = {**first, "server_start_id": "restart-b"}
    item: JsonObject = {
        "candidate": first,
        "candidate_repeat": repeated,
        "generation_parameters": {},
        "item_id": "gate-determinism-short",
        "module": "sanity-gates",
        "source_item": {
            "category": "determinism",
            "expected": {"answer": "101"},
            "gate_kind": "validity",
        },
    }
    write_json_file(tmp_path / "plan.lock.json", {"plan": "test"})

    # When the smoke record and receipt are written.
    _ = write_smoke_record(
        tmp_path,
        artifact={},
        execution={"server_starts": [{"server_start_id": "restart-a"}, {"server_start_id": "restart-b"}]},
        items=[item],
        manifest_edition="check-set-v1",
        manifest_sha256="a" * 64,
        resumed=False,
    )

    # Then items.jsonl carries both comparison inputs and the receipt binds those bytes.
    persisted = cast(JsonObject, json.loads((tmp_path / "items.jsonl").read_text(encoding="utf-8")))
    assert persisted["candidate"] == first
    assert persisted["candidate_repeat"] == repeated
    receipt = read_json(tmp_path / "receipt.json")
    artifacts = receipt["artifacts"]
    assert isinstance(artifacts, dict)
    assert artifacts["items.jsonl"] == sha256_file(tmp_path / "items.jsonl")
