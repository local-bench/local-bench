"""Signed receipts for maintainer BigCodeBench verification runs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._suite import item_hashes, read_json_object, render_benches, suite_version
from localbench._types import JsonObject
from localbench.coding_exec.artifacts import (
    ASSEMBLY_RECIPE_ID,
    HARNESS_REV,
    code_artifact_for_generation,
)
from localbench.coding_exec.ast_gate import AST_GATE_REV
from localbench.coding_exec.extract import EXTRACTOR_REV
from localbench.coding_exec.program import SENTINEL_SCHEME_REV
from localbench.coding_exec.score import BENCH
from localbench.submissions.canon import canonical_json_hash
from localbench.submissions.crypto import sign_manifest_payload, verify_manifest_signature
from localbench.submissions.strict_json import json_values_equal
from localbench.submissions.validate import SubmissionValidationError

RECEIPT_SCHEMA_VERSION: Final = "localbench.coding_verifier_receipt.v1"
CODING_ITEM_PATCH_FIELDS: Final = ("code_artifact", "correct", "extracted", "failure_kind")
CODING_ARTIFACT_PATCH_FIELDS: Final = (
    "verdict",
    "verdict_source",
    "image_digest",
    "conformance_status",
    "extraction_status",
    "ast_gate_rev",
    "sentinel_scheme_rev",
    "assembled_program_sha256",
)


class CodingVerificationError(SubmissionValidationError):
    pass


@dataclass(frozen=True, slots=True)
class CodingVerificationResult:
    record: JsonObject
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedCodingReceipt:
    source_run_sha256: str
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


def verify_coding_receipt(
    run: JsonObject,
    *,
    suite_dir: Path,
    expected_public_key: str,
) -> VerifiedCodingReceipt:
    receipt_value = run.get("coding_verifier_receipt")
    if not isinstance(receipt_value, dict):
        raise CodingVerificationError("coding_verifier_receipt must be a JSON object")
    receipt = dict(receipt_value)
    try:
        payload = verify_signed_verifier_receipt(receipt, expected_public_key)
    except ValueError as error:
        raise CodingVerificationError(str(error)) from error
    if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION or payload.get("complete") is not True:
        raise CodingVerificationError("coding verifier receipt is incomplete or uses an unsupported schema")
    source_run_sha256 = payload.get("source_run_sha256")
    if not isinstance(source_run_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", source_run_sha256) is None:
        raise CodingVerificationError("coding verifier receipt source_run_sha256 must be 64 lowercase hex")
    image_digest = payload.get("image_digest")
    if not isinstance(image_digest, str) or re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image_digest) is None:
        raise CodingVerificationError("coding verifier receipt image must be digest-pinned")

    for key, expected in _current_receipt_constants(suite_dir).items():
        actual = payload.get(key)
        if not json_values_equal(actual, expected):
            raise CodingVerificationError(f"coding verifier receipt {key} is not current")

    coding_items = coding_items_by_id(run, suite_dir=suite_dir)
    item_count = len(coding_items)
    if not json_values_equal(payload.get("coding_item_count"), item_count):
        raise CodingVerificationError("coding verifier receipt does not cover every coding item")
    if not json_values_equal(payload.get("verified_item_count"), item_count):
        raise CodingVerificationError("coding verifier receipt does not verify every coding item")
    if not all(_has_trusted_disposition(item) for item in coding_items.values()):
        raise CodingVerificationError("coding verifier receipt contains an unverified coding item")
    if not json_values_equal(payload.get("coding_patch_sha256"), coding_patch_sha256(run)):
        raise CodingVerificationError("coding verifier receipt does not cover the accepted coding patch")
    _assert_current_coding_artifacts(coding_items, image_digest, suite_dir=suite_dir)
    return VerifiedCodingReceipt(
        source_run_sha256=source_run_sha256,
        receipt_sha256=canonical_json_hash(receipt),
    )


def coding_items_by_id(run: JsonObject, *, suite_dir: Path) -> dict[str, JsonObject]:
    suite = read_json_object(suite_dir / "suite.json")
    rendered = render_benches(BENCH, "standard", None, suite_dir, suite, [])
    if len(rendered) != 1:
        raise CodingVerificationError("current coding suite cannot be rendered")
    expected_ids = {str(item["id"]) for item in rendered[0].benchmark_items}
    coding_items = [item for item in _items(run) if item.get("bench") == BENCH]
    observed: dict[str, JsonObject] = {}
    duplicates: set[str] = set()
    for item in coding_items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise CodingVerificationError("coding item id must be a non-empty string")
        if item_id in observed:
            duplicates.add(item_id)
        observed[item_id] = item
    if duplicates:
        raise CodingVerificationError("duplicate coding item id(s): " + ", ".join(sorted(duplicates)))
    missing = sorted(expected_ids - observed.keys())
    if missing:
        raise CodingVerificationError("missing coding item id(s): " + ", ".join(missing))
    extra = sorted(observed.keys() - expected_ids)
    if extra:
        raise CodingVerificationError("extra coding item id(s): " + ", ".join(extra))
    return observed


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


def _current_receipt_constants(suite_dir: Path) -> JsonObject:
    suite = read_json_object(suite_dir / "suite.json")
    return {
        "suite_version": suite_version(suite),
        "item_set_hashes": item_hashes(suite_dir, [f"{BENCH}.jsonl"]),
        "runner_sha256": HARNESS_REV,
        "artifact_harness_rev": HARNESS_REV,
        "assembly_recipe_id": ASSEMBLY_RECIPE_ID,
        "ast_gate_rev": AST_GATE_REV,
        "extractor_rev": EXTRACTOR_REV,
        "sentinel_scheme_rev": SENTINEL_SCHEME_REV,
    }


def _assert_current_coding_artifacts(
    coding_items: dict[str, JsonObject],
    image_digest: str,
    *,
    suite_dir: Path,
) -> None:
    suite = read_json_object(suite_dir / "suite.json")
    bench = render_benches(BENCH, "standard", None, suite_dir, suite, [])[0]
    expected_by_id = {
        str(benchmark["id"]): (source, benchmark)
        for source, benchmark in zip(bench.source_items, bench.benchmark_items, strict=True)
    }
    for item_id, item in coding_items.items():
        source, benchmark = expected_by_id[item_id]
        expected = code_artifact_for_generation(source, benchmark, item)
        artifact = item.get("code_artifact")
        if not isinstance(artifact, dict):
            raise CodingVerificationError(f"coding artifact {item_id} must be a JSON object")
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
            if not json_values_equal(artifact.get(key), expected.get(key)):
                raise CodingVerificationError(f"coding item {item_id} has stale or mismatched {key}")
        if not json_values_equal(artifact.get("image_digest"), image_digest):
            raise CodingVerificationError(
                f"coding item {item_id} is not tied to the receipt image digest"
            )


__all__ = [
    "CODING_ARTIFACT_PATCH_FIELDS",
    "CODING_ITEM_PATCH_FIELDS",
    "CodingVerificationError",
    "CodingVerificationResult",
    "RECEIPT_SCHEMA_VERSION",
    "VerifiedCodingReceipt",
    "attach_signed_verifier_receipt",
    "coding_items_by_id",
    "coding_patch_sha256",
    "verify_coding_receipt",
    "verify_signed_verifier_receipt",
]
