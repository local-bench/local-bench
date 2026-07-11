"""Combine an unsigned release payload with the returned offline signature."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from localbench.submissions.canon import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    signature = json.loads(args.signature.read_text(encoding="utf-8"))
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    document = {"payload": payload, "payload_sha256": digest, "signature": signature}
    args.out.write_bytes(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
