"""Offline-capable signer for mutable C1 runtime trust metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.appliance.manifest import RUNTIME_PUBLIC_KEYS
from localbench.appliance.trust import sign_trust_metadata
from localbench.submissions.canon import write_json_file
from localbench.submissions.crypto import load_private_key


def main() -> int:
    parser = argparse.ArgumentParser(prog="sign-runtime-trust")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trust payload must be a JSON object")
    # The key id is derived from the signing key itself, never assumed — a key whose
    # public half is absent from the client trust map cannot be stamped with a
    # trusted id (same discipline as signed_manifest/signed_contract).
    public_key = load_private_key(args.signing_key).public_key.hex()
    key_id = next(
        (kid for kid, pub in RUNTIME_PUBLIC_KEYS.items() if pub == public_key), None
    )
    if key_id is None:
        raise ValueError("signing key is not registered in RUNTIME_PUBLIC_KEYS")
    write_json_file(
        args.out,
        sign_trust_metadata(payload, args.signing_key, key_id=key_id),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
