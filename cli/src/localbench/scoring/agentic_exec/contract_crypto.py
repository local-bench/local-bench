from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ContractPrivateKey(Protocol):
    public_key: bytes


def load_private_key(path: Path) -> ContractPrivateKey:
    from localbench.submissions.crypto import load_private_key as load

    return load(path)


def sign_bytes(payload: bytes, signing_key_path: Path) -> str:
    from localbench.submissions.crypto import sign_bytes as sign

    return sign(payload, signing_key_path)


def verify_bytes(payload: bytes, signature_hex: str, public_key_hex: str) -> bool:
    from localbench.submissions.crypto import verify_bytes as verify

    return verify(payload, signature_hex, public_key_hex)
