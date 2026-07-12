"""Maintainer-only landing automation for verified benchmark runs.

Trust boundary: ``land-run`` operates only on run records produced by the
maintainer's own harness.  Campaign and agentic evidence receive structural and
drift checks, not cryptographic authentication or anti-spoof guarantees.  The
maintainer is responsible for the authenticity of those input records.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench._scoring import aggregate, run_totals
from localbench._suite import item_hashes, read_json_object, render_benches, suite_version
from localbench.coding_exec.artifacts import ASSEMBLY_RECIPE_ID, HARNESS_REV, code_artifact_for_generation
from localbench.coding_exec.ast_gate import AST_GATE_REV
from localbench.coding_exec.extract import EXTRACTOR_REV
from localbench.coding_exec.program import SENTINEL_SCHEME_REV
from localbench.coding_exec.receipt import (
    RECEIPT_SCHEMA_VERSION,
    coding_patch_sha256,
    verify_signed_verifier_receipt,
)
from localbench.coding_exec.score import BENCH as CODING_BENCH
from localbench.lane_conformance import assess_run_conformance
from localbench.lane_spec import lane_spec_id_for_lane
from localbench.orchestrate import _budget_audit, _suite_coverage
from localbench.perf import perf_summary
from localbench.persistence import atomic_write_bytes, atomic_write_json
from localbench.reasoning_leaks import registry_leak_regexes
from localbench.reasoning_registry import execution_profile_for_id
from localbench.scoring.axis_status import axis_status_for_benches
from localbench.scoring.board import build_board
from localbench.scoring.board_support import DEFAULT_OUT_V2, DEFAULT_RUNS_DIR, REPO_ROOT, read_json, slugify, write_json
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.foundation_scores import score_summary
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_release import coverage_profile_for_id

DATA_SOURCES_PATH: Final = REPO_ROOT / "web" / "data_sources.json"
MODEL_CATALOG_PATH: Final = REPO_ROOT / "web" / "model_catalog.json"
LANDED_RUNS_DIR: Final = REPO_ROOT / "runs" / "bench" / "landed"
LAUNCH_FREEZE_PATH: Final = REPO_ROOT / "web" / "components" / "launch-freeze.ts"
BOARD_MANIFEST_PATH: Final = DEFAULT_OUT_V2.with_name("board_v2.manifest.json")
PUBLIC_DATA_PATH: Final = REPO_ROOT / "web" / "public" / "data"
SUITE_DIR: Final = REPO_ROOT / "suite" / "v1"
LANDING_LOCK_PATH: Final = REPO_ROOT / ".localbench-land.lock"
LANDING_JOURNAL_PATH: Final = REPO_ROOT / ".localbench-land-journal.json"
LANDING_BACKUPS_PATH: Final = REPO_ROOT / ".localbench-land-backups"
_PROTECTED_PUBLIC_RUNS: Final = (
    ("gemma-4-12b-it", "gemma-4-12b-it__gemma-4-12b-it-qat-ud-q2kxl-bounded-final-v2"),
)


class LandingError(RuntimeError):
    """Raised when a run cannot be landed without violating publication gates."""


@dataclass(frozen=True, slots=True)
class LandingResult:
    board_sha256: str
    canonical_path: Path
    dry_run: bool
    launch_freeze_hash: str | None
    model_label: str
    model_sha256: str
    source_added: bool


def land_run(
    run_dir: Path,
    *,
    coding_verified_path: Path | None = None,
    gguf_path: Path,
    verifier_public_key: str,
    dry_run: bool = False,
) -> LandingResult:
    """Stage, gate, and optionally apply the documented maintainer landing pipeline."""
    resolved_run_dir = run_dir.expanduser().resolve()
    if not resolved_run_dir.is_dir():
        raise LandingError(f"--run must be a run directory: {resolved_run_dir}")
    original_path = resolved_run_dir / "localbench-run.json"
    verified_path = _resolve_verified_path(resolved_run_dir, coding_verified_path)
    original = _read_object(original_path, "original run")
    verified = _read_object(verified_path, "coding-verified run")
    _assert_campaign_complete(resolved_run_dir, original)
    _assert_generations_untouched(original, verified)
    patched = _strict_coding_patch(original, verified)
    _assert_coding_verified(patched)
    _assert_agentic_verification(patched)
    receipt_hash = _assert_verifier_receipt(
        original_path,
        verified,
        patched,
        verifier_public_key=verifier_public_key,
    )
    model_sha = _hash_actual_gguf(
        gguf_path,
        claimed_sha256=_model_sha(patched),
        claimed_size_bytes=_model_size(patched),
    )
    rescored = _rescore(
        patched,
        original_path=original_path,
        verified_path=verified_path,
        verifier_receipt_sha256=receipt_hash,
    )
    catalog_entry = _catalog_entry(rescored, resolved_run_dir)
    sources = _read_sources()
    source_template = _existing_source_template(sources, _required_text(catalog_entry, "id"))
    source = _source_entry(rescored, catalog_entry, source_template, model_sha=model_sha)
    canonical_path = _canonical_path(rescored, model_sha)
    relative_canonical = canonical_path.relative_to(REPO_ROOT).as_posix()
    source["file"] = relative_canonical

    existing_source = _source_for_artifact(sources, model_sha)
    source_added = existing_source is None
    if existing_source is not None:
        existing_file = existing_source.get("file")
        if existing_file != relative_canonical:
            raise LandingError(
                f"exact GGUF {model_sha} is already curated from {existing_file}; refusing a second canonical record"
            )

    current_board = _read_object(DEFAULT_OUT_V2, "current board")
    _validate_launch_freeze()
    frozen_timestamp = _generated_at(current_board)
    with tempfile.TemporaryDirectory(prefix=".localbench-land-", dir=REPO_ROOT) as temp_name:
        temp_dir = Path(temp_name)
        staged_run = temp_dir / "canonical" / canonical_path.name
        atomic_write_json(rescored, staged_run)
        staged_sources = copy.deepcopy(sources)
        if source_added:
            staged_source = copy.deepcopy(source)
            staged_source["file"] = str(staged_run)
            staged_sources.append(staged_source)
        else:
            for item in staged_sources:
                if item.get("file") == relative_canonical:
                    item["file"] = str(staged_run)
                    break
        build_curation = temp_dir / "build-data_sources.json"
        atomic_write_json(staged_sources, build_curation)
        candidate_board = build_board(
            runs_dir=DEFAULT_RUNS_DIR,
            curation_path=build_curation,
            generated_at=frozen_timestamp,
        )
        candidate_system = _candidate_system(candidate_board, canonical_path.stem, source)
        if candidate_system.get("ranked") is not True:
            raise LandingError("the verified run still fails ranked gates; refusing to curate it")
        changed = changed_existing_ranked_rows(current_board, candidate_board)
        if changed:
            raise LandingError(
                "candidate landing would change existing ranked row(s): " + ", ".join(changed)
            )
        staged_board = temp_dir / "board_v2.json"
        write_json(staged_board, candidate_board)
        staged_site_data = temp_dir / "site-data"
        _preflight_web_build(build_curation, staged_board, staged_site_data)
        _assert_protected_public_runs_unchanged(PUBLIC_DATA_PATH, staged_site_data)
        candidate_board_sha = _sha256_file(staged_board)
        staged_final_sources = temp_dir / "data_sources.json"
        original_sources_bytes = DATA_SOURCES_PATH.read_bytes()
        atomic_write_bytes(
            _append_json_array_item(original_sources_bytes, source) if source_added else original_sources_bytes,
            staged_final_sources,
        )
        staged_manifest = temp_dir / "board_v2.manifest.json"
        atomic_write_json(
            _object(candidate_board.get("manifest"), "candidate board manifest")
            | {"board_sha256": candidate_board_sha},
            staged_manifest,
        )
        staged_freeze = temp_dir / "launch-freeze.ts"
        _write_launch_freeze(LAUNCH_FREEZE_PATH, staged_freeze, candidate_board_sha)

        if dry_run:
            return LandingResult(
                board_sha256=candidate_board_sha,
                canonical_path=canonical_path,
                dry_run=True,
                launch_freeze_hash=None,
                model_label=_required_text(source, "model_label"),
                model_sha256=model_sha,
                source_added=source_added,
            )

        _apply_staged_outputs(
            temp_dir,
            (
                (staged_run, canonical_path),
                (staged_final_sources, DATA_SOURCES_PATH),
                (staged_board, DEFAULT_OUT_V2),
                (staged_manifest, BOARD_MANIFEST_PATH),
                (staged_site_data, PUBLIC_DATA_PATH),
                (staged_freeze, LAUNCH_FREEZE_PATH),
            ),
        )
        return LandingResult(
            board_sha256=candidate_board_sha,
            canonical_path=canonical_path,
            dry_run=False,
            launch_freeze_hash=candidate_board_sha,
            model_label=_required_text(source, "model_label"),
            model_sha256=model_sha,
            source_added=source_added,
        )


def changed_existing_ranked_rows(current: JsonObject, candidate: JsonObject) -> tuple[str, ...]:
    """Return existing ranked model slugs whose complete board objects changed or disappeared."""
    before = {
        _required_text(model, "slug"): model
        for model in _object_list(current.get("models"), "current board models")
        if model.get("ranked") is True
    }
    after = {
        _required_text(model, "slug"): model
        for model in _object_list(candidate.get("models"), "candidate board models")
    }
    return tuple(sorted(slug for slug, row in before.items() if after.get(slug) != row))


def print_landing_checklist(result: LandingResult) -> None:
    marker = "WOULD" if result.dry_run else "OK"
    print("final checklist")
    print(f"[{marker}] exact GGUF identity pinned: {result.model_sha256}")
    print(f"[{marker}] coding verdicts maintainer-verified and current scorer identity stamped")
    print(f"[{marker}] canonical record: {result.canonical_path}")
    print(f"[{marker}] web/data_sources.json: {'append entry' if result.source_added else 'entry already present'}")
    print(f"[{marker}] existing ranked rows unchanged")
    print(f"[{marker}] board rebuilt; sha256={result.board_sha256}")
    print(f"[{marker}] web public data rebuilt")
    if result.launch_freeze_hash is None:
        print("[WOULD] web/components/launch-freeze.ts boardSha256 re-pinned")
    else:
        print(f"[OK] web/components/launch-freeze.ts boardSha256={result.launch_freeze_hash}")
    print("[MANUAL] deploy and live smoke were not run")


def _resolve_verified_path(run_dir: Path, raw: Path | None) -> Path:
    if raw is None:
        return run_dir / "coding-verified.json"
    expanded = raw.expanduser()
    if expanded.is_absolute():
        return expanded
    cwd_candidate = expanded.resolve()
    return cwd_candidate if cwd_candidate.exists() else (run_dir / expanded).resolve()


def _read_object(path: Path, label: str) -> JsonObject:
    if not path.is_file():
        raise LandingError(f"{label} not found: {path}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise LandingError(f"{label} must be a JSON object: {path}")
    return value


def _read_sources() -> list[JsonObject]:
    value = read_json(DATA_SOURCES_PATH)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LandingError(f"{DATA_SOURCES_PATH} must be an array of objects")
    return list(value)


def _assert_generations_untouched(original: JsonObject, verified: JsonObject) -> None:
    stable_original = {key: value for key, value in original.items() if key != "items"}
    stable_verified = {
        key: value
        for key, value in verified.items()
        if key not in {"items", "coding_verifier_receipt"}
    }
    if stable_original != stable_verified:
        changed = sorted(
            key
            for key in set(stable_original) | set(stable_verified)
            if stable_original.get(key) != stable_verified.get(key)
        )
        raise LandingError(
            "coding verification changed non-coding top-level field(s): " + ", ".join(changed)
        )
    original_items = _object_list(original.get("items"), "original items")
    verified_items = _object_list(verified.get("items"), "verified items")
    if len(original_items) != len(verified_items):
        raise LandingError("coding verification changed the item count")
    mutable = {"code_artifact", "correct", "extracted", "failure_kind"}
    mutable_artifact = {
        "verdict",
        "verdict_source",
        "image_digest",
        "conformance_status",
        "extraction_status",
        "ast_gate_rev",
        "sentinel_scheme_rev",
        "assembled_program_sha256",
    }
    for before, after in zip(original_items, verified_items, strict=True):
        identity = (before.get("bench"), before.get("id"))
        if identity != (after.get("bench"), after.get("id")):
            raise LandingError(f"coding verification changed item order/identity at {identity}")
        if before.get("bench") != "bigcodebench_hard":
            if before != after:
                raise LandingError(f"coding verification changed non-coding item {identity[1]}")
            continue
        stable_before = {key: value for key, value in before.items() if key not in mutable}
        stable_after = {key: value for key, value in after.items() if key not in mutable}
        if stable_before != stable_after:
            raise LandingError(f"coding verification changed generation data for {identity[1]}")
        before_artifact = _object(before.get("code_artifact"), f"original coding artifact {identity[1]}")
        after_artifact = _object(after.get("code_artifact"), f"verified coding artifact {identity[1]}")
        artifact_before = {key: value for key, value in before_artifact.items() if key not in mutable_artifact}
        artifact_after = {key: value for key, value in after_artifact.items() if key not in mutable_artifact}
        if artifact_before != artifact_after:
            raise LandingError(f"coding verification changed immutable artifact data for {identity[1]}")


def _strict_coding_patch(original: JsonObject, verified: JsonObject) -> JsonObject:
    """Create the landed record from the original plus an explicit coding-only patch."""
    patched = copy.deepcopy(original)
    original_items = _object_list(patched.get("items"), "original items")
    verified_items = _object_list(verified.get("items"), "verified items")
    for before, after in zip(original_items, verified_items, strict=True):
        if before.get("bench") != CODING_BENCH:
            continue
        before_artifact = _object(before.get("code_artifact"), f"original coding artifact {before.get('id')}")
        after_artifact = _object(after.get("code_artifact"), f"verified coding artifact {after.get('id')}")
        for key in (
            "verdict",
            "verdict_source",
            "image_digest",
            "conformance_status",
            "extraction_status",
            "ast_gate_rev",
            "sentinel_scheme_rev",
            "assembled_program_sha256",
        ):
            if key in after_artifact:
                before_artifact[key] = copy.deepcopy(after_artifact[key])
            else:
                before_artifact.pop(key, None)
        before["code_artifact"] = before_artifact
        for key in ("correct", "extracted", "failure_kind"):
            if key in after:
                before[key] = copy.deepcopy(after[key])
            else:
                before.pop(key, None)
    return patched


def _assert_coding_verified(run: JsonObject) -> None:
    items = [item for item in _object_list(run.get("items"), "verified items") if item.get("bench") == "bigcodebench_hard"]
    if not items:
        raise LandingError("coding-verified record has no BigCodeBench-Hard items")
    missing = [str(item.get("id")) for item in items if not _trusted_coding_disposition(item)]
    if missing:
        suffix = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        raise LandingError(f"coding verifier left untrusted dispositions: {suffix}")


def _assert_agentic_verification(run: JsonObject) -> None:
    agentic = _object(run.get("agentic_run"), "agentic_run")
    runs = _object_list(agentic.get("runs"), "agentic_run.runs")
    if len(runs) < 2:
        raise LandingError("agentic verification must contain the full two-run campaign")
    subset_hashes = {_required_text(item, "subset_hash") for item in runs}
    if len(subset_hashes) != 1:
        raise LandingError("agentic verification runs do not use the same frozen task subset")
    for index, item in enumerate(runs, start=1):
        for gate in ("infra_timeout_rate", "infra_sandbox_rate", "harness_error_rate"):
            value = item.get(gate)
            if not isinstance(value, int | float) or isinstance(value, bool) or value != 0:
                raise LandingError(f"agentic run {index} failed infrastructure gate {gate}={value!r}")


def _assert_campaign_complete(run_dir: Path, run: JsonObject) -> None:
    status = _read_object(run_dir / "run.status.json", "campaign status")
    if status.get("state") != "complete":
        raise LandingError("campaign status must be complete before landing")
    completed = status.get("completed_items")
    total = status.get("total_items")
    if (
        not isinstance(completed, int)
        or isinstance(completed, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or completed != total
    ):
        raise LandingError("campaign status must report every item complete")
    campaign = _read_object(run_dir / "campaign.json", "campaign")
    campaign_items = _object(campaign.get("items"), "campaign.items")
    if campaign_items.get("total") != total or len(_object_list(run.get("items"), "original items")) < total:
        raise LandingError("campaign completed-item count does not match the final run")
    campaign_suite = _object(campaign.get("suite"), "campaign.suite")
    run_suite = _object(_object(run.get("manifest"), "manifest").get("suite"), "manifest.suite")
    for campaign_key, run_key in (("suite_version", "suite_version"), ("suite_hash", "suite_hash")):
        campaign_value = campaign_suite.get(campaign_key)
        run_value = run_suite.get(run_key)
        if campaign_value is not None and campaign_value != run_value:
            raise LandingError(f"campaign {campaign_key} does not match the final run")


def _assert_verifier_receipt(
    original_path: Path,
    verified: JsonObject,
    patched: JsonObject,
    *,
    verifier_public_key: str,
) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", verifier_public_key) is None:
        raise LandingError("--verifier-public-key must be a 64-hex Ed25519 public key")
    receipt = _object(verified.get("coding_verifier_receipt"), "coding_verifier_receipt")
    try:
        payload = verify_signed_verifier_receipt(receipt, verifier_public_key)
    except ValueError as error:
        raise LandingError(str(error)) from error
    if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION or payload.get("complete") is not True:
        raise LandingError("coding verifier receipt is incomplete or uses an unsupported schema")
    if payload.get("source_run_sha256") != _sha256_file(original_path):
        raise LandingError("coding verifier receipt is not bound to the original run bytes")
    if payload.get("coding_patch_sha256") != coding_patch_sha256(patched):
        raise LandingError("coding verifier receipt does not cover the accepted coding patch")
    image = payload.get("image_digest")
    if not isinstance(image, str) or re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image) is None:
        raise LandingError("coding verifier receipt image must be digest-pinned")

    suite = read_json_object(SUITE_DIR / "suite.json")
    expected_hashes = item_hashes(SUITE_DIR, [f"{CODING_BENCH}.jsonl"])
    expected_constants = {
        "suite_version": suite_version(suite),
        "item_set_hashes": expected_hashes,
        "runner_sha256": HARNESS_REV,
        "artifact_harness_rev": HARNESS_REV,
        "assembly_recipe_id": ASSEMBLY_RECIPE_ID,
        "ast_gate_rev": AST_GATE_REV,
        "extractor_rev": EXTRACTOR_REV,
        "sentinel_scheme_rev": SENTINEL_SCHEME_REV,
    }
    for key, expected in expected_constants.items():
        if payload.get(key) != expected:
            raise LandingError(f"coding verifier receipt {key} is not current")
    coding_items = [item for item in _object_list(patched.get("items"), "items") if item.get("bench") == CODING_BENCH]
    if payload.get("coding_item_count") != len(coding_items) or payload.get("verified_item_count") != len(coding_items):
        raise LandingError("coding verifier receipt does not cover every coding item")
    _assert_current_coding_artifacts(patched, image)
    return hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _assert_current_coding_artifacts(run: JsonObject, image_digest: str) -> None:
    suite = read_json_object(SUITE_DIR / "suite.json")
    rendered = render_benches(CODING_BENCH, "standard", None, SUITE_DIR, suite, [])
    if len(rendered) != 1:
        raise LandingError("current coding suite cannot be rendered")
    bench = rendered[0]
    expected_by_id = {
        str(benchmark["id"]): (source, benchmark)
        for source, benchmark in zip(bench.source_items, bench.benchmark_items, strict=True)
    }
    for item in _object_list(run.get("items"), "items"):
        if item.get("bench") != CODING_BENCH:
            continue
        item_id = str(item.get("id"))
        expected_pair = expected_by_id.get(item_id)
        if expected_pair is None:
            raise LandingError(f"coding item {item_id} is absent from the current frozen suite")
        source, benchmark = expected_pair
        expected = code_artifact_for_generation(source, benchmark, item)
        actual = _object(item.get("code_artifact"), f"coding artifact {item_id}")
        for key in (
            "raw_text_sha256",
            "extracted_code",
            "sanitized_code",
            "assembly_recipe_id",
            "assembled_program_sha256",
            "item_record_sha",
            "prompt_content_sha",
            "test_sha",
            "ast_gate_rev",
            "sentinel_scheme_rev",
            "extractor_rev",
            "harness_rev",
        ):
            if actual.get(key) != expected.get(key):
                raise LandingError(f"coding item {item_id} has stale or mismatched {key}")
        if actual.get("image_digest") != image_digest:
            raise LandingError(f"coding item {item_id} is not tied to the receipt image digest")


def _hash_actual_gguf(path: Path, *, claimed_sha256: str, claimed_size_bytes: int) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise LandingError(f"--gguf must be the actual model file: {resolved}")
    if resolved.stat().st_size != claimed_size_bytes:
        raise LandingError(
            f"actual GGUF size {resolved.stat().st_size} does not match manifest size {claimed_size_bytes}"
        )
    digest = _sha256_file(resolved)
    if digest != claimed_sha256:
        raise LandingError(
            f"actual GGUF SHA-256 {digest} does not match the run identity {claimed_sha256}"
        )
    return digest


def _trusted_coding_disposition(item: JsonObject) -> bool:
    artifact = item.get("code_artifact")
    if not isinstance(artifact, dict):
        return False
    if artifact.get("verdict_source") == "verifier":
        verdict = artifact.get("verdict")
        return (
            isinstance(verdict, dict)
            and isinstance(verdict.get("passed"), bool)
            and item.get("correct") is verdict.get("passed")
            and not (
                verdict.get("passed") is True
                and (verdict.get("timeout") is True or verdict.get("oom") is True)
            )
        )
    if item.get("correct") is not False:
        return False
    conformance = artifact.get("conformance_status")
    if isinstance(conformance, dict) and conformance.get("failure") == "coding_ast_rejected":
        return True
    extraction = artifact.get("extraction_status")
    return isinstance(extraction, dict) and extraction.get("status") not in (None, "ok")


def _rescore(
    run: JsonObject,
    *,
    original_path: Path,
    verified_path: Path,
    verifier_receipt_sha256: str,
) -> JsonObject:
    result = copy.deepcopy(run)
    manifest = _object(result.get("manifest"), "manifest")
    recorded = _object(manifest.get("scorecard"), "manifest.scorecard")
    profile_id = _required_text(recorded, "execution_profile_id")
    lane_spec_id = _required_text(recorded, "lane_spec_id")
    prior_scorecard_id = _required_text(recorded, "scorecard_id")
    current = scorecard_identity(profile_id, lane_spec_id=lane_spec_id)
    items = _object_list(result.get("items"), "items")
    suite_dir = _assert_rescore_coverage(result, items)
    _recompute_derived_record(result, items, suite_dir)
    budget = _budget_audit(items)  # type: ignore[arg-type]
    manifest["scorecard"] = current
    result["budget_audit"] = budget
    result["rescore_provenance"] = {
        "operation": "maintainer-land-run-current-scorer",
        "reason": (
            "coding verdicts re-executed by the maintainer verifier; scorecard identity and budget audit "
            "re-derived from current canonical functions; model generations unchanged"
        ),
        "source_run": original_path.name,
        "coding_verified_source": verified_path.name,
        "prior_scorecard_id": prior_scorecard_id,
        "rescored_scorecard_id": current["scorecard_id"],
        "generations_untouched": True,
        "coding_reverified": True,
        "verifier_receipt_sha256": verifier_receipt_sha256,
    }
    return result


def _assert_rescore_coverage(result: JsonObject, items: list[JsonObject]) -> Path:
    manifest = _object(result.get("manifest"), "manifest")
    suite_manifest = _object(manifest.get("suite"), "manifest.suite")
    coverage_profile_id = _required_text(suite_manifest, "coverage_profile_id")
    try:
        profile = coverage_profile_for_id(coverage_profile_id)
    except SuiteResolutionError as error:
        raise LandingError(str(error)) from error
    suite_dir = _suite_dir_for_identity(suite_manifest, coverage_profile_id)
    suite = read_json_object(suite_dir / "suite.json")
    tier = _required_text(suite_manifest, "tier")
    suite_benches = _object(suite.get("benches"), "suite.benches")
    expected_benches = set(profile.benches)
    static_benches = sorted(expected_benches & set(suite_benches))
    undefined_expected = sorted(expected_benches - set(suite_benches) - {"appworld_c"})
    if undefined_expected:
        raise LandingError(
            "stamped suite coverage profile references undefined bench(es): "
            + ", ".join(undefined_expected)
        )

    rendered = render_benches(",".join(static_benches), tier, None, suite_dir, suite, [])
    audit = _suite_coverage(
        rendered,
        items,  # type: ignore[arg-type]
        suite=suite,
        tier=tier,
        max_items=None,
    )
    missing_by_bench: dict[str, int] = {}
    missing_items = audit.get("missing_items")
    if not isinstance(missing_items, list) or not all(isinstance(item, str) for item in missing_items):
        raise LandingError("suite coverage audit returned invalid missing_items")
    for missing in missing_items:
        bench, separator, _item_id = missing.partition("/")
        if separator:
            missing_by_bench[bench] = missing_by_bench.get(bench, 0) + 1

    observed_counts: dict[str, int] = {}
    for item in items:
        bench = item.get("bench")
        if isinstance(bench, str):
            observed_counts[bench] = observed_counts.get(bench, 0) + 1
    expected_counts = {bench.name: len(bench.benchmark_items) for bench in rendered}
    if "appworld_c" in expected_benches:
        agentic = _object(result.get("agentic_run"), "agentic_run")
        subset_size = agentic.get("subset_size")
        if not isinstance(subset_size, int) or isinstance(subset_size, bool) or subset_size <= 0:
            raise LandingError(
                "agentic_run.subset_size must define the stamped appworld_c coverage count"
            )
        expected_counts["appworld_c"] = subset_size

    shortfalls = []
    for bench in sorted(expected_benches):
        expected = expected_counts[bench]
        observed = observed_counts.get(bench, 0)
        missing = missing_by_bench.get(bench, 0)
        if observed != expected or missing:
            detail = f"{bench} ({observed}/{expected} items)"
            if missing and observed == expected:
                detail += f" ({missing} required item id(s) missing)"
            shortfalls.append(detail)
    undefined_items = [
        f"{bench} ({observed_counts[bench]} items)"
        for bench in sorted(set(observed_counts) - expected_benches)
    ]
    if shortfalls or undefined_items:
        details = []
        if shortfalls:
            details.append("coverage mismatch: " + ", ".join(shortfalls))
        if undefined_items:
            details.append("undefined bench items: " + ", ".join(undefined_items))
        raise LandingError(
            f"record cannot satisfy stamped suite coverage {coverage_profile_id}: "
            + "; ".join(details)
        )
    return suite_dir


def _suite_dir_for_identity(suite_manifest: JsonObject, coverage_profile_id: str) -> Path:
    suite_version_value = _required_text(suite_manifest, "suite_version")
    release_id = _required_text(suite_manifest, "suite_release_id")
    expected_release_id = f"{suite_version_value}-{coverage_profile_id}"
    if release_id != expected_release_id:
        raise LandingError(
            f"manifest suite_release_id {release_id!r} does not match stamped coverage identity "
            f"{expected_release_id!r}"
        )
    match = re.fullmatch(r"suite-(v[0-9]+)", suite_version_value)
    if match is None:
        raise LandingError(f"unsupported stamped suite version: {suite_version_value}")
    suite_dir = REPO_ROOT / "suite" / match.group(1)
    if not (suite_dir / "suite.json").is_file():
        raise LandingError(f"stamped suite is unavailable for recertification: {suite_dir}")
    return suite_dir


def _recompute_derived_record(result: JsonObject, items: list[JsonObject], suite_dir: Path) -> None:
    suite = read_json_object(suite_dir / "suite.json")
    manifest = _object(result.get("manifest"), "manifest")
    suite_manifest = _object(manifest.get("suite"), "manifest.suite")
    tier = _required_text(suite_manifest, "tier")
    bench_names = sorted(
        {
            str(item.get("bench"))
            for item in items
            if isinstance(item.get("bench"), str) and item.get("bench") in _object(suite.get("benches"), "suite.benches")
        }
    )
    rendered = render_benches(",".join(bench_names), tier, None, suite_dir, suite, [])
    baselines = {bench.name: bench.baseline for bench in rendered}
    grouped: dict[str, list[JsonObject]] = {}
    for item in items:
        bench = item.get("bench")
        if isinstance(bench, str):
            grouped.setdefault(bench, []).append(item)
    benches: JsonObject = {}
    for bench, bench_items in grouped.items():
        # Inline AppWorld items describe the final diagnostic run, while the
        # publishable bench score is the mean across the full rerun campaign.
        # Re-aggregating those items would silently replace the campaign mean
        # with the final run's ASR and make the board reject the record.
        if bench == "appworld_c":
            benches[bench] = _agentic_campaign_aggregate(result)
        else:
            benches[bench] = aggregate(bench, bench_items, baselines.get(bench, 0.0))  # type: ignore[arg-type]
    result["benches"] = benches

    prior_totals = _object(result.get("totals"), "totals")
    wall_time = prior_totals.get("wall_time_seconds")
    if not isinstance(wall_time, int | float) or isinstance(wall_time, bool) or wall_time < 0:
        raise LandingError("totals.wall_time_seconds must be a non-negative number")
    result["totals"] = run_totals(items, float(wall_time))  # type: ignore[arg-type]
    result["perf"] = perf_summary(items)

    suite_axes = suite.get("axes") if isinstance(suite.get("axes"), dict) else None
    axis_status = axis_status_for_benches(benches, suite_axes)
    result["axis_status"] = axis_status
    scores = score_summary(benches, axis_status, suite_axes=suite_axes)  # type: ignore[arg-type]
    result["scores"] = scores
    result["headline_complete"] = scores.get("headline_score") is not None

    scorecard = _object(manifest.get("scorecard"), "manifest.scorecard")
    profile_id = _required_text(scorecard, "execution_profile_id")
    profile = execution_profile_for_id(profile_id)
    leak_regexes = () if profile is None else registry_leak_regexes(profile.conformance)
    lane = _required_text(suite_manifest, "lane")
    forced = profile is not None and profile.forcing is not None
    result["conformance"] = assess_run_conformance(
        grouped,  # type: ignore[arg-type]
        forced=forced,
        lane_spec_id=lane_spec_id_for_lane(lane),
        leak_regexes_by_bench={bench: leak_regexes for bench in grouped},
    )
    result["budget_audit"] = _budget_audit(items)  # type: ignore[arg-type]

    sampling = _object(manifest.get("sampling"), "manifest.sampling")
    temperature = sampling.get("temperature")
    top_k = sampling.get("top_k")
    seed = sampling.get("seed")
    deterministic = temperature == 0 and top_k == 1 and isinstance(seed, int) and not isinstance(seed, bool)
    result["sampler_audit"] = {
        "status": "deterministic" if deterministic else "unverified",
        "temperature": temperature,
        "top_k": top_k,
        "seed": seed,
        "determinism_policy": sampling.get("determinism_policy"),
    }
    result["prompt_audit"] = {
        "status": "canonical",
        "execution_profile_id": profile_id,
        "user_supplied_stops_removed": False,
    }
    result["suite_coverage"] = _suite_coverage(
        rendered,
        items,  # type: ignore[arg-type]
        suite=suite,
        tier=tier,
        max_items=None,
    )


def _agentic_campaign_aggregate(run: JsonObject) -> JsonObject:
    agentic = _object(run.get("agentic_run"), "agentic_run")
    subset_size = agentic.get("subset_size")
    mean_asr = agentic.get("mean_asr")
    if not isinstance(subset_size, int) or isinstance(subset_size, bool) or subset_size <= 0:
        raise LandingError("agentic_run.subset_size must be a positive integer")
    if not isinstance(mean_asr, int | float) or isinstance(mean_asr, bool) or not 0 <= mean_asr <= 1:
        raise LandingError("agentic_run.mean_asr must be a number between 0 and 1")
    return {
        "n": subset_size,
        "n_errors": 0,
        "n_extraction_failures": 0,
        "raw_accuracy": float(mean_asr),
        "chance_corrected": float(mean_asr),
        "conditional_accuracy": float(mean_asr),
        "termination_rate": 1.0,
    }


def _catalog_entry(run: JsonObject, run_dir: Path) -> JsonObject:
    catalog = _read_object(MODEL_CATALOG_PATH, "model catalog")
    models = _object_list(catalog.get("models"), "model catalog models")
    declared = _required_text(_object(run.get("model"), "run model"), "name")
    by_slug = [
        model for model in models
        if declared == _required_text(model, "slug") or declared.startswith(_required_text(model, "slug") + "-")
    ]
    if by_slug:
        return max(by_slug, key=lambda item: len(_required_text(item, "slug")))
    campaign_path = run_dir / "campaign.json"
    if campaign_path.is_file():
        campaign = _read_object(campaign_path, "campaign")
        hf_id = _object(campaign.get("model"), "campaign.model").get("hf_model_id")
        if isinstance(hf_id, str):
            exact = [model for model in models if str(model.get("id", "")).casefold() == hf_id.casefold()]
            if len(exact) == 1:
                return exact[0]
    raise LandingError(
        f"cannot map declared model {declared!r} to web/model_catalog.json; add the catalog entry before landing"
    )


def _existing_source_template(sources: list[JsonObject], model_id: str) -> JsonObject | None:
    return next((item for item in sources if str(item.get("model_id", "")).casefold() == model_id.casefold()), None)


def _source_entry(
    run: JsonObject,
    catalog: JsonObject,
    template: JsonObject | None,
    *,
    model_sha: str,
) -> JsonObject:
    manifest_model = _object(_object(run.get("manifest"), "manifest").get("model"), "manifest.model")
    suite = _object(_object(run.get("manifest"), "manifest").get("suite"), "manifest.suite")
    model_id = _required_text(catalog, "id")
    model_label = _template_text(template, "model_label") or _required_text(catalog, "display_name")
    family = _template_text(template, "family") or _required_text(catalog, "family")
    publisher = _template_text(template, "publisher") or _required_text(catalog, "org")
    gguf_repo = _template_text(template, "gguf_repo") or _optional_text(catalog.get("gguf_repo"))
    quant = _required_text(manifest_model, "quant_label")
    size = manifest_model.get("file_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise LandingError("manifest.model.file_size_bytes must be a positive integer")
    entry: JsonObject = {
        "kind": "community",
        "origin": "community_submission",
        "trust_label": "project_anchor",
        "agentic_provenance": "project_attested",
        "provenance_notes": [
            "maintainer_verified_exact_gguf",
            "maintainer_two_run_agentic_verification",
        ],
        "family": family,
        "model_id": model_id,
        "model_label": model_label,
        "quant_label": quant,
        "publisher": publisher,
        "gguf_repo": gguf_repo,
        "file": None,
        "reasoning_lane": _required_text(suite, "lane"),
        "independent_replication": False,
        "release_date": None,
        "vram_footprint_gb": size / 1_000_000_000,
        "notes": (
            f"Maintainer-landed exact GGUF {model_sha}; coding verdicts re-executed by the sandbox verifier, "
            "two-run agentic verification attached, and scorecard identity + budget audit re-derived with "
            "model generations unchanged."
        ),
    }
    return entry


def _canonical_path(run: JsonObject, model_sha: str) -> Path:
    name = _required_text(_object(run.get("model"), "run model"), "name")
    lane = _required_text(_object(_object(run.get("manifest"), "manifest").get("suite"), "manifest.suite"), "lane")
    return LANDED_RUNS_DIR / f"{slugify(name)}-{model_sha[:12]}-{slugify(lane)}.json"


def _model_sha(run: JsonObject) -> str:
    top = _required_text(_object(run.get("model"), "run model"), "file_sha256")
    manifest = _required_text(
        _object(_object(run.get("manifest"), "manifest").get("model"), "manifest.model"),
        "file_sha256",
    )
    if top != manifest or re.fullmatch(r"[0-9a-f]{64}", top) is None:
        raise LandingError("run model SHA-256 is missing, malformed, or inconsistent")
    return top


def _model_size(run: JsonObject) -> int:
    size = _object(_object(run.get("manifest"), "manifest").get("model"), "manifest.model").get("file_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise LandingError("manifest.model.file_size_bytes must be a positive integer")
    return size


def _source_for_artifact(sources: list[JsonObject], model_sha: str) -> JsonObject | None:
    for source in sources:
        raw_path = source.get("file")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            continue
        try:
            run = _read_object(path, "curated run")
            if _model_sha(run) == model_sha:
                return source
        except (LandingError, OSError, json.JSONDecodeError):
            continue
    return None


def _candidate_system(board: JsonObject, stem: str, source: JsonObject) -> JsonObject:
    slug = slugify(_required_text(source, "model_label"))
    model = next(
        (item for item in _object_list(board.get("models"), "candidate models") if item.get("slug") == slug),
        None,
    )
    if model is None:
        raise LandingError(f"candidate board omitted landed model {slug}")
    run_id = f"{slug}__{stem}"
    system = next(
        (item for item in _object_list(model.get("systems"), f"{slug}.systems") if item.get("run_id") == run_id),
        None,
    )
    if system is None:
        skipped_runs: list[JsonObject] = []
        manifest = board.get("manifest")
        if isinstance(manifest, dict):
            raw_skipped = manifest.get("skipped_runs")
            if isinstance(raw_skipped, list):
                skipped_runs = [item for item in raw_skipped if isinstance(item, dict)]
        canonical_name = f"{stem}.json"
        skipped = next(
            (
                item
                for item in skipped_runs
                if isinstance(item.get("file"), str) and Path(item["file"]).name == canonical_name
            ),
            None,
        )
        if skipped is not None:
            reason = skipped.get("reason")
            rendered_reason = reason if isinstance(reason, str) else repr(reason)
            raise LandingError(
                f"candidate board omitted landed system {run_id}; staged run {canonical_name} "
                f"was skipped: {rendered_reason}"
            )
        existing_run_ids = sorted(
            str(item["run_id"])
            for item in _object_list(model.get("systems"), f"{slug}.systems")
            if isinstance(item.get("run_id"), str)
        )
        rendered_ids = ", ".join(existing_run_ids) if existing_run_ids else "<none>"
        raise LandingError(
            f"candidate board omitted landed system {run_id}; no matching skipped_runs entry for "
            f"{canonical_name}; existing run_ids for {slug}: {rendered_ids}"
        )
    return system


def _preflight_web_build(sources: Path, board: Path, out_dir: Path) -> None:
    env = os.environ.copy()
    env["LOCALBENCH_BOARD_PATH"] = str(board)
    command = [sys.executable, "build_data.py", "--sources", str(sources), "--out", str(out_dir)]
    _checked(command, cwd=REPO_ROOT / "web", env=env, label="candidate web data build")


def _checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    label: str,
) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LandingError(f"{label} failed: {detail}")


def _write_launch_freeze(source: Path, out: Path, board_hash: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", board_hash) is None:
        raise LandingError("boardSha256 must be a 64-hex SHA-256 digest")
    original = source.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(boardSha256:\s*")[0-9a-f]+(")',
        rf"\g<1>{board_hash}\g<2>",
        original,
        count=1,
    )
    if count != 1:
        raise LandingError(f"could not locate boardSha256 in {source}")
    atomic_write_bytes(updated.encode("utf-8"), out)


def _validate_launch_freeze() -> None:
    value = LAUNCH_FREEZE_PATH.read_text(encoding="utf-8")
    if re.search(r'boardSha256:\s*"[0-9a-f]{64}"', value) is None:
        raise LandingError(f"could not locate boardSha256 in {LAUNCH_FREEZE_PATH}")


def _assert_protected_public_runs_unchanged(before_dir: Path, after_dir: Path) -> None:
    for model_slug, run_id in _PROTECTED_PUBLIC_RUNS:
        before = _public_run_bytes(before_dir / "models" / f"{model_slug}.json", run_id)
        after = _public_run_bytes(after_dir / "models" / f"{model_slug}.json", run_id)
        if before != after:
            raise LandingError(f"candidate web build changed protected public run {run_id}")
        before_detail = _required_file_bytes(before_dir / "runs" / f"{run_id}.json", run_id)
        after_detail = _required_file_bytes(after_dir / "runs" / f"{run_id}.json", run_id)
        if before_detail != after_detail:
            raise LandingError(f"candidate web build changed protected public run detail {run_id}")


def _public_run_bytes(path: Path, run_id: str) -> bytes:
    payload = _read_object(path, f"public model {path.name}")
    runs = _object_list(payload.get("runs"), f"{path.name}.runs")
    run = next((item for item in runs if item.get("run_id") == run_id), None)
    if run is None:
        raise LandingError(f"protected public run is missing: {run_id}")
    return (json.dumps(run, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _required_file_bytes(path: Path, run_id: str) -> bytes:
    if not path.is_file():
        raise LandingError(f"protected public run detail is missing: {run_id}")
    return path.read_bytes()


def _apply_staged_outputs(
    temp_dir: Path,
    staged_targets: tuple[tuple[Path, Path], ...],
) -> None:
    """Swap a completely validated output set, restoring every target on any failure."""
    _acquire_landing_lock()
    backups_dir = LANDING_BACKUPS_PATH
    try:
        backups_dir.mkdir()
    except Exception:
        LANDING_LOCK_PATH.unlink(missing_ok=True)
        raise
    journal: JsonObject = {"schema_version": "localbench.landing-journal.v1", "entries": []}
    attempted: list[tuple[Path, Path | None, JsonObject]] = []
    try:
        for index, (staged, target) in enumerate(staged_targets):
            if not staged.exists():
                raise LandingError(f"staged landing output is missing: {staged}")
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = backups_dir / f"{index}-{target.name}"
            existed = target.exists()
            entry: JsonObject = {
                "target": str(target),
                "backup": str(backup) if existed else None,
                "staged": str(staged),
                "backed_up": False,
                "swapped": False,
            }
            attempted.append((target, backup if existed else None, entry))
            entries = journal["entries"]
            if isinstance(entries, list):
                entries.append(entry)
            atomic_write_json(journal, LANDING_JOURNAL_PATH)
            if existed:
                os.replace(target, backup)
                entry["backed_up"] = True
                atomic_write_json(journal, LANDING_JOURNAL_PATH)
            os.replace(staged, target)
            entry["swapped"] = True
            atomic_write_json(journal, LANDING_JOURNAL_PATH)
    except Exception as apply_error:
        rollback_errors = _rollback_staged_outputs(attempted)
        if rollback_errors:
            journal["recovery_required"] = True
            journal["rollback_errors"] = rollback_errors
            try:
                atomic_write_json(journal, LANDING_JOURNAL_PATH)
            except Exception:
                pass
            detail = "; ".join(rollback_errors)
            raise LandingError(
                "landing apply failed and rollback was incomplete; "
                f"recovery journal: {LANDING_JOURNAL_PATH}; backups: {backups_dir}; "
                f"lock retained: {LANDING_LOCK_PATH}; rollback errors: {detail}"
            ) from apply_error
        _clear_landing_recovery_state(backups_dir)
        raise
    _clear_landing_recovery_state(backups_dir)


def _rollback_staged_outputs(
    attempted: list[tuple[Path, Path | None, JsonObject]],
) -> list[str]:
    errors: list[str] = []
    for target, backup, entry in reversed(attempted):
        try:
            if entry.get("swapped") is True:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            if entry.get("backed_up") is True:
                if backup is None or not backup.exists():
                    raise OSError(f"backup is missing for {target}")
                os.replace(backup, target)
        except Exception as error:
            errors.append(f"{target}: {error}")
    return errors


def _clear_landing_recovery_state(backups_dir: Path) -> None:
    shutil.rmtree(backups_dir)
    LANDING_JOURNAL_PATH.unlink(missing_ok=True)
    LANDING_LOCK_PATH.unlink(missing_ok=True)


def _acquire_landing_lock() -> None:
    try:
        descriptor = os.open(LANDING_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise LandingError(
            f"landing lock already exists: {LANDING_LOCK_PATH}; inspect the crash journal before retrying"
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
        handle.write("\n")


def _append_json_array_item(original: bytes, item: JsonObject) -> bytes:
    text = original.decode("utf-8")
    stripped = text.rstrip()
    if not stripped.endswith("]"):
        raise LandingError(f"{DATA_SOURCES_PATH} is not a JSON array")
    prefix = stripped[:-1].rstrip()
    separator = ",\n" if prefix.endswith("}") else "\n"
    rendered = json.dumps(item, indent=2, ensure_ascii=False, allow_nan=False)
    indented = "\n".join("  " + line for line in rendered.splitlines())
    return f"{prefix}{separator}{indented}\n]\n".encode("utf-8")


def _generated_at(board: JsonObject) -> str | None:
    manifest = board.get("manifest")
    return _optional_text(manifest.get("generated_at")) if isinstance(manifest, dict) else None


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise LandingError(f"{label} must be an object")
    return value


def _object_list(value: JsonValue | None, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LandingError(f"{label} must be an array of objects")
    return list(value)


def _required_text(value: JsonObject, key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text:
        raise LandingError(f"{key} must be a non-empty string")
    return text


def _optional_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def _template_text(template: JsonObject | None, key: str) -> str | None:
    return None if template is None else _optional_text(template.get(key))


__all__ = [
    "LandingError",
    "LandingResult",
    "changed_existing_ranked_rows",
    "land_run",
    "print_landing_checklist",
]
