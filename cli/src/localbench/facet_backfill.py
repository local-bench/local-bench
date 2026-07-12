"""Fail-closed composition of a season-2 Tool Use facet backfill campaign."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Final

from localbench._suite import read_json_object, render_benches
from localbench._types import JsonObject, JsonValue
from localbench.landing import (
    LandingError,
    _assert_rescore_coverage,
    _recompute_derived_record,
)
from localbench.orchestrate import _budget_audit
from localbench.persistence import atomic_write_json
from localbench.scoring.editorial import (
    INDEX_VERSION_V4,
    SEASON_2_COVERAGE_PROFILE_ID,
    index_version_for_coverage_profile,
)
from localbench.scoring.scorecard import scorecard_identity
from localbench.scoring.season2_rescore import rescore_record_season2
from localbench.submissions.canon import sha256_file
from localbench.suite_release import build_suite_release_manifest
from localbench.suite_verify import license_manifest, suite_hash

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
SUITE_V2_DIR: Final = REPO_ROOT / "suite" / "v2"
BACKFILL_BENCH: Final = "bfcl_multi_turn_base"


class FacetBackfillError(RuntimeError):
    """A backfill input failed an identity, integrity, or composition gate."""


def compose_facet_backfill(record_path: Path, partial_path: Path, out_path: Path) -> JsonObject:
    """Attach exactly one verified BFCL-base partial campaign to a copied record."""
    original_file = record_path.expanduser().resolve()
    partial_file, status_file = _resolve_partial(partial_path)
    output_file = out_path.expanduser().resolve()
    if output_file in {original_file, partial_file}:
        raise FacetBackfillError("--out must be a new file; input records are immutable")
    if output_file.exists():
        raise FacetBackfillError("--out must not already exist")
    original = _read_object(original_file, "original record")
    partial = _read_object(partial_file, "partial record")
    status = _read_object(status_file, "partial campaign status")

    identity = _assert_identity(original, partial)
    partial_items = _assert_partial_items(original, partial)
    completeness = _assert_complete_status(status, len(partial_items))
    original_prompt, partial_prompt = _assert_prompt_audits(original, partial)
    original_sampler, partial_sampler = _assert_sampler_audits(original, partial)

    original_hash = sha256_file(original_file)
    partial_hash = sha256_file(partial_file)
    status_hash = sha256_file(status_file)
    campaign_id = f"facet-backfill:{partial_hash}"
    attached = []
    for raw_item in partial_items:
        item = copy.deepcopy(raw_item)
        item["facet_backfill_campaign"] = {
            "campaign_id": campaign_id,
            "source_path": str(partial_file),
            "source_sha256": partial_hash,
        }
        attached.append(item)

    result = copy.deepcopy(original)
    items = _object_list(result.get("items"), "original items")
    items.extend(attached)
    result["items"] = items
    _stamp_season2_identity(result, partial)
    try:
        suite_dir = _assert_rescore_coverage(result, items)
        _recompute_derived_record(result, items, suite_dir)
    except LandingError as error:
        raise FacetBackfillError(str(error)) from error

    campaigns = {
        "original": {
            "path": str(original_file),
            "sha256": original_hash,
            "run_started_at": _required_text(original, "run_started_at"),
            "run_finished_at": _required_text(original, "run_finished_at"),
        },
        "partial": {
            "campaign_id": campaign_id,
            "path": str(partial_file),
            "sha256": partial_hash,
            "run_started_at": _required_text(partial, "run_started_at"),
            "run_finished_at": _required_text(partial, "run_finished_at"),
            "status_path": str(status_file),
            "status_sha256": status_hash,
        },
    }
    budget = _budget_audit(items)  # type: ignore[arg-type]
    budget["composition"] = "deterministic-union-of-two-campaigns"
    budget["campaigns"] = campaigns
    result["budget_audit"] = budget
    result["prompt_audit"] = {
        **original_prompt,
        "composition": "strict-equal-two-campaigns",
        "campaigns": {"original": original_prompt, "partial": partial_prompt},
    }
    result["sampler_audit"] = {
        **original_sampler,
        "composition": "strict-equal-two-campaigns",
        "campaigns": {"original": original_sampler, "partial": partial_sampler},
    }
    result["facet_backfill"] = {
        "schema_version": "localbench.facet_backfill.v1",
        "operation": "immutable-attach-strict-patch",
        "bench": BACKFILL_BENCH,
        "attached_item_count": len(attached),
        "identity": identity,
        "campaigns": campaigns,
        "partial_campaign_status": {
            "state": status["state"],
            "completed_items": status["completed_items"],
            "total_items": status["total_items"],
            "completeness_check": completeness,
        },
        "original_untouched": True,
        "timestamps_source": "input-records",
    }
    result["index_version"] = index_version_for_coverage_profile(
        SEASON_2_COVERAGE_PROFILE_ID
    )
    rescored = rescore_record_season2(result)
    if rescored.get("index_version") != INDEX_VERSION_V4:
        raise FacetBackfillError("season-2 rescore did not bind index-v4.0")
    if rescored.get("missing_headline_axes") != [] or rescored.get("composite_v4") is None:
        raise FacetBackfillError("season-2 rescore did not produce a strict complete composite")
    result["season2_rescore"] = rescored
    atomic_write_json(result, output_file)
    return result


def _assert_identity(original: JsonObject, partial: JsonObject) -> JsonObject:
    original_model = _model_identity(original, "original")
    partial_model = _model_identity(partial, "partial")
    _strict_equal("model file_sha256", original_model["file_sha256"], partial_model["file_sha256"])
    _strict_equal("model file_size_bytes", original_model["file_size_bytes"], partial_model["file_size_bytes"])

    original_profile = _profile_identity(original, "original")
    partial_profile = _profile_identity(partial, "partial")
    _strict_equal("execution profile", original_profile, partial_profile)
    original_lane = _lane_identity(original, "original")
    partial_lane = _lane_identity(partial, "partial")
    _strict_equal("lane_spec_id", original_lane, partial_lane)
    original_renderer = _manifest(original, "original").get("prompt_renderer")
    partial_renderer = _manifest(partial, "partial").get("prompt_renderer")
    if not isinstance(original_renderer, dict) or not isinstance(partial_renderer, dict):
        raise FacetBackfillError("prompt_renderer identity must be present in both campaigns")
    _strict_equal("prompt_renderer identity", original_renderer, partial_renderer)
    original_slots = _single_slot_identity(original, "original")
    partial_slots = _single_slot_identity(partial, "partial")
    _strict_equal("single-slot serving evidence", original_slots, partial_slots)
    return {
        "model": original_model,
        "execution_profile": original_profile,
        "lane_spec_id": original_lane,
        "prompt_renderer": copy.deepcopy(original_renderer),
        "single_slot_serving": original_slots,
    }


def _model_identity(record: JsonObject, label: str) -> JsonObject:
    top = _object(record.get("model"), f"{label}.model")
    manifest_model = _object(_manifest(record, label).get("model"), f"{label}.manifest.model")
    top_sha = _required_text(top, "file_sha256")
    manifest_sha = _required_text(manifest_model, "file_sha256")
    _strict_equal(f"{label} top-level/manifest model file_sha256", top_sha, manifest_sha)
    size = manifest_model.get("file_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise FacetBackfillError(f"{label}.manifest.model.file_size_bytes must be positive")
    top_size = top.get("file_size_bytes")
    if top_size is not None:
        _strict_equal(f"{label} top-level/manifest model file_size_bytes", top_size, size)
    return {"file_sha256": manifest_sha, "file_size_bytes": size}


def _profile_identity(record: JsonObject, label: str) -> JsonObject:
    manifest = _manifest(record, label)
    scorecard = _object(manifest.get("scorecard"), f"{label}.manifest.scorecard")
    execution = _object(manifest.get("execution_profile"), f"{label}.manifest.execution_profile")
    identity = {
        "id": _required_text(scorecard, "execution_profile_id"),
        "digest": _required_text(scorecard, "execution_profile_digest"),
    }
    _strict_equal(f"{label} execution profile id", execution.get("id"), identity["id"])
    _strict_equal(f"{label} execution profile digest", execution.get("digest"), identity["digest"])
    sampling = _object(manifest.get("sampling"), f"{label}.manifest.sampling")
    _strict_equal(f"{label} sampling execution profile", sampling.get("execution_profile_id"), identity["id"])
    return identity


def _lane_identity(record: JsonObject, label: str) -> str:
    manifest = _manifest(record, label)
    scorecard = _object(manifest.get("scorecard"), f"{label}.manifest.scorecard")
    lane_spec_id = _required_text(scorecard, "lane_spec_id")
    suite = _object(manifest.get("suite"), f"{label}.manifest.suite")
    _strict_equal(f"{label} suite lane", suite.get("lane"), lane_spec_id)
    return lane_spec_id


def _single_slot_identity(record: JsonObject, label: str) -> JsonObject:
    manifest = _manifest(record, label)
    runtime = _object(manifest.get("runtime"), f"{label}.manifest.runtime")
    execution = _object(manifest.get("execution"), f"{label}.manifest.execution")
    evidence = {
        "parallel_slots": runtime.get("parallel_slots"),
        "client_concurrency": execution.get("concurrency"),
    }
    if evidence != {"parallel_slots": 1, "client_concurrency": 1}:
        raise FacetBackfillError(f"{label} campaign lacks single-slot serving evidence")
    return evidence


def _assert_prompt_audits(original: JsonObject, partial: JsonObject) -> tuple[JsonObject, JsonObject]:
    first = _object(original.get("prompt_audit"), "original.prompt_audit")
    second = _object(partial.get("prompt_audit"), "partial.prompt_audit")
    if first.get("status") != "canonical" or second.get("status") != "canonical":
        raise FacetBackfillError("both prompt audits must be canonical")
    _strict_equal("prompt audit", first, second)
    return copy.deepcopy(first), copy.deepcopy(second)


def _assert_sampler_audits(original: JsonObject, partial: JsonObject) -> tuple[JsonObject, JsonObject]:
    first = _object(original.get("sampler_audit"), "original.sampler_audit")
    second = _object(partial.get("sampler_audit"), "partial.sampler_audit")
    required = ("temperature", "top_k", "seed", "determinism_policy")
    for label, audit in (("original", first), ("partial", second)):
        if audit.get("status") != "deterministic":
            raise FacetBackfillError(f"{label} sampler audit must be deterministic")
        for key in required:
            if key not in audit or audit[key] is None:
                raise FacetBackfillError(f"{label} sampler audit is missing {key}")
    _strict_equal("sampler pins", {key: first[key] for key in required}, {key: second[key] for key in required})
    for label, record, audit in (("original", original, first), ("partial", partial, second)):
        sampling = _object(_manifest(record, label).get("sampling"), f"{label}.manifest.sampling")
        for key in ("temperature", "top_k", "seed"):
            _strict_equal(f"{label} sampler {key}", sampling.get(key), audit[key])
        policy = sampling.get("determinism_policy")
        policy_id = policy.get("policy_id") if isinstance(policy, dict) else policy
        _strict_equal(f"{label} determinism policy", policy_id, audit["determinism_policy"])
    return copy.deepcopy(first), copy.deepcopy(second)


def _assert_partial_items(original: JsonObject, partial: JsonObject) -> list[JsonObject]:
    suite = read_json_object(SUITE_V2_DIR / "suite.json")
    rendered = render_benches(BACKFILL_BENCH, "standard", None, SUITE_V2_DIR, suite, [])
    expected = {str(item["id"]) for item in rendered[0].benchmark_items}
    items = _object_list(partial.get("items"), "partial items")
    observed: list[str] = []
    for item in items:
        if item.get("bench") != BACKFILL_BENCH:
            raise FacetBackfillError("partial contains an item outside bfcl_multi_turn_base")
        item_id = _required_text(item, "id")
        observed.append(item_id)
        if not isinstance(item.get("correct"), bool):
            raise FacetBackfillError(f"partial item {item_id} has no boolean verdict")
    if len(observed) != len(set(observed)):
        raise FacetBackfillError("partial contains duplicate item ids")
    if set(observed) != expected or len(observed) != len(expected):
        missing = sorted(expected - set(observed))
        wrong = sorted(set(observed) - expected)
        raise FacetBackfillError(
            f"partial must contain exactly {len(expected)} frozen {BACKFILL_BENCH} ids; "
            f"missing={missing[:3]}, wrong={wrong[:3]}"
        )
    original_keys = {
        (item.get("bench"), item.get("id"))
        for item in _object_list(original.get("items"), "original items")
    }
    duplicates = sorted(str(item_id) for item_id in observed if (BACKFILL_BENCH, item_id) in original_keys)
    if duplicates:
        raise FacetBackfillError(f"partial duplicates original item ids: {duplicates[:3]}")
    return items


def _assert_complete_status(status: JsonObject, expected: int) -> str:
    if status.get("state") != "complete":
        raise FacetBackfillError("partial campaign status must be complete")
    completed = status.get("completed_items")
    total = status.get("total_items")
    if completed != expected or total != expected:
        raise FacetBackfillError(
            f"partial campaign status must report {expected}/{expected} completed items"
        )
    return "complete-and-exact-item-count"


def _stamp_season2_identity(result: JsonObject, partial: JsonObject) -> None:
    manifest = _manifest(result, "composed")
    partial_manifest = _manifest(partial, "partial")
    suite = _object(manifest.get("suite"), "composed.manifest.suite")
    release = build_suite_release_manifest(
        SUITE_V2_DIR, coverage_profile_id=SEASON_2_COVERAGE_PROFILE_ID
    )
    suite_definition = read_json_object(SUITE_V2_DIR / "suite.json")
    suite.update(
        {
            "suite_id": release["suite_release_id"],
            "suite_version": release["suite_semver"],
            "suite_release_id": release["suite_release_id"],
            "suite_manifest_sha256": release["suite_manifest_sha256"],
            "suite_hash": suite_hash(SUITE_V2_DIR),
            "suite_hash_algorithm": release["suite_hash_algorithm"],
            "coverage_profile_id": release["coverage_profile_id"],
            "item_set_hashes": copy.deepcopy(release["item_set_hashes"]),
            "axis_membership": copy.deepcopy(release["axis_membership"]),
            "bench_membership": copy.deepcopy(release["bench_membership"]),
            "license_manifest_sha256": release["license_manifest_sha256"],
            "license_manifest": license_manifest(suite_definition, SUITE_V2_DIR),
        }
    )
    manifest["suite"] = suite
    profile = _profile_identity(result, "composed")
    lane = _lane_identity(result, "composed")
    manifest["scorecard"] = scorecard_identity(profile["id"], lane_spec_id=lane)
    sampling = _object(manifest.get("sampling"), "composed.manifest.sampling")
    partial_sampling = _object(partial_manifest.get("sampling"), "partial.manifest.sampling")
    by_bench = _object(sampling.get("by_bench"), "composed.manifest.sampling.by_bench")
    partial_by_bench = _object(partial_sampling.get("by_bench"), "partial.manifest.sampling.by_bench")
    by_bench[BACKFILL_BENCH] = copy.deepcopy(
        _object(partial_by_bench.get(BACKFILL_BENCH), f"partial sampling for {BACKFILL_BENCH}")
    )
    sampling["by_bench"] = by_bench
    manifest["sampling"] = sampling
    result["manifest"] = manifest


def _resolve_partial(raw: Path) -> tuple[Path, Path]:
    resolved = raw.expanduser().resolve()
    if resolved.is_dir():
        run_file = resolved / "localbench-run.json"
        status_file = resolved / "run.status.json"
    else:
        run_file = resolved
        status_file = resolved.parent / "run.status.json"
    if not run_file.is_file():
        raise FacetBackfillError(f"partial run JSON not found: {run_file}")
    if not status_file.is_file():
        raise FacetBackfillError(f"partial campaign status not found: {status_file}")
    return run_file, status_file


def _read_object(path: Path, label: str) -> JsonObject:
    if not path.is_file():
        raise FacetBackfillError(f"{label} not found: {path}")
    try:
        value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FacetBackfillError(f"cannot read {label}: {path}") from error
    return _object(value, label)


def _manifest(record: JsonObject, label: str) -> JsonObject:
    return _object(record.get("manifest"), f"{label}.manifest")


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise FacetBackfillError(f"{label} must be an object")
    return value


def _object_list(value: JsonValue | None, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise FacetBackfillError(f"{label} must be an array of objects")
    return list(value)


def _required_text(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise FacetBackfillError(f"{key} must be a non-empty string")
    return item


def _strict_equal(label: str, first: JsonValue | None, second: JsonValue | None) -> None:
    if first != second:
        raise FacetBackfillError(f"{label} mismatch between original and partial campaigns")
