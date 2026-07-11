"""Offline-capable signer for a C1 canonical release digest.

This command reads only a signing request (domain, payload digest, key id) and
the private key. It does not need the release artifact, source tree, or network.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.appliance.manifest import MANIFEST_SIGNATURE_DOMAIN, RUNTIME_KEY_ID
from localbench.submissions.crypto import load_private_key, sign_bytes


def main() -> int:
    parser = argparse.ArgumentParser(prog="sign-runtime-release")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request != {
        "schema": "localbench.runtime_signing_request.v1",
        "domain": MANIFEST_SIGNATURE_DOMAIN.decode("ascii").rstrip("\n"),
        "key_id": RUNTIME_KEY_ID,
        "payload_sha256": request.get("payload_sha256"),
    }:
        raise ValueError("signing request contains unexpected fields or values")
    digest = bytes.fromhex(str(request["payload_sha256"]))
    if len(digest) != 32:
        raise ValueError("payload_sha256 must be 32 bytes")
    key = load_private_key(args.signing_key)
    envelope = {
        "algorithm": "Ed25519",
        "key_id": RUNTIME_KEY_ID,
        "public_key": key.public_key.hex(),
        "signature": sign_bytes(MANIFEST_SIGNATURE_DOMAIN + digest, args.signing_key),
    }
    args.out.write_bytes(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
