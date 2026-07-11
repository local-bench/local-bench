"""Offline-capable signer for mutable C1 runtime trust metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.appliance.manifest import RUNTIME_KEY_ID
from localbench.appliance.trust import sign_trust_metadata
from localbench.submissions.canon import write_json_file


def main() -> int:
    parser = argparse.ArgumentParser(prog="sign-runtime-trust")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("trust payload must be a JSON object")
    write_json_file(
        args.out,
        sign_trust_metadata(payload, args.signing_key, key_id=RUNTIME_KEY_ID),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
