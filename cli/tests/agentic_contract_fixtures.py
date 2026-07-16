from __future__ import annotations

from pathlib import Path

import pytest

from localbench._types import JsonObject
from localbench.scoring.agentic_exec import execution_contract, rank_gate
from localbench.scoring.agentic_exec.execution_contract import CONTRACT_SIGNATURE_DOMAIN
from localbench.submissions.canon import (
    canonical_json_bytes,
    canonical_json_hash,
    write_json_file,
)
from localbench.submissions.crypto import load_private_key, sign_bytes
from localbench.submissions.keys import write_private_key
from scripts.build_contract_v4_payload import (
    BASE_CONTRACT_ID,
    V4_CONTRACT_ID,
    build_v4_payload,
)

TEST_ONLY_CONTRACT_KEY_ID = "localbench-test-only-c6-do-not-trust"


def write_test_signed_v4_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: JsonObject | None = None,
) -> Path:
    value = payload or build_v4_payload(
        gate_status="passed-current-repo-harness-vs-appliance"
    )
    key_path = tmp_path / "test-only-c6-contract-key.pem"
    write_private_key(key_path, seed=bytes(range(32)))
    key = load_private_key(key_path)
    contract: JsonObject = {
        "payload": value,
        "payload_sha256": canonical_json_hash(value),
        "signature": {
            "key_id": TEST_ONLY_CONTRACT_KEY_ID,
            "algorithm": "Ed25519",
            "public_key": key.public_key.hex(),
            "signature": sign_bytes(
                CONTRACT_SIGNATURE_DOMAIN + canonical_json_bytes(value),
                key_path,
            ),
        },
    }
    monkeypatch.setattr(
        execution_contract,
        "CONTRACT_PUBLIC_KEYS",
        {
            **execution_contract.CONTRACT_PUBLIC_KEYS,
            TEST_ONLY_CONTRACT_KEY_ID: key.public_key.hex(),
        },
    )
    monkeypatch.setattr(rank_gate, "CONTRACT_ID", BASE_CONTRACT_ID)
    path = tmp_path / f"{V4_CONTRACT_ID}.test-signed.json"
    write_json_file(path, contract)
    return path
