from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from localbench.appliance.manifest import MANIFEST_SIGNATURE_DOMAIN
from localbench.appliance.trust import (
    TRUST_SCHEMA,
    TRUST_SIGNATURE_DOMAIN,
    TrustMetadataError,
    admit_trust_metadata,
    sign_trust_metadata,
)
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import sign_bytes, verify_bytes
from localbench.submissions.keys import write_private_key


def test_rotated_keys_are_persisted_and_trust_rollback_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root.pem"
    root_public = write_private_key(root, seed=bytes(range(32)))
    rotated = tmp_path / "rotated.pem"
    rotated_public = write_private_key(rotated, seed=bytes(reversed(range(32))))
    payload = {
        "schema": TRUST_SCHEMA,
        "sequence": 7,
        "admitted_keys": [{"key_id": "rotated-1", "public_key": rotated_public}],
        "revoked_key_ids": [],
        "kill_switched_runtime_ids": [],
    }
    raw = canonical_json_bytes(sign_trust_metadata(payload, root, key_id="root")) + b"\n"
    state_path = tmp_path / "trust-state.json"
    state = admit_trust_metadata(raw, embedded_roots={"root": root_public}, state_path=state_path)
    assert state["admitted_keys"] == {"rotated-1": rotated_public}
    older = dict(payload, sequence=6)
    with pytest.raises(TrustMetadataError, match="rollback"):
        admit_trust_metadata(canonical_json_bytes(sign_trust_metadata(older, root, key_id="root")), embedded_roots={"root": root_public}, state_path=state_path)


def test_fixed_seed_cross_domain_signature_is_rejected(tmp_path: Path) -> None:
    key = tmp_path / "key.pem"
    public = write_private_key(key, seed=bytes(range(32)))
    digest = hashlib.sha256(b"fixed release vector").digest()
    signature = sign_bytes(MANIFEST_SIGNATURE_DOMAIN + digest, key)
    assert verify_bytes(MANIFEST_SIGNATURE_DOMAIN + digest, signature, public)
    assert not verify_bytes(TRUST_SIGNATURE_DOMAIN + digest, signature, public)


def test_same_sequence_retarget_and_key_id_retarget_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root.pem"
    root_public = write_private_key(root, seed=bytes(range(32)))
    state_path = tmp_path / "state.json"
    base = {
        "schema": TRUST_SCHEMA,
        "sequence": 1,
        "admitted_keys": [{"key_id": "next", "public_key": "11" * 32}],
        "revoked_key_ids": [],
        "kill_switched_runtime_ids": [],
    }
    raw = canonical_json_bytes(sign_trust_metadata(base, root, key_id="root"))
    admit_trust_metadata(raw, embedded_roots={"root": root_public}, state_path=state_path)
    assert admit_trust_metadata(
        raw, embedded_roots={"root": root_public}, state_path=state_path
    )["sequence"] == 1
    changed = dict(base, kill_switched_runtime_ids=["runtime"])
    with pytest.raises(TrustMetadataError, match="sequence retarget"):
        admit_trust_metadata(
            canonical_json_bytes(sign_trust_metadata(changed, root, key_id="root")),
            embedded_roots={"root": root_public},
            state_path=state_path,
        )
    retarget = dict(base, sequence=2, admitted_keys=[{"key_id": "next", "public_key": "22" * 32}])
    with pytest.raises(TrustMetadataError, match="key ID retarget"):
        admit_trust_metadata(
            canonical_json_bytes(sign_trust_metadata(retarget, root, key_id="root")),
            embedded_roots={"root": root_public},
            state_path=state_path,
        )


def test_revocation_and_kill_switch_are_monotonic(tmp_path: Path) -> None:
    root = tmp_path / "root.pem"
    root_public = write_private_key(root, seed=bytes(range(32)))
    state_path = tmp_path / "state.json"
    for sequence, revoked, killed in ((1, ["old-key"], ["old-runtime"]), (2, [], [])):
        payload = {
            "schema": TRUST_SCHEMA,
            "sequence": sequence,
            "admitted_keys": [],
            "revoked_key_ids": revoked,
            "kill_switched_runtime_ids": killed,
        }
        state = admit_trust_metadata(
            canonical_json_bytes(sign_trust_metadata(payload, root, key_id="root")),
            embedded_roots={"root": root_public},
            state_path=state_path,
        )
    assert state["revoked_key_ids"] == ["old-key"]
    assert state["kill_switched_runtime_ids"] == ["old-runtime"]
