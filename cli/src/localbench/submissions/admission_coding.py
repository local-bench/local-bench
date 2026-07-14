from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.coding_exec.receipt import (
    CODING_ARTIFACT_PATCH_FIELDS,
    CODING_ITEM_PATCH_FIELDS,
    CodingVerificationError,
    CodingVerificationResult,
    coding_items_by_id,
    verify_coding_receipt,
)
from localbench.coding_exec.score import BENCH as CODING_BENCH
from localbench.submissions.strict_json import (
    StrictJsonError,
    json_values_equal,
    strict_json_loads,
)


def verify_coding_receipt_for_bundle(
    bundle: JsonObject,
    bundle_source_bytes: bytes,
    verified_path: Path,
    *,
    suite_dir: Path,
    verifier_public_key: str,
) -> CodingVerificationResult:
    verified = _read_verified(verified_path)
    receipt = verify_coding_receipt(
        verified,
        suite_dir=suite_dir,
        expected_public_key=verifier_public_key,
    )
    bundle_items = coding_items_by_id(bundle, suite_dir=suite_dir)
    verified_items = coding_items_by_id(verified, suite_dir=suite_dir)
    _assert_run_identity(bundle, verified)
    _assert_generation_identity(bundle_items, verified_items)
    source_hashes = _admission_source_hashes(
        bundle_source_bytes,
        verified,
        bundle_items,
    )
    if receipt.source_run_sha256 not in source_hashes:
        raise CodingVerificationError("coding verifier receipt is not bound to the submitted run")
    return CodingVerificationResult(
        record=verified,
        receipt_sha256=receipt.receipt_sha256,
    )


def _read_verified(path: Path) -> JsonObject:
    try:
        source = path.read_bytes()
    except OSError as error:
        raise CodingVerificationError(f"coding-verified run not found: {path}") from error
    try:
        value = strict_json_loads(source, "coding-verified run")
    except StrictJsonError as error:
        raise CodingVerificationError(str(error)) from error
    if not isinstance(value, dict):
        raise CodingVerificationError("coding-verified run must be a JSON object")
    return value


def _assert_run_identity(bundle: JsonObject, verified: JsonObject) -> None:
    bundle_manifest = _required_object(bundle.get("manifest"), "bundle manifest")
    verified_manifest = _required_object(verified.get("manifest"), "verified manifest")
    if not json_values_equal(bundle_manifest.get("model"), verified_manifest.get("model")):
        raise CodingVerificationError("coding verifier receipt model identity does not match the bundle")
    if not json_values_equal(bundle.get("model"), verified.get("model")):
        raise CodingVerificationError("coding verifier receipt artifact identity does not match the bundle")
    if not json_values_equal(bundle_manifest.get("suite"), verified_manifest.get("suite")):
        raise CodingVerificationError("coding verifier receipt suite identity does not match the bundle")
    stable_bundle = {
        key: value
        for key, value in bundle_manifest.items()
        if key not in {"execution", "model", "suite"}
    }
    stable_verified = {
        key: value
        for key, value in verified_manifest.items()
        if key not in {"execution", "model", "suite"}
    }
    if not json_values_equal(stable_bundle, stable_verified):
        raise CodingVerificationError("coding verifier receipt manifest identity does not match the bundle")


def _assert_generation_identity(
    bundle_items: dict[str, JsonObject],
    verified_items: dict[str, JsonObject],
) -> None:
    # Admission compares parsed JSON values, not raw item strings: bundle canonicalization may
    # change whitespace/key order, while recursive exact-type equality still rejects bool/int
    # coercion. This representation bridge is admission-only; landing remains exact-byte bound.
    for item_id, bundle_item in bundle_items.items():
        verified_item = verified_items[item_id]
        if not json_values_equal(
            _generation_identity(bundle_item),
            _generation_identity(verified_item),
        ):
            raise CodingVerificationError(
                f"coding verifier receipt generation content does not match bundle item {item_id}"
            )


def _generation_identity(item: JsonObject) -> JsonObject:
    identity = {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if key not in CODING_ITEM_PATCH_FIELDS
    }
    artifact = _required_object(item.get("code_artifact"), "coding item artifact")
    identity["code_artifact"] = {
        key: copy.deepcopy(value)
        for key, value in artifact.items()
        if key not in CODING_ARTIFACT_PATCH_FIELDS
    }
    return identity


def _admission_source_hashes(
    bundle_source_bytes: bytes,
    verified: JsonObject,
    bundle_items: dict[str, JsonObject],
) -> frozenset[str]:
    reconstructed = copy.deepcopy(verified)
    reconstructed.pop("coding_verifier_receipt", None)
    raw_items = reconstructed.get("items")
    if not isinstance(raw_items, list):
        raise CodingVerificationError("coding-verified run items must be an array")
    for raw_item in raw_items:
        if not isinstance(raw_item, dict) or raw_item.get("bench") != CODING_BENCH:
            continue
        item_id = raw_item.get("id")
        if not isinstance(item_id, str):
            raise CodingVerificationError("coding item id must be a string")
        original = bundle_items[item_id]
        original_artifact = _required_object(original.get("code_artifact"), "bundle coding artifact")
        restored_artifact = _required_object(raw_item.get("code_artifact"), "verified coding artifact")
        for key in CODING_ARTIFACT_PATCH_FIELDS:
            if key in original_artifact:
                restored_artifact[key] = copy.deepcopy(original_artifact[key])
            else:
                restored_artifact.pop(key, None)
        raw_item["code_artifact"] = restored_artifact
        for key in CODING_ITEM_PATCH_FIELDS[1:]:
            if key in original:
                raw_item[key] = copy.deepcopy(original[key])
            else:
                raw_item.pop(key, None)
    reconstructed_bytes = (json.dumps(reconstructed, indent=2) + "\n").encode("utf-8")
    return frozenset(
        {
            hashlib.sha256(bundle_source_bytes).hexdigest(),
            hashlib.sha256(reconstructed_bytes).hexdigest(),
        }
    )


def _required_object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise CodingVerificationError(f"{label} must be a JSON object")
    return value
