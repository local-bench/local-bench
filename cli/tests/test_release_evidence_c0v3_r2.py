"""Mechanical release gate binding the shipped constants to the committed evidence bundle.

This is the F3 remedy from the night-run plan review, hardened after the arm's-length
evidence review (F1): nothing may ship unless the client's pinned manifest digest, the active
contract, and the worker identity all reconcile with the committed C0 packaging-differential
evidence for the c0v3-r2 runtime -- AND the differential evidence actually proves two distinct
installations behaved identically. The gate is written to reject the c0v2 self-comparison
failure class: hollow verdict maps, missing per-task traces, constant/empty digests, and any
side whose worker modules did not resolve from its own installation root.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from localbench.appliance.manifest import (
    PINNED_INITIAL_MANIFEST_SHA256,
    PINNED_RUNTIME_ID,
    RUNTIME_KEY_ID,
    RUNTIME_PUBLIC_KEYS,
    verify_manifest_bytes,
)
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.scoring.agentic_exec.worker_identity import _WORKER_MODULES
from localbench.submissions.canon import canonical_json_bytes

EVIDENCE_DIR = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "release-evidence"
    / "aw013p1-pypi28113a7a-ubuntu2404-py312-c0v3-r2"
)
# Recorded in the release README; the worker wheel the rootfs baked and the differential
# validated. Bound here so a swapped evidence bundle with a different wheel is rejected.
RELEASE_WORKER_WHEEL_SHA256 = (
    "9d2b7962932e6b3b6ae57f338ee3fab4b2233ab48333c7a124b53794d9c6ab3f"
)
RELEASE_ROOTFS_SHA256 = (
    "257108fb8b17ec11374acf81d80d24419c677aea7de78dcf9ee8f3ece730ac11"
)
EQUAL_FIELDS = frozenset(
    {
        "model_turn_requests",
        "sandbox_operations",
        "finalize_verdict",
        "scored_envelopes",
        "aggregates",
        "worker_identity",
    }
)
TRACE_FIELDS = ("model_turn_requests", "sandbox_operations", "finalize_verdict", "scored_envelopes")
# Digests of empty/constant JSON values -- what a hollow trace would hash to.
HOLLOW_DIGESTS = frozenset(
    hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    for value in ([], None, {}, "", 0)
)
ORIGIN_MODULES = (*_WORKER_MODULES, "localbench")
SELF_TEST_DRIFT_MARKERS = (
    "agentic execution contract drift",
    "agentic runtime identity drift",
)


def _load(name: str) -> dict:
    return json.loads((EVIDENCE_DIR / name).read_text(encoding="utf-8"))


def test_client_pin_matches_committed_manifest_bytes() -> None:
    raw = (EVIDENCE_DIR / "manifest.json").read_bytes()
    assert PINNED_INITIAL_MANIFEST_SHA256 != ""
    assert hashlib.sha256(raw).hexdigest() == PINNED_INITIAL_MANIFEST_SHA256


def test_committed_manifest_verifies_under_admitted_runtime_key() -> None:
    raw = (EVIDENCE_DIR / "manifest.json").read_bytes()
    trust = _load("trust-v1.json")
    payload = verify_manifest_bytes(
        raw,
        expected_runtime_id=PINNED_RUNTIME_ID,
        trust_state=trust.get("payload", trust),
        expected_manifest_sha256=PINNED_INITIAL_MANIFEST_SHA256,
    )
    assert payload["runtime_id"] == PINNED_RUNTIME_ID
    signature = _load("manifest.json")["signature"]
    assert signature["key_id"] == RUNTIME_KEY_ID
    assert signature["public_key"] == RUNTIME_PUBLIC_KEYS[RUNTIME_KEY_ID]


def test_committed_differential_proves_distinct_installations() -> None:
    evidence = _load("packaging-differential.json")
    assert evidence["mode"] == "differential"
    assert evidence["verdict"] == "pass"
    assert evidence.get("diffs") == []

    # All six named comparison fields must be present and true -- an empty or partial map
    # (all({}.values()) is True) must not slip through.
    verdicts = evidence["equal_fields_verdicts"]
    assert set(verdicts) == EQUAL_FIELDS
    assert all(verdicts.values())

    repo = evidence["per_side"]["repo"]
    appliance = evidence["per_side"]["appliance"]

    # Both sides genuinely ran and succeeded.
    for side in (repo, appliance):
        aggregates = side["aggregates"]
        assert aggregates["tasks_succeeded"] == aggregates["tasks_total"] > 0

    # Installation distinctness -- the c0v2 failure class. Every worker module (and the
    # localbench package) must resolve from the side's own root, and neither side's sys.path
    # may leak the other's root.
    for module in ORIGIN_MODULES:
        assert str(repo["module_origins"][module]).startswith("/opt/localbench/diff-src/")
        assert str(appliance["module_origins"][module]).startswith("/opt/localbench/venv/")
    # sys_path must be present (a forged bundle must not skip the leak check by omitting it).
    appliance_sys_path = appliance["module_origins"]["sys_path"]
    assert isinstance(appliance_sys_path, list) and appliance_sys_path
    assert not any("/opt/localbench/diff-src" in str(entry) for entry in appliance_sys_path)
    assert repo["module_origins"].get("sys_prefix") == "/opt/localbench/venv"

    # Per-task traces exist on both sides, are equal across sides, and are not hollow digests.
    task_ids = tuple(evidence["task_ids"])
    assert len(task_ids) >= 2
    for task_id in task_ids:
        repo_task = repo["per_task"][task_id]
        appliance_task = appliance["per_task"][task_id]
        for field in TRACE_FIELDS:
            repo_digest = repo_task[field]
            appliance_digest = appliance_task[field]
            assert repo_digest == appliance_digest
            assert repo_digest not in HOLLOW_DIGESTS

    # worker_content must match across sides and be non-empty.
    repo_content = repo["worker_identity"]["worker_content_sha256"]
    assert repo_content and len(repo_content) == 64
    assert repo_content == appliance["worker_identity"]["worker_content_sha256"]


def test_differential_is_cross_bound_to_the_signed_manifest() -> None:
    evidence = _load("packaging-differential.json")
    manifest_payload = _load("manifest.json")["payload"]
    contract = load_execution_contract()
    assert evidence["runtime_id"] == manifest_payload["runtime_id"] == PINNED_RUNTIME_ID
    assert evidence["rootfs_sha256"] == manifest_payload["rootfs"]["sha256"] == RELEASE_ROOTFS_SHA256
    assert evidence["worker_wheel_sha256"] == RELEASE_WORKER_WHEEL_SHA256
    assert (
        evidence["contract_payload_sha256"]
        == manifest_payload["execution_contract_sha256"]
        == contract["payload_sha256"]
    )
    assert contract["payload"]["contract_id"] == "agentic-execution-contract-aw013p1-pypi28113a7a-v4"


def test_differential_selftest_is_a_bound_negative_control() -> None:
    selftest = _load("packaging-differential-selftest.json")
    assert selftest["mode"] == "self-test"
    assert selftest["verdict"] != "pass"
    # Bind the negative control to this exact release so a stale self-test from an earlier
    # build cannot satisfy the gate.
    assert selftest["runtime_id"] == PINNED_RUNTIME_ID
    assert selftest["rootfs_sha256"] == RELEASE_ROOTFS_SHA256
    assert selftest["worker_wheel_sha256"] == RELEASE_WORKER_WHEEL_SHA256
    # The failure must be a designed source-divergence detection, not an unrelated startup
    # error that would mean the detection layer never fired.
    blob = json.dumps(selftest)
    assert any(marker in blob for marker in SELF_TEST_DRIFT_MARKERS)
