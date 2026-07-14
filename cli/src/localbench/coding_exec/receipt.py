"""Signed receipts for maintainer BigCodeBench verification runs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._suite import item_hashes, read_json_object, suite_version
from localbench._types import JsonObject
from localbench.coding_exec.artifacts import (
    ASSEMBLY_RECIPE_ID,
    HARNESS_REV,
)
from localbench.coding_exec.ast_gate import AST_GATE_REV
from localbench.coding_exec.extract import EXTRACTOR_REV
from localbench.coding_exec.program import SENTINEL_SCHEME_REV
from localbench.coding_exec.score import BENCH
from localbench.submissions.canon import canonical_json_hash
from localbench.submissions.crypto import sign_manifest_payload, verify_manifest_signature
from localbench.submissions.validate import SubmissionValidationError

RECEIPT_SCHEMA_VERSION: Final = "localbench.coding_verifier_receipt.v1"


class CodingVerificationError(SubmissionValidationError):
    pass


@dataclass(frozen=True, slots=True)
class CodingVerificationResult:
    record: JsonObject
    receipt_sha256: str


def attach_signed_verifier_receipt(
    run: JsonObject,
    *,
    source_bytes: bytes,
    suite_dir: Path,
    image_digest: str,
    signing_key: Path,
) -> None:
    """Attach a receipt covering the exact source run and accepted coding patch."""
    suite = read_json_object(suite_dir / "suite.json")
    payload: JsonObject = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "complete": True,
        "source_run_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "coding_patch_sha256": coding_patch_sha256(run),
        "image_digest": image_digest,
        "runner_sha256": HARNESS_REV,
        "artifact_harness_rev": HARNESS_REV,
        "assembly_recipe_id": ASSEMBLY_RECIPE_ID,
        "ast_gate_rev": AST_GATE_REV,
        "extractor_rev": EXTRACTOR_REV,
        "sentinel_scheme_rev": SENTINEL_SCHEME_REV,
        "suite_version": suite_version(suite),
        "item_set_hashes": item_hashes(suite_dir, [f"{BENCH}.jsonl"]),
        "verified_item_count": sum(
            1
            for item in _items(run)
            if item.get("bench") == BENCH and _has_trusted_disposition(item)
        ),
        "coding_item_count": sum(1 for item in _items(run) if item.get("bench") == BENCH),
    }
    run["coding_verifier_receipt"] = {
        "payload": payload,
        "signature": sign_manifest_payload(payload, signing_key),
    }


def verify_signed_verifier_receipt(receipt: JsonObject, expected_public_key: str) -> JsonObject:
    payload = receipt.get("payload")
    signature = receipt.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        raise ValueError("coding verifier receipt must contain payload and signature objects")
    if signature.get("public_key") != expected_public_key:
        raise ValueError("coding verifier receipt signer is not the configured maintainer verifier")
    if not verify_manifest_signature({"payload": payload, "signature": signature}):
        raise ValueError("coding verifier receipt signature is invalid")
    return dict(payload)


def coding_patch_sha256(run: JsonObject) -> str:
    patch: list[JsonObject] = []
    for item in _items(run):
        if item.get("bench") != BENCH:
            continue
        artifact = item.get("code_artifact")
        patch.append(
            {
                "bench": BENCH,
                "id": item.get("id"),
                "correct": item.get("correct"),
                "extracted": item.get("extracted"),
                "failure_kind": item.get("failure_kind"),
                "verdict": artifact.get("verdict") if isinstance(artifact, dict) else None,
                "verdict_source": artifact.get("verdict_source") if isinstance(artifact, dict) else None,
                "image_digest": artifact.get("image_digest") if isinstance(artifact, dict) else None,
                "conformance_status": artifact.get("conformance_status") if isinstance(artifact, dict) else None,
                "extraction_status": artifact.get("extraction_status") if isinstance(artifact, dict) else None,
            },
        )
    return canonical_json_hash(patch)


def _items(run: JsonObject) -> list[JsonObject]:
    raw = run.get("items")
    return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _has_trusted_disposition(item: JsonObject) -> bool:
    artifact = item.get("code_artifact")
    if not isinstance(artifact, dict):
        return False
    if artifact.get("verdict_source") == "verifier" and isinstance(artifact.get("verdict"), dict):
        return True
    if item.get("correct") is not False:
        return False
    conformance = artifact.get("conformance_status")
    extraction = artifact.get("extraction_status")
    return (
        isinstance(conformance, dict) and conformance.get("failure") == "coding_ast_rejected"
    ) or (
        isinstance(extraction, dict) and extraction.get("status") not in (None, "ok")
    )


__all__ = [
    "CodingVerificationError",
    "CodingVerificationResult",
    "RECEIPT_SCHEMA_VERSION",
    "attach_signed_verifier_receipt",
    "coding_patch_sha256",
    "verify_signed_verifier_receipt",
]
