from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_bytes, canonical_json_hash

_P: Final = 2**255 - 19
_Q: Final = 2**252 + 27742317777372353535851937790883648493
_D: Final = -121665 * pow(121666, _P - 2, _P) % _P
_I: Final = pow(2, (_P - 1) // 4, _P)
_OID: Final = b"\x06\x03\x2b\x65\x70"

Point = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Ed25519PrivateKey:
    seed: bytes
    public_key: bytes


def sign_manifest_payload(payload: JsonObject, signing_key_path: Path) -> JsonObject:
    key = load_private_key(signing_key_path)
    payload_bytes = canonical_json_bytes(payload)
    return {
        "algorithm": "Ed25519",
        "public_key": key.public_key.hex(),
        "signature": _sign(payload_bytes, key.seed, key.public_key).hex(),
    }


def sign_bytes(payload: bytes, signing_key_path: Path) -> str:
    key = load_private_key(signing_key_path)
    return _sign(payload, key.seed, key.public_key).hex()


def verify_manifest_signature(manifest: JsonObject) -> bool:
    payload = manifest.get("payload")
    signature = manifest.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        return False
    algorithm = signature.get("algorithm")
    public_key = signature.get("public_key")
    signature_hex = signature.get("signature")
    if algorithm != "Ed25519" or not isinstance(public_key, str) or not isinstance(signature_hex, str):
        return False
    try:
        public_bytes = bytes.fromhex(public_key)
        signature_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    return _verify(canonical_json_bytes(payload), signature_bytes, public_bytes)


def manifest_payload_sha(payload: JsonObject) -> str:
    return canonical_json_hash(payload)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    der = _pem_to_der(path.read_text(encoding="utf-8"))
    seed = _private_seed_from_der(der)
    public_key = _public_from_seed(seed)
    return Ed25519PrivateKey(seed=seed, public_key=public_key)


def _pem_to_der(pem: str) -> bytes:
    lines = [
        line.strip()
        for line in pem.splitlines()
        if line.strip() and not line.startswith("-----")
    ]
    return base64.b64decode("".join(lines), validate=True)


def _private_seed_from_der(der: bytes) -> bytes:
    if len(der) == 32:
        return der
    marker = der.rfind(b"\x04\x20")
    if _OID not in der or marker < 0 or marker + 34 > len(der):
        raise Ed25519KeyError("private key must be Ed25519 PKCS8 PEM")
    return der[marker + 2 : marker + 34]


class Ed25519KeyError(Exception):
    pass


def _public_from_seed(seed: bytes) -> bytes:
    a, _prefix = _secret_expand(seed)
    return _encode_point(_scalarmult(_base_point(), a))


def _sign(message: bytes, seed: bytes, public_key: bytes) -> bytes:
    a, prefix = _secret_expand(seed)
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _Q
    encoded_r = _encode_point(_scalarmult(_base_point(), r))
    k = int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(), "little") % _Q
    encoded_s = ((r + k * a) % _Q).to_bytes(32, "little")
    return encoded_r + encoded_s


def _verify(message: bytes, signature: bytes, public_key: bytes) -> bool:
    if len(signature) != 64 or len(public_key) != 32:
        return False
    public_point = _decode_point(public_key)
    r_point = _decode_point(signature[:32])
    if public_point is None or r_point is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % _Q
    left = _scalarmult(_base_point(), s)
    right = _edwards(r_point, _scalarmult(public_point, k))
    return left == right


def _secret_expand(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise Ed25519KeyError("private key seed must be 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _base_point() -> Point:
    y = 4 * pow(5, _P - 2, _P) % _P
    x = _recover_x(y, 0)
    if x is None:
        raise Ed25519KeyError("base point recovery failed")
    return x, y


def _recover_x(y: int, sign: int) -> int | None:
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _edwards(left: Point, right: Point) -> Point:
    x1, y1 = left
    x2, y2 = right
    denominator_x = pow(1 + _D * x1 * x2 * y1 * y2, _P - 2, _P)
    denominator_y = pow(1 - _D * x1 * x2 * y1 * y2, _P - 2, _P)
    x3 = (x1 * y2 + x2 * y1) * denominator_x % _P
    y3 = (y1 * y2 + x1 * x2) * denominator_y % _P
    return x3, y3


def _scalarmult(point: Point, scalar: int) -> Point:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _edwards(result, addend)
        addend = _edwards(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: Point) -> bytes:
    x, y = point
    bits = y.to_bytes(32, "little")
    return bits[:31] + bytes([bits[31] | ((x & 1) << 7)])


def _decode_point(data: bytes) -> Point | None:
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    sign = data[31] >> 7
    x = _recover_x(y, sign)
    if x is None:
        return None
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return x, y
