#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# ─── How to run ───────────────────────────────────────────────────────────────
# uv run --project cli python cli/tools/verify_release_evidence.py --help
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Final, Literal

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.execution_contract import (
    V5_CONTRACT_ID,
    ExecutionContractDriftError,
    load_execution_contract,
)
from localbench.scoring.agentic_exec.worker_identity import _WORKER_MODULES
from localbench.submissions.canon import canonical_json_hash

EvidenceMode = Literal["differential", "self-test"]

_SCHEMA: Final = "localbench.packaging_differential.v1"
_TASK_IDS: Final = ("fac291d_1", "50e1ac9_1")
_TASK_HASH_FIELDS: Final = (
    "model_turn_requests",
    "sandbox_operations",
    "finalize_verdict",
    "scored_envelopes",
)
_EQUAL_FIELDS: Final = (
    *_TASK_HASH_FIELDS,
    "aggregates",
    "worker_identity",
)
_REPO_SOURCE_ROOT: Final = "/opt/localbench/diff-src"
_DRIFT_MARKERS: Final = (
    "agentic execution contract drift",
    "agentic runtime identity drift",
)
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class VerificationError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class EvidenceDocument:
    path: Path
    payload: JsonObject
    sha256: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify c0v5 release evidence")
    parser.add_argument("--evidence", action="append", required=True, type=Path)
    parser.add_argument("--pending-contract", required=True, type=Path)
    parser.add_argument("--rootfs-sha256", required=True)
    parser.add_argument("--worker-wheel-sha256", required=True)
    parser.add_argument(
        "--mode",
        action="append",
        choices=("differential", "self-test"),
    )
    parser.add_argument("--expect-self-test", type=int)
    args = parser.parse_args()
    try:
        _require_sha256(args.rootfs_sha256, "expected rootfs sha256")
        _require_sha256(args.worker_wheel_sha256, "expected worker wheel sha256")
        documents = tuple(_load_evidence(path) for path in args.evidence)
        for document in documents:
            print(f"evidence_sha256={document.sha256} path={document.path}")
        modes = _resolve_modes(documents, args.mode, args.expect_self_test)
        contract = load_execution_contract(
            args.pending_contract,
            expected_contract_id=V5_CONTRACT_ID,
        )
        payload = _require_object(contract, "payload", "pending contract")
        contract_sha256 = canonical_json_hash(payload)
        if contract.get("payload_sha256") != contract_sha256:
            raise VerificationError("pending contract payload sha256 mismatch")
        for document, mode in zip(documents, modes, strict=True):
            _verify_evidence(
                document.payload,
                mode=mode,
                contract_id=str(payload["contract_id"]),
                contract_sha256=contract_sha256,
                rootfs_sha256=args.rootfs_sha256,
                worker_wheel_sha256=args.worker_wheel_sha256,
            )
    except (VerificationError, ExecutionContractDriftError) as error:
        print(f"FAIL: {error}")
        return 1
    hashes = " ".join(document.sha256 for document in documents)
    print(f"PASS evidence_sha256={hashes}")
    return 0


def _load_evidence(path: Path) -> EvidenceDocument:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read evidence {path}: {type(error).__name__}") from error
    if not isinstance(parsed, dict):
        raise VerificationError(f"evidence {path} must be a JSON object")
    return EvidenceDocument(path=path, payload=parsed, sha256=canonical_json_hash(parsed))


def _resolve_modes(
    documents: tuple[EvidenceDocument, ...],
    explicit_modes: list[str] | None,
    expected_self_tests: int | None,
) -> tuple[EvidenceMode, ...]:
    if explicit_modes is not None:
        if len(explicit_modes) != len(documents):
            raise VerificationError("each evidence file requires one --mode")
        modes = tuple(_parse_mode(mode) for mode in explicit_modes)
    else:
        if expected_self_tests is None:
            raise VerificationError("--expect-self-test is required when --mode is omitted")
        modes = tuple(_parse_mode(document.payload.get("mode")) for document in documents)
    actual_self_tests = sum(mode == "self-test" for mode in modes)
    if expected_self_tests is not None and actual_self_tests != expected_self_tests:
        raise VerificationError("self-test evidence count mismatch")
    return modes


def _parse_mode(value: JsonValue) -> EvidenceMode:
    if value == "differential":
        return "differential"
    if value == "self-test":
        return "self-test"
    raise VerificationError("evidence mode must be differential or self-test")


def _verify_evidence(
    evidence: JsonObject,
    *,
    mode: EvidenceMode,
    contract_id: str,
    contract_sha256: str,
    rootfs_sha256: str,
    worker_wheel_sha256: str,
) -> None:
    if evidence.get("schema") != _SCHEMA:
        raise VerificationError("evidence schema mismatch")
    if evidence.get("mode") != mode:
        raise VerificationError("evidence mode mismatch")
    if evidence.get("contract_payload_sha256") != contract_sha256:
        raise VerificationError("contract payload sha256 mismatch")
    if evidence.get("contract_id") != contract_id:
        raise VerificationError("contract id mismatch")
    if evidence.get("rootfs_sha256") != rootfs_sha256:
        raise VerificationError("rootfs sha256 mismatch")
    if evidence.get("worker_wheel_sha256") != worker_wheel_sha256:
        raise VerificationError("worker wheel sha256 mismatch")
    _verify_module_origins(evidence)
    if mode == "differential":
        _verify_differential(evidence)
    else:
        _verify_self_test(evidence)


def _verify_differential(evidence: JsonObject) -> None:
    if evidence.get("verdict") != "pass":
        raise VerificationError("differential verdict must be pass")
    verdicts = _require_object(evidence, "equal_fields_verdicts", "evidence")
    if set(verdicts) != set(_EQUAL_FIELDS) or not all(
        verdicts.get(field) is True for field in _EQUAL_FIELDS
    ):
        raise VerificationError("differential equality verdicts must all be true")
    if evidence.get("diffs") != []:
        raise VerificationError("differential diffs must be empty")
    task_ids = evidence.get("task_ids")
    if not isinstance(task_ids, list) or set(task_ids) != set(_TASK_IDS) or len(task_ids) != len(_TASK_IDS):
        raise VerificationError("differential task set is incomplete")
    staged = _require_object(evidence, "staged_source", "evidence")
    staged_count = staged.get("staged_file_count")
    if not isinstance(staged_count, int) or isinstance(staged_count, bool) or staged_count <= 0:
        raise VerificationError("staged source file count must be positive")
    per_side = _require_object(evidence, "per_side", "evidence")
    for side_name in ("repo", "appliance"):
        side = _require_object(per_side, side_name, "per_side")
        per_task = _require_object(side, "per_task", f"{side_name} side")
        for task_id in _TASK_IDS:
            capture = _require_object(per_task, task_id, f"{side_name} per_task")
            if not all(_is_sha256(capture.get(field)) for field in _TASK_HASH_FIELDS):
                raise VerificationError(f"{side_name} task {task_id} hashes are incomplete")


def _verify_self_test(evidence: JsonObject) -> None:
    if evidence.get("verdict") != "fail":
        raise VerificationError("self-test verdict must be fail")
    diffs = evidence.get("diffs")
    if not isinstance(diffs, list) or not any(
        marker in text
        for text in _string_values(diffs)
        for marker in _DRIFT_MARKERS
    ):
        raise VerificationError("self-test designed drift marker is missing")


def _verify_module_origins(evidence: JsonObject) -> None:
    per_side = _require_object(evidence, "per_side", "evidence")
    for side_name in ("repo", "appliance"):
        side = _require_object(per_side, side_name, "per_side")
        origins = _require_object(side, "module_origins", f"{side_name} side")
        if side_name == "repo":
            prefix = f"{_REPO_SOURCE_ROOT}/"
        else:
            sys_prefix = origins.get("sys_prefix")
            if not isinstance(sys_prefix, str) or not sys_prefix:
                raise VerificationError("appliance module origins omit installed venv root")
            prefix = f"{sys_prefix.rstrip('/')}/"
        for module_name in (*_WORKER_MODULES, "localbench"):
            path = origins.get(module_name)
            if not isinstance(path, str) or not path.startswith(prefix):
                raise VerificationError(f"{side_name} module origin is outside {prefix}")


def _require_object(container: JsonObject, field: str, context: str) -> JsonObject:
    value = container.get(field)
    if not isinstance(value, dict):
        raise VerificationError(f"{context} {field} must be an object")
    return value


def _require_sha256(value: str, label: str) -> None:
    if not _is_sha256(value):
        raise VerificationError(f"{label} must be 64 lowercase hex characters")


def _is_sha256(value: JsonValue) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _string_values(value: JsonValue) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(text for item in value for text in _string_values(item))
    if isinstance(value, dict):
        return tuple(text for item in value.values() for text in _string_values(item))
    return ()


if __name__ == "__main__":
    raise SystemExit(main())
