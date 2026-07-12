from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import assert_never

from localbench._scoring import BenchAggregate, ScoredItem, aggregate
from localbench._suite import read_json_object
from localbench._types import JsonObject, JsonValue, Usage
from localbench.scoring.axis_status import AxisStatusBlock, parse_axis_status_block
from localbench.scoring.editorial import index_version_for_coverage_profile
from localbench.scoring.public_rescore import score_public_item
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.canon import canonical_json_bytes, canonical_json_hash, sha256_bytes, sha256_file
from localbench.submissions.contracts import ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION
from localbench.submissions.foundation import (
    VALIDATOR_VERSION,
    normalize_result_bundle,
    validate_accepted_result_projection,
)
from localbench.submissions.foundation_scores import axis_projection, score_summary
from localbench.submissions.origin import SubmissionOrigin
from localbench.submissions.provenance import (
    AgenticProvenanceResult,
    CarriedVerdict,
    carried_from_result_items,
    evaluate_agentic_provenance,
)
from localbench.submissions.validate import (
    SuiteItem,
    SubmissionValidationError,
    suite_item_index,
)

GRANDFATHERED_ATTESTED_BUNDLE_SHA256S = frozenset(
    {
        # ticket_790a73b6: validator-v1 ranked Gemma row from the pre-attestation direct-finalize path.
        "f815ebbb78516cbdd27b379a87c9fc34fd172692ee4e4e2ce047c5c02c846f85",
    },
)


def canonical_projection_bytes(projection: JsonObject) -> bytes:
    """Exact immutable object bytes (no trailing newline)."""
    validate_accepted_result_projection(projection)
    return canonical_json_bytes(projection)


def projection_object_sha256(projection: JsonObject) -> str:
    """Content address of the exact canonical bytes stored in object storage."""
    return sha256_bytes(canonical_json_bytes(projection))


def rescore_bundle(
    path: Path,
    *,
    suite_dir: Path,
    validated_at: str,
    origin: SubmissionOrigin = "project_anchor",
) -> JsonObject:
    loaded = load_result_bundle_input(path)
    bundle_sha256 = sha256_file(path)
    bundle = normalize_result_bundle(loaded.record, suite_dir=suite_dir)
    _restore_declared_suite_pair(bundle, loaded.record)
    suite_items = _suite_items(bundle, suite_dir)
    dynamic_benches = _dynamic_benches(suite_dir, suite_items)
    items = _scored_items(_items(bundle), suite_items, dynamic_benches)
    benches = _bench_aggregates(items, suite_items, dynamic_benches)
    axis_status = parse_axis_status_block(_object(bundle.get("axis_status")))
    provenance = _agentic_provenance(
        origin,
        carried_from_result_items(_items(bundle), dynamic_benches),
        loaded.attestations,
        bundle_sha256,
    )
    projection = _projection(
        bundle=bundle,
        benches=benches,
        axis_status=axis_status,
        bundle_sha256=bundle_sha256,
        validated_at=validated_at,
        rescore_modes={
            bench: ("verdict_carried" if bench in dynamic_benches else "rescored")
            for bench in sorted(benches)
        },
        origin=origin,
        provenance=provenance,
    )
    projection["artifact_hashes"] = _artifact_hashes(path, projection)
    if _object(_object(bundle.get("manifest")).get("integrity")).get("publishable") is True:
        validate_accepted_result_projection(projection)
    return projection


def _restore_declared_suite_pair(bundle: JsonObject, source: JsonObject) -> None:
    declared = _object(_object(source.get("manifest")).get("suite"))
    release_id = declared.get("suite_release_id")
    manifest_sha256 = declared.get("suite_manifest_sha256")
    if not isinstance(release_id, str) or not isinstance(manifest_sha256, str):
        return
    manifest = _object(bundle.get("manifest"))
    suite = _object(manifest.get("suite"))
    suite["suite_release_id"] = release_id
    suite["suite_manifest_sha256"] = manifest_sha256
    manifest["suite"] = suite
    bundle["manifest"] = manifest


def _dynamic_benches(
    suite_dir: Path,
    suite_items: Mapping[tuple[str, str], SuiteItem],
) -> frozenset[str]:
    """Headline-axis benches that ship NO static item set (e.g. ``appworld_c``).

    These cannot be re-scored from suite sources — an agentic verdict needs the live
    AppWorld evaluator, so the projection CARRIES the bundle's per-item verdicts instead
    (``rescore_modes: verdict_carried``; integrity rests on the run-level agentic
    verdict-channel provenance). Derived ONLY from the suite dir's scorecard registry
    (trusted, site-released): a bundle cannot invent a verdict-carried bench, and
    candidate-axis benches (weight 0) stay ineligible so absent axes can't be smuggled
    in as unscoreable items.
    """
    scorecard_path = suite_dir / "SCORECARD.json"
    if not scorecard_path.exists():
        # Older/dev suites ship no scorecard registry -> no verdict-carried eligibility,
        # i.e. exactly the strict pre-dynamic behavior (every item needs a static source).
        return frozenset()
    scorecard = read_json_object(scorecard_path)
    registry = scorecard.get("registry")
    static_benches = {bench for bench, _item_id in suite_items}
    dynamic: set[str] = set()
    if isinstance(registry, list):
        for entry in registry:
            if not isinstance(entry, dict) or entry.get("role") != "headline":
                continue
            benches = entry.get("benches")
            if not isinstance(benches, list):
                continue
            dynamic.update(
                bench
                for bench in benches
                if isinstance(bench, str) and bench not in static_benches
            )
    return frozenset(dynamic)


def _agentic_provenance(
    origin: SubmissionOrigin,
    carried: list[CarriedVerdict],
    attestations: list[JsonObject],
    bundle_sha256: str,
) -> AgenticProvenanceResult:
    result = evaluate_agentic_provenance(
        carried,
        attestations,
        bundle_sha256=bundle_sha256,
        grandfathered_bundle_sha256s=GRANDFATHERED_ATTESTED_BUNDLE_SHA256S,
    )
    if origin == "community" and result.label == "project_attested":
        return AgenticProvenanceResult("self_reported", ("community_origin",))
    return result


def _trust_label(origin: SubmissionOrigin) -> str:
    match origin:
        case "project_anchor":
            return "project_anchor"
        case "community":
            return "community_self_submitted"
        case unreachable:
            assert_never(unreachable)


def _projection(
    *,
    bundle: JsonObject,
    benches: Mapping[str, BenchAggregate],
    axis_status: AxisStatusBlock,
    bundle_sha256: str,
    validated_at: str,
    rescore_modes: Mapping[str, str],
    origin: SubmissionOrigin,
    provenance: AgenticProvenanceResult,
) -> JsonObject:
    manifest = _object(bundle.get("manifest"))
    suite = _object(manifest.get("suite"))
    scorecard = _object(manifest.get("scorecard"))
    coverage_profile_id = str(suite.get("coverage_profile_id"))
    index_version = index_version_for_coverage_profile(coverage_profile_id)
    carried_index_version = bundle.get("index_version")
    if carried_index_version is not None and carried_index_version != index_version:
        raise ValueError(
            "result bundle index_version does not match its coverage_profile_id: "
            f"{carried_index_version!r} != {index_version!r}",
        )
    projection: JsonObject = {
        "schema_version": ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
        "model": _projection_model(bundle, manifest, origin, bundle_sha256),
        "lineage": _projection_lineage(manifest),
        "runtime": _object(manifest.get("runtime")),
        "suite_release_id": str(suite.get("suite_release_id")),
        "suite_manifest_sha256": str(suite.get("suite_manifest_sha256")),
        "scorecard_id": str(scorecard.get("scorecard_id")),
        "coverage_profile_id": coverage_profile_id,
        "index_version": index_version,
        "headline_complete": bool(bundle.get("headline_complete")),
        "scores": score_summary(benches, axis_status, suite_axes=_suite_axes(manifest)),
        "axes": axis_projection(benches, axis_status),
        "conformance": _object(bundle.get("conformance")),
        "receipt_references": _receipt_references(bundle),
        "artifact_hashes": {
            "bundle_sha256": bundle_sha256,
            "projection_sha256": "",
            "public_artifact_manifest_sha256": "",
        },
        "origin": origin,
        "trust_label": _trust_label(origin),
        "verification_level": "bundle_rescored",
        "agentic_provenance": provenance.label,
        # Per-bench honesty marker: "rescored" = recomputed from suite sources here;
        # "verdict_carried" = the bundle's own verdicts (dynamic bench, no static source).
        "rescore_modes": dict(rescore_modes),
        "validator": {
            "validator_version": VALIDATOR_VERSION,
            "commit": _object(manifest.get("provenance")).get("localbench_repo_commit"),
            "validated_at": validated_at,
        },
    }
    if provenance.notes:
        projection["provenance_notes"] = list(provenance.notes)
    return projection


def _scored_items(
    items: list[JsonObject],
    suite_items: Mapping[tuple[str, str], SuiteItem],
    dynamic_benches: frozenset[str] = frozenset(),
) -> list[ScoredItem]:
    scored: list[ScoredItem] = []
    seen_dynamic: set[tuple[str, str]] = set()
    for item in items:
        bench = _required_string(item.get("bench"), "bench")
        item_id = _required_string(item.get("id"), "id")
        suite_item = suite_items.get((bench, item_id))
        if suite_item is None:
            if bench not in dynamic_benches:
                raise SubmissionValidationError(f"unknown item: {bench}/{item_id}")
            key = (bench, item_id)
            if key in seen_dynamic:
                # A carried verdict repeated N times would inflate the axis unchecked.
                raise SubmissionValidationError(f"duplicate item: {bench}/{item_id}")
            seen_dynamic.add(key)
            scored.append(_verdict_carried_item(item, bench, item_id))
            continue
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


def _verdict_carried_item(item: JsonObject, bench: str, item_id: str) -> ScoredItem:
    """Carry a dynamic-bench verdict from the bundle verbatim (nothing to re-score).

    ``correct`` is the bundle's own outcome; its integrity rests on the run-level
    agentic verdict-channel provenance rather than local re-scoring. (Independent
    attestation of carried verdicts is the pre-open-submissions hardening scope.)
    """
    return {
        "id": item_id,
        "bench": bench,
        "response_text": _optional_string(item.get("response_text")),
        "extracted": _optional_string(item.get("extracted")),
        "correct": bool(item.get("correct")),
        "finish_reason": _optional_string(item.get("finish_reason")),
        "latency_seconds": _number(item.get("latency_seconds")),
        "started_at": _optional_string(item.get("started_at")) or "",
        "finished_at": _optional_string(item.get("finished_at")) or "",
        "attempts": _int(item.get("attempts")),
        "usage": _usage(item.get("usage")),
        "error": _optional_string(item.get("error")),
    }


def _bench_aggregates(
    items: list[ScoredItem],
    suite_items: Mapping[tuple[str, str], SuiteItem],
    dynamic_benches: frozenset[str] = frozenset(),
) -> dict[str, BenchAggregate]:
    baselines = _baselines(suite_items)
    for bench in dynamic_benches:
        # Verdict benches have no guess-rate to correct for: raw == chance_corrected.
        baselines.setdefault(bench, 0.0)
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


def _projection_model(
    bundle: JsonObject,
    manifest: JsonObject,
    origin: SubmissionOrigin,
    bundle_sha256: str,
) -> JsonObject:
    model = _object(bundle.get("model"))
    manifest_model = _object(manifest.get("model"))
    artifact_sha256 = manifest_model.get("file_sha256")
    return {
        "display_name": model.get("name"),
        "declared_name": model.get("name") or manifest_model.get("family"),
        "file_sha256": artifact_sha256,
        "file_size_bytes": manifest_model.get("file_size_bytes"),
        "file_name": manifest_model.get("file_name"),
        "family": manifest_model.get("family"),
        "quant_label": manifest_model.get("quant_label"),
        "format": manifest_model.get("format"),
        "tokenizer_digest": manifest_model.get("tokenizer_digest"),
        "chat_template_digest": manifest_model.get("chat_template_digest"),
        "identity_status": "unverified" if origin == "community" else "maintainer_verified",
        "model_system_key": (
            f"artifact:{artifact_sha256}"
            if isinstance(artifact_sha256, str)
            else f"legacy-project-anchor:{bundle_sha256}"
        ),
    }


def _projection_lineage(manifest: JsonObject) -> JsonObject:
    model = _object(manifest.get("model"))
    base_model = model.get("base_model")
    if isinstance(base_model, str):
        values = [base_model]
    elif isinstance(base_model, list):
        values = [value for value in base_model if isinstance(value, str)]
    else:
        values = []
    return {"base_model": values}


def _receipt_references(bundle: JsonObject) -> JsonObject:
    receipts = _object(bundle.get("receipt_references"))
    coding = receipts.get("coding_receipt_sha256")
    return {"coding_receipt_sha256": coding if isinstance(coding, str) else None}


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
