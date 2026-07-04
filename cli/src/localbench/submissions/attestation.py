from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_hash
from localbench.submissions.crypto import sign_manifest_payload, verify_manifest_signature

ATTESTATION_SCHEMA = "localbench.verdict_attestation.v1"
ATTESTATION_KEY_ID = "localbench-attester-2026-07"
# Production attester public key (localbench-attester-2026-07). The private key lives
# only on the project anchor machine and is never committed; rotating the key means
# adding a new key_id + constant, not editing history.
ATTESTER_PUBLIC_KEY_HEX: str | None = "c2325733eecbd7360080347520f46ad5f7a882b5b90add4219e8b306aca4dcde"


def sign_verdict_attestation(
    *,
    bench: str,
    task_id: str,
    run_id: str,
    verdict: JsonObject,
    signing_key_path: Path,
    attested_at: str | None = None,
    key_id: str = ATTESTATION_KEY_ID,
) -> JsonObject:
    payload: JsonObject = {
        "schema": ATTESTATION_SCHEMA,
        "bench": bench,
        "task_id": task_id,
        "run_id": run_id,
        "verdict": dict(verdict),
        "verdict_sha256": canonical_json_hash(verdict),
        "attested_at": attested_at or _utc_now(),
        "key_id": key_id,
    }
    return {
        "payload": payload,
        "payload_sha256": canonical_json_hash(payload),
        "signature": sign_manifest_payload(payload, signing_key_path),
    }


def verify_verdict_attestation(
    record: JsonObject,
    *,
    expected_public_key_hex: str | None = None,
) -> bool:
    expected = expected_attester_public_key_hex(expected_public_key_hex)
    if expected is None:
        return False
    payload = record.get("payload")
    signature = record.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        return False
    if not _payload_is_well_formed(payload):
        return False
    public_key = signature.get("public_key")
    if not isinstance(public_key, str) or public_key.lower() != expected.lower():
        return False
    if record.get("payload_sha256") != canonical_json_hash(payload):
        return False
    verdict = payload.get("verdict")
    if not isinstance(verdict, dict) or payload.get("verdict_sha256") != canonical_json_hash(verdict):
        return False
    return verify_manifest_signature({"payload": payload, "signature": signature})


def expected_attester_public_key_hex(override: str | None = None) -> str | None:
    return override or os.environ.get("LOCALBENCH_ATTESTER_PUBKEY") or ATTESTER_PUBLIC_KEY_HEX


def _payload_is_well_formed(payload: JsonObject) -> bool:
    verdict = payload.get("verdict")
    return (
        payload.get("schema") == ATTESTATION_SCHEMA
        and isinstance(payload.get("bench"), str)
        and isinstance(payload.get("task_id"), str)
        and isinstance(payload.get("run_id"), str)
        and isinstance(payload.get("attested_at"), str)
        and isinstance(payload.get("key_id"), str)
        and isinstance(payload.get("verdict_sha256"), str)
        and isinstance(verdict, dict)
        and isinstance(verdict.get("success"), bool)
        and isinstance(verdict.get("collateral_damage"), bool)
    )


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
