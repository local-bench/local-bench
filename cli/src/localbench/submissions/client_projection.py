from __future__ import annotations

from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.client import SubmissionEnvelope
from localbench.submissions.projection import client_reported_projection
from localbench.submissions.submit_run_inputs import _resolve_run_suite_dir


def build_client_reported_projection(
    bundle_path: Path,
    envelope: SubmissionEnvelope,
    *,
    suite_dir: Path | None,
    validated_at: str,
) -> JsonObject:
    record = load_result_bundle_input(bundle_path).record
    manifest = record.get("manifest")
    suite = manifest.get("suite") if isinstance(manifest, dict) else None
    projection_suite_dir = (
        suite_dir
        if suite_dir is not None
        else _resolve_run_suite_dir(suite if isinstance(suite, dict) else {})
    )
    return client_reported_projection(
        bundle_path,
        suite_dir=projection_suite_dir,
        validated_at=validated_at,
        origin=envelope["origin"],
    )
