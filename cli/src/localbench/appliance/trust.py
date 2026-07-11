"""Mutable runtime trust metadata, independently signed by the embedded root."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.persistence import atomic_write_json
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import sign_bytes, verify_bytes

TRUST_SCHEMA: Final = "localbench.agentic_runtime_trust.v1"
TRUST_SIGNATURE_DOMAIN: Final = b"localbench.agentic-runtime-trust.v1\n"
TRUST_URL: Final = "https://local-bench.ai/artifacts/agentic/trust-v1.json"
MAX_TRUST_BYTES: Final = 256 * 1024


class TrustMetadataError(ValueError):
    pass


def sign_trust_metadata(payload: JsonObject, key_path: Path, *, key_id: str) -> JsonObject:
    from localbench.submissions.crypto import load_private_key

    key = load_private_key(key_path)
    body = canonical_json_bytes(payload)
    return {
        "payload": payload,
        "payload_sha256": hashlib.sha256(body).hexdigest(),
        "signature": {
            "algorithm": "Ed25519",
            "key_id": key_id,
            "public_key": key.public_key.hex(),
            "signature": sign_bytes(TRUST_SIGNATURE_DOMAIN + body, key_path),
        },
    }


def admit_trust_metadata(
    raw: bytes,
    *,
    embedded_roots: dict[str, str],
    state_path: Path,
) -> JsonObject:
    if len(raw) > MAX_TRUST_BYTES:
        raise TrustMetadataError("trust metadata exceeds byte limit")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrustMetadataError("trust metadata is not UTF-8 JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("payload"), dict):
        raise TrustMetadataError("trust payload object required")
    payload: JsonObject = document["payload"]
    signature = document.get("signature")
    if not isinstance(signature, dict):
        raise TrustMetadataError("trust signature object required")
    key_id = signature.get("key_id")
    public_key = embedded_roots.get(key_id) if isinstance(key_id, str) else None
    body = canonical_json_bytes(payload)
    if (
        signature.get("algorithm") != "Ed25519"
        or signature.get("public_key") != public_key
        or not isinstance(signature.get("signature"), str)
        or public_key is None
        or not verify_bytes(
            TRUST_SIGNATURE_DOMAIN + body, str(signature["signature"]), public_key
        )
        or document.get("payload_sha256") != hashlib.sha256(body).hexdigest()
    ):
        raise TrustMetadataError("trust signature is invalid")
    _validate_payload(payload)
    previous = _read_state(state_path)
    sequence = int(payload["sequence"])
    if previous is not None:
        previous_sequence = int(previous["sequence"])
        if sequence < previous_sequence:
            raise TrustMetadataError("trust metadata rollback refused")
        if sequence == previous_sequence:
            if previous.get("metadata_sha256") == hashlib.sha256(raw).hexdigest():
                return previous
            raise TrustMetadataError("trust metadata sequence retarget refused")
    admitted = dict(previous.get("admitted_keys", {})) if previous else {}
    for item in payload["admitted_keys"]:
        admitted_id = str(item["key_id"])
        admitted_key = str(item["public_key"])
        if admitted_id in admitted and admitted[admitted_id] != admitted_key:
            raise TrustMetadataError("admitted key ID retarget refused")
        admitted[admitted_id] = admitted_key
    revoked = set(previous.get("revoked_key_ids", ())) if previous else set()
    revoked.update(str(item) for item in payload["revoked_key_ids"])
    killed = set(previous.get("kill_switched_runtime_ids", ())) if previous else set()
    killed.update(str(item) for item in payload["kill_switched_runtime_ids"])
    state: JsonObject = {
        "schema": "localbench.agentic_runtime_trust_state.v1",
        "sequence": sequence,
        "admitted_keys": admitted,
        "revoked_key_ids": sorted(revoked),
        "kill_switched_runtime_ids": sorted(killed),
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
    }
    atomic_write_json(state, state_path)
    return state


def _validate_payload(payload: JsonObject) -> None:
    if payload.get("schema") != TRUST_SCHEMA or not isinstance(payload.get("sequence"), int):
        raise TrustMetadataError("unsupported trust schema/sequence")
    for field in ("revoked_key_ids", "kill_switched_runtime_ids"):
        value = payload.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise TrustMetadataError(f"{field} must contain strings")
    admitted = payload.get("admitted_keys")
    if not isinstance(admitted, list):
        raise TrustMetadataError("admitted_keys must be a list")
    for item in admitted:
        if not isinstance(item, dict) or not isinstance(item.get("key_id"), str):
            raise TrustMetadataError("admitted key_id is invalid")
        try:
            key = bytes.fromhex(str(item.get("public_key")))
        except ValueError as error:
            raise TrustMetadataError("admitted public key is invalid") from error
        if len(key) != 32:
            raise TrustMetadataError("admitted public key is invalid")


def _read_state(path: Path) -> JsonObject | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise TrustMetadataError("persisted trust state is invalid")
    return value
