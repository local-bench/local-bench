from __future__ import annotations

import base64
import os
from pathlib import Path

from localbench.submissions.crypto import load_private_key

_PKCS8_ED25519_PREFIX = bytes.fromhex("302e020100300506032b657004220420")


def write_private_key(path: Path, seed: bytes | None = None) -> str:
    key_seed = seed or os.urandom(32)
    if len(key_seed) != 32:
        raise Ed25519SeedError("Ed25519 private key seed must be 32 bytes")
    path.write_text(_pem(_PKCS8_ED25519_PREFIX + key_seed), encoding="utf-8")
    return load_private_key(path).public_key.hex()


class Ed25519SeedError(Exception):
    pass


def _pem(der: bytes) -> str:
    encoded = base64.b64encode(der).decode("ascii")
    lines = "\n".join(encoded[index : index + 64] for index in range(0, len(encoded), 64))
    return f"-----BEGIN PRIVATE KEY-----\n{lines}\n-----END PRIVATE KEY-----\n"
