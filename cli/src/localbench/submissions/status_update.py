from __future__ import annotations

from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.landing import verify_coding_run
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.canon import write_json_file
from localbench.submissions.foundation import VALIDATOR_VERSION, validate_submission_bundle
from localbench.submissions.origin import normalize_origin
from localbench.submissions.projection import projection_object_sha256, rescore_admission_bundle

STATUS_UPDATE_SCHEMA_VERSION: Final = "localbench.submission_status_update.v1"
_CODING_VERIFIER_PUBLIC_KEY: Final = "63d52c31a16d5806a0de4dbbdcd8680e3960137bc044ba337d8d2f7572fccc60"


def verify_submission(
    bundle_path: Path,
    *,
    suite_dir: Path,
    projection_out: Path,
    validated_at: str,
    validator_commit: str | None,
    origin: str,
    coding_verified_path: Path | None = None,
) -> JsonObject:
    validation = validate_submission_bundle(bundle_path, suite_dir=suite_dir)
    loaded = load_result_bundle_input(bundle_path)
    coding_verification = (
        verify_coding_run(
            loaded.record,
            loaded.source_bytes,
            coding_verified_path,
            suite_dir=suite_dir,
            verifier_public_key=_CODING_VERIFIER_PUBLIC_KEY,
        )
        if coding_verified_path is not None
        else None
    )
    projection = rescore_admission_bundle(
        bundle_path,
        suite_dir=suite_dir,
        validated_at=validated_at,
        origin=normalize_origin(origin),
        coding_verification=coding_verification,
    )
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
