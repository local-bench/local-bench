from __future__ import annotations

from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.archive import unpack_bundle
from localbench.submissions.canon import write_json_file
from localbench.submissions.contracts import VERIFICATION_SCHEMA_VERSION
from localbench.submissions.crypto import verify_manifest_signature
from localbench.submissions.dedup import dedup_keys
from localbench.submissions.divergence import compare_client_divergence
from localbench.submissions.rescore import recompute_public_scores
from localbench.submissions.trust import offline_trust_state
from localbench.submissions.validate import (
    SubmissionValidationError,
    suite_item_index,
    validate_file_hashes,
    validate_item_contracts,
    validate_items_match_suite,
    validate_manifest_contract,
    validate_suite_and_scorecard,
)


def verify_bundle_offline(
    bundle_path: Path,
    *,
    suite_dir: Path,
    out_path: Path | None = None,
) -> JsonObject:
    bundle = unpack_bundle(bundle_path)
    payload = validate_manifest_contract(bundle.manifest)
    if not verify_manifest_signature(bundle.manifest):
        raise SubmissionValidationError("manifest signature verification failed")
    validate_file_hashes(bundle.manifest, bundle.files)
    validate_item_contracts(bundle.items)
    validate_suite_and_scorecard(payload, suite_dir)
    expected = suite_item_index(payload, suite_dir)
    validate_items_match_suite(bundle.items, expected)
    recomputed = recompute_public_scores(bundle.items, expected)
    divergence = compare_client_divergence(bundle.items, recomputed)
    trust = offline_trust_state()
    result: JsonObject = {
        "schema_version": VERIFICATION_SCHEMA_VERSION,
        "status": "accepted",
        "bundle_sha256": bundle.bundle_sha256,
        "submission_id": _submission_id(payload),
        "trust_label": trust["trust_label"],
        "publishable": trust["publishable"],
        "publishable_reasons": trust["publishable_reasons"],
        "recomputed": recomputed,
        "divergence": divergence,
        "dedup": dedup_keys(bundle.bundle_sha256, bundle.manifest, bundle.items),
        "audit": {
            "client_aggregates_ignored": True,
            "client_item_scores_ignored": True,
            "run_original_present": bundle.run_original is not None,
        },
    }
    if out_path is not None:
        write_json_file(out_path, result)
    return result


def _submission_id(payload: JsonObject) -> str:
    ticket = payload.get("ticket")
    if isinstance(ticket, dict) and isinstance(ticket.get("submission_id"), str):
        return ticket["submission_id"]
    return "offline-unknown"
