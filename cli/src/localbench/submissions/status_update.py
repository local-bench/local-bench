from __future__ import annotations

from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import write_json_file
from localbench.submissions.foundation import VALIDATOR_VERSION, rescore_bundle, validate_submission_bundle
from localbench.submissions.projection import projection_object_sha256

STATUS_UPDATE_SCHEMA_VERSION: Final = "localbench.submission_status_update.v1"


def verify_submission(
    bundle_path: Path,
    *,
    suite_dir: Path,
    projection_out: Path,
    validated_at: str,
    validator_commit: str | None,
    origin: str,
) -> JsonObject:
    validation = validate_submission_bundle(bundle_path, suite_dir=suite_dir)
    projection = rescore_bundle(bundle_path, suite_dir=suite_dir, validated_at=validated_at, origin=origin)
    write_json_file(projection_out, projection)
    blockers = _string_list(validation.get("blocking_reasons"))
    accepted = bool(validation.get("publishable"))
    return {
        "schema_version": STATUS_UPDATE_SCHEMA_VERSION,
        "accepted": accepted,
        "status": "accepted" if accepted else "rejected",
        "reason": "publishable" if accepted else _rejection_reason(blockers),
        "blocking_reasons": blockers,
        "projection_sha256": _projection_sha256(projection),
        "projection_object_sha256": projection_object_sha256(projection),
        "projection": projection,
        "projection_path": str(projection_out),
        "raw_bundle_sha256": str(validation.get("bundle_sha256")),
        "validator_version": VALIDATOR_VERSION,
        "validator_commit": validator_commit,
        "validated_at": validated_at,
    }


def _projection_sha256(projection: JsonObject) -> str:
    artifact_hashes = projection.get("artifact_hashes")
    if isinstance(artifact_hashes, dict) and isinstance(artifact_hashes.get("projection_sha256"), str):
        return artifact_hashes["projection_sha256"]
    return ""


def _rejection_reason(blockers: list[str]) -> str:
    return ";".join(blockers) if blockers else "validation_failed"


def _string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
