from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Final

from localbench.checkset.input_runs import read_json
from localbench.checkset.models import (
    ChecksetBuildError,
    ItemRecord,
    JsonObject,
    JsonValue,
    ModuleRecord,
)
from localbench.checkset.select import SELECTION_SEED
from localbench.submissions.canon import canonical_json_bytes

GATE_COUNTS = {
    "stop-token": 3,
    "budget-control": 3,
    "template-canary": 3,
    "repetition": 3,
    "long-context-needle": 3,
    "determinism": 3,
}
DETERMINISM_FIELDS = ("token_ids", "finish_reason", "parsed_tool_calls", "scorer_result")
PADDING_ALGORITHM: Final = "sha256-wordbank-padding-v1"
CONSTRUCTION_TOKENS_PER_WORD_BOUND: Final = 1.45
PADDING_WORDS: Final = (
    "acacia",
    "amber",
    "banyan",
    "breeze",
    "canyon",
    "cedar",
    "coral",
    "dawn",
    "delta",
    "dune",
    "ember",
    "fern",
    "flint",
    "grove",
    "harbor",
    "heath",
    "iris",
    "island",
    "jade",
    "kelp",
    "lagoon",
    "linen",
    "maple",
    "meadow",
    "mist",
    "myrtle",
    "oasis",
    "ochre",
    "olive",
    "orchid",
    "pebble",
    "pine",
    "quartz",
    "reed",
    "ridge",
    "river",
    "sand",
    "shore",
    "spruce",
    "stone",
    "tide",
    "vale",
    "willow",
    "wren",
)


def build_sanity_gates(repo_root: Path) -> tuple[ModuleRecord, JsonObject]:
    source_path = repo_root / "checkset" / "sanity-gates.json"
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    document = read_json(source_path)
    if document.get("schema_version") != "localbench-sanity-gates-v1":
        raise ChecksetBuildError("Unsupported sanity-gate schema.")
    raw = document.get("gates")
    if not isinstance(raw, list) or not all(isinstance(record, dict) for record in raw):
        raise ChecksetBuildError("Sanity-gate source must contain object definitions.")
    definitions = [_with_digest(_materialize_gate(record)) for record in raw if isinstance(record, dict)]
    definition_values: list[JsonValue] = [record for record in definitions]
    counts = Counter(record.get("category") for record in definitions)
    if counts != Counter(GATE_COUNTS):
        raise ChecksetBuildError("Sanity-gate source does not match the locked 18-item taxonomy.")
    module = ModuleRecord(
        name="sanity-gates",
        scored=18,
        items=tuple(
            ItemRecord(
                _required_str(record, "item_id"),
                _required_str(record, "content_sha256"),
                "gates",
            )
            for record in definitions
        ),
        source={"dataset": "checkset/sanity-gates.json", "revision": source_sha256, "split": "authored"},
        scorer={"name": "sanity-gates-exact", "version": "localbench-v1"},
        selection={"algorithm": "complete-authored-gate-set-v1", "inputs_sha256": source_sha256, "seed": SELECTION_SEED},
    )
    metadata: JsonObject = {
        "definitions": definition_values,
        "determinism_contract": {
            "comparison_fields": list(DETERMINISM_FIELDS),
            "independent_server_restarts": True,
            "tolerance": 0,
        },
        "source_sha256": source_sha256,
        "status": "ready",
    }
    return module, metadata


def determinism_canary_matches(first: JsonObject, second: JsonObject) -> bool:
    first_start = first.get("server_start_id")
    second_start = second.get("server_start_id")
    if not isinstance(first_start, str) or not first_start or not isinstance(second_start, str) or not second_start:
        return False
    if first_start == second_start:
        return False
    return all(first.get(field) == second.get(field) for field in DETERMINISM_FIELDS)


def _materialize_gate(source: JsonObject) -> JsonObject:
    is_needle = source.get("category") == "long-context-needle"
    is_long_determinism = (
        source.get("category") == "determinism"
        and source.get("canary_class") == "long-context"
    )
    if not is_needle and not is_long_determinism:
        return dict(source)
    item_id = _required_str(source, "item_id")
    prompt = _required_str(source, "prompt")
    embedded_value = _required_str(source, "needle" if is_needle else "checksum")
    nominal_target_tokens = source.get("nominal_target_tokens")
    pinned_word_count = source.get("pinned_word_count")
    tokens_per_word_bound = source.get("construction_tokens_per_word_bound")
    padding = source.get("padding")
    expected = source.get("expected")
    if not isinstance(nominal_target_tokens, int) or nominal_target_tokens < 3:
        raise ChecksetBuildError("Long-context nominal_target_tokens must be an integer of at least three.")
    if tokens_per_word_bound != CONSTRUCTION_TOKENS_PER_WORD_BOUND:
        raise ChecksetBuildError("Long-context construction tokens-per-word bound must be pinned to 1.45.")
    expected_word_count = nominal_target_tokens * 100 // 145
    if not isinstance(pinned_word_count, int) or pinned_word_count != expected_word_count:
        raise ChecksetBuildError("Long-context pinned_word_count must equal floor(nominal_target_tokens / 1.45).")
    if not isinstance(padding, dict) or not isinstance(expected, dict):
        raise ChecksetBuildError("Long-context gates require padding and expected objects.")
    algorithm = padding.get("algorithm")
    seed = padding.get("seed")
    depth_ppm = padding.get("depth_ppm")
    if algorithm != PADDING_ALGORITHM or not isinstance(seed, int):
        raise ChecksetBuildError("Long-context padding algorithm and seed must be pinned.")
    if not isinstance(depth_ppm, int) or not 0 < depth_ppm < 1_000_000:
        raise ChecksetBuildError("Long-context padding depth_ppm must be between zero and one million.")
    if expected.get("answer") != embedded_value:
        raise ChecksetBuildError("Long-context expected answer must equal its embedded value.")
    embedding_index = pinned_word_count * depth_ppm // 1_000_000
    if embedding_index <= 0 or embedding_index >= pinned_word_count - 1:
        raise ChecksetBuildError("Long-context value must have non-empty prefix and suffix padding.")
    words = [_padding_word(seed, item_id, index) for index in range(pinned_word_count)]
    words[embedding_index] = f"{'NEEDLE' if is_needle else 'CHECKSUM'}={embedded_value}"
    context = " ".join(words)
    record = dict(source)
    record["prompt"] = f"{prompt}\n<context>\n{context}\n</context>"
    embedding: JsonObject = {
        "algorithm": PADDING_ALGORITHM,
        "depth_ratio": round(embedding_index / (pinned_word_count - 1), 6),
        "prefix_words": embedding_index,
        "suffix_words": pinned_word_count - embedding_index - 1,
        "window_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
        "window_words": pinned_word_count,
    }
    embedding["needle_word_index" if is_needle else "checksum_word_index"] = embedding_index
    record["needle_embedding" if is_needle else "checksum_embedding"] = embedding
    return record


def _padding_word(seed: int, item_id: str, index: int) -> str:
    digest = hashlib.sha256(f"{seed}:{item_id}:{index}".encode()).digest()
    return PADDING_WORDS[int.from_bytes(digest[:2], "big") % len(PADDING_WORDS)]


def _with_digest(source: JsonObject) -> JsonObject:
    record = dict(source)
    record["content_sha256"] = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return record


def _required_str(row: JsonObject, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ChecksetBuildError(f"Sanity-gate field {key!r} must be a non-empty string.")
    return value
