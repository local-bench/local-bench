from __future__ import annotations

from localbench._types import JsonObject, JsonValue
from localbench.submissions.submit_run_inputs import BundleInfo

SELF_REPORTED_LINE = "community submissions are labeled self-reported on the agentic axis"
REVIEW_LINE = "the maintainer reviews every submission before anything publishes."


def dry_run_lines(site: str, public_key: str, display_name: str | None, bundle: BundleInfo) -> list[str]:
    lines = [
        "dry-run   no network calls made",
        f"site      {site}",
        f"bundle    {bundle.path}",
        f"sha256    {bundle.sha256}",
        f"public_key {public_key}",
        f"suite     {bundle.suite_release_id}",
        f"manifest  {bundle.suite_manifest_sha256}",
    ]
    if display_name is not None:
        lines.append(f"display   {display_name}")
    if bundle.declared_model_slug is not None:
        lines.append(f"model     {bundle.declared_model_slug}")
    return lines


def summary_lines(status: JsonObject, fallback_submission_id: str) -> list[str]:
    submission_id = _text(status.get("submission_id")) or fallback_submission_id
    state = _text(status.get("status")) or "unknown"
    return [
        f"submission {submission_id}",
        f"status     {state}",
        f"agentic    {SELF_REPORTED_LINE}",
        f"review     {REVIEW_LINE}",
    ]


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None
