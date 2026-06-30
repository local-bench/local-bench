from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from localbench._scoring import BenchAggregate, ScoredItem, aggregate
from localbench._types import JsonObject, JsonValue, Usage
from localbench.scoring.axis_status import AxisStatusBlock, parse_axis_status_block
from localbench.scoring.public_rescore import score_public_item
from localbench.submissions.canon import canonical_json_hash, sha256_file
from localbench.submissions.contracts import ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION
from localbench.submissions.foundation import (
    VALIDATOR_VERSION,
    normalize_result_bundle,
    validate_accepted_result_projection,
)
from localbench.submissions.foundation_scores import axis_projection, score_summary
from localbench.submissions.validate import (
    SuiteItem,
    SubmissionValidationError,
    suite_item_index,
)


def rescore_bundle(
    path: Path,
    *,
    suite_dir: Path,
    validated_at: str,
) -> JsonObject:
    bundle = normalize_result_bundle(_read_json(path), suite_dir=suite_dir)
    items = _scored_items(_items(bundle), _suite_items(bundle, suite_dir))
    benches = _bench_aggregates(items, _suite_items(bundle, suite_dir))
    axis_status = parse_axis_status_block(_object(bundle.get("axis_status")))
    projection = _projection(
        bundle=bundle,
        benches=benches,
        axis_status=axis_status,
        bundle_sha256=sha256_file(path),
        validated_at=validated_at,
    )
    projection["artifact_hashes"] = _artifact_hashes(path, projection)
    validate_accepted_result_projection(projection)
    return projection


def _projection(
    *,
    bundle: JsonObject,
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    bundle_sha256: str,
    validated_at: str,
) -> JsonObject:
    manifest = _object(bundle.get("manifest"))
    suite = _object(manifest.get("suite"))
    scorecard = _object(manifest.get("scorecard"))
    return {
        "schema_version": ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
        "model": _projection_model(bundle, manifest),
        "runtime": _object(manifest.get("runtime")),
        "suite_release_id": str(suite.get("suite_release_id")),
        "suite_manifest_sha256": str(suite.get("suite_manifest_sha256")),
        "scorecard_id": str(scorecard.get("scorecard_id")),
        "coverage_profile_id": str(suite.get("coverage_profile_id")),
        "headline_complete": bool(bundle.get("headline_complete")),
        "scores": score_summary(benches, axis_status, suite_axes=_suite_axes(manifest)),
        "axes": axis_projection(benches, axis_status),
        "conformance": _object(bundle.get("conformance")),
        "artifact_hashes": {
            "bundle_sha256": bundle_sha256,
            "projection_sha256": "",
            "public_artifact_manifest_sha256": "",
        },
        "origin": "project_anchor",
        "trust_label": "community_re_scored",
        "verification_level": "offline_rescore",
        "validator": {
            "validator_version": VALIDATOR_VERSION,
            "commit": _object(manifest.get("provenance")).get("localbench_repo_commit"),
            "validated_at": validated_at,
        },
    }


def _scored_items(
    items: list[JsonObject],
    suite_items: Mapping[tuple[str, str], SuiteItem],
) -> list[ScoredItem]:
    scored: list[ScoredItem] = []
    for item in items:
        bench = _required_string(item.get("bench"), "bench")
        item_id = _required_string(item.get("id"), "id")
        suite_item = suite_items.get((bench, item_id))
        if suite_item is None:
            raise SubmissionValidationError(f"unknown item: {bench}/{item_id}")
        detail = score_public_item(
            bench,
            suite_item.source,
            _optional_string(item.get("response_text")),
            error=_optional_string(item.get("error")),
            finish_reason=_optional_string(item.get("finish_reason")),
        )
        scored_item: ScoredItem = {
            "id": item_id,
            "bench": bench,
            "response_text": _optional_string(item.get("response_text")),
            "extracted": detail["extracted"],
            "correct": detail["correct"],
            "finish_reason": _optional_string(item.get("finish_reason")),
            "latency_seconds": _number(item.get("latency_seconds")),
            "started_at": _optional_string(item.get("started_at")) or "",
            "finished_at": _optional_string(item.get("finished_at")) or "",
            "attempts": _int(item.get("attempts")),
            "usage": _usage(item.get("usage")),
            "error": _optional_string(item.get("error")),
        }
        if "failure_kind" in detail:
            scored_item["failure_kind"] = detail["failure_kind"]
        scored.append(scored_item)
    return scored


def _bench_aggregates(
    items: list[ScoredItem],
    suite_items: Mapping[tuple[str, str], SuiteItem],
) -> dict[str, BenchAggregate]:
    baselines = _baselines(suite_items)
    return {
        bench: aggregate(bench, [item for item in items if item["bench"] == bench], baseline)
        for bench, baseline in baselines.items()
        if any(item["bench"] == bench for item in items)
    }


def _suite_items(bundle: JsonObject, suite_dir: Path) -> dict[tuple[str, str], SuiteItem]:
    suite = _object(_object(bundle.get("manifest")).get("suite"))
    payload: JsonObject = {
        "suite": {
            "item_set_hashes": _object(suite.get("item_set_hashes")),
            "tier": suite.get("tier") or bundle.get("tier") or "standard",
        },
    }
    return suite_item_index(payload, suite_dir)


def _projection_model(bundle: JsonObject, manifest: JsonObject) -> JsonObject:
    model = _object(bundle.get("model"))
    manifest_model = _object(manifest.get("model"))
    return {
        "display_name": model.get("name"),
        "file_sha256": manifest_model.get("file_sha256"),
        "file_size_bytes": manifest_model.get("file_size_bytes"),
        "file_name": manifest_model.get("file_name"),
        "family": manifest_model.get("family"),
        "quant_label": manifest_model.get("quant_label"),
        "format": manifest_model.get("format"),
        "tokenizer_digest": manifest_model.get("tokenizer_digest"),
        "chat_template_digest": manifest_model.get("chat_template_digest"),
    }


def _artifact_hashes(path: Path, projection: JsonObject) -> JsonObject:
    hashable = _projection_for_hash(projection)
    projection_sha = canonical_json_hash(hashable)
    return {
        "bundle_sha256": sha256_file(path),
        "projection_sha256": projection_sha,
        "public_artifact_manifest_sha256": canonical_json_hash(
            {"projection_sha256": projection_sha, "bundle_sha256": sha256_file(path)},
        ),
    }


def _projection_for_hash(projection: JsonObject) -> JsonObject:
    hashable = json.loads(json.dumps(projection, ensure_ascii=False))
    if not isinstance(hashable, dict):
        return {}
    artifact_hashes = _object(hashable.get("artifact_hashes"))
    artifact_hashes["projection_sha256"] = ""
    artifact_hashes["public_artifact_manifest_sha256"] = ""
    hashable["artifact_hashes"] = artifact_hashes
    return hashable


def _suite_axes(manifest: JsonObject) -> JsonObject | None:
    axes = _object(_object(manifest.get("suite")).get("axis_membership"))
    if not axes:
        return None
    return {axis: {"benches": benches} for axis, benches in axes.items()}


def _baselines(suite_items: Mapping[tuple[str, str], SuiteItem]) -> dict[str, float]:
    baselines: dict[str, float] = {}
    for suite_item in suite_items.values():
        baselines[suite_item.bench] = suite_item.baseline
    return baselines


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SubmissionValidationError("result bundle must be a JSON object")
    return data


def _items(bundle: JsonObject) -> list[JsonObject]:
    value = bundle.get("items")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _usage(value: JsonValue | None) -> Usage:
    usage = _object(value)
    return {
        "prompt_tokens": _nullable_int(usage.get("prompt_tokens")),
        "completion_tokens": _nullable_int(usage.get("completion_tokens")),
        "total_tokens": _nullable_int(usage.get("total_tokens")),
    }


def _required_string(value: JsonValue | None, label: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise SubmissionValidationError(f"{label} must be a non-empty string")


def _optional_string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _number(value: JsonValue | None) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _int(value: JsonValue | None) -> int:
    if isinstance(value, bool):
        return 1
    return value if isinstance(value, int) else 1


def _nullable_int(value: JsonValue | None) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
