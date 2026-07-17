from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue

ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
ZIP_MODE: Final = 0o100644 << 16


def canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_hash(value: JsonValue) -> str:
    return sha256_bytes(canonical_json_bytes(value))


# Digests the server independently re-derives (projection object/semantic hashes) must be
# computed over bytes that survive a JSON round-trip through the Worker: JSON.parse drops
# the int/float distinction, so json.dumps float formatting ("0.0", "1e+16") diverges from
# JSON.stringify ("0", "10000000000000000") and the server 409s. These helpers reproduce
# ECMAScript number/string/key-order serialization exactly.
_JS_SAFE_INT_LIMIT: Final = 2**53


def jcs_json_bytes(value: JsonValue) -> bytes:
    return "".join(_jcs_fragments(value)).encode("utf-8")


def jcs_json_hash(value: JsonValue) -> str:
    return sha256_bytes(jcs_json_bytes(value))


def _jcs_fragments(value: JsonValue) -> list[str]:
    out: list[str] = []
    _emit_jcs(value, out)
    return out


def _emit_jcs(value: JsonValue, out: list[str]) -> None:
    if value is None or isinstance(value, (str, bool)):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, (int, float)):
        out.append(_ecma_number_str(value))
    elif isinstance(value, Sequence):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _emit_jcs(item, out)
        out.append("]")
    elif isinstance(value, Mapping):
        out.append("{")
        # JS Object.keys().sort() compares UTF-16 code units.
        for index, key in enumerate(sorted(value, key=lambda k: k.encode("utf-16-be"))):
            if index:
                out.append(",")
            out.append(json.dumps(key, ensure_ascii=False))
            out.append(":")
            _emit_jcs(value[key], out)
        out.append("}")
    else:
        raise TypeError(f"jcs canonical JSON does not support {type(value).__name__}")


def _ecma_number_str(value: int | float) -> str:
    if isinstance(value, int):
        if abs(value) >= _JS_SAFE_INT_LIMIT:
            raise ValueError(f"integer {value} exceeds the JS safe range; digest would diverge")
        return str(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("jcs canonical JSON only supports finite numbers")
    if value == 0.0:
        return "0"
    tup = Decimal(repr(value)).normalize().as_tuple()
    digits = "".join(map(str, tup.digits))
    k = len(digits)
    n = int(tup.exponent) + k
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        exponent = n - 1
        mantissa = digits[0] + ("." + digits[1:] if k > 1 else "")
        body = f"{mantissa}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"
    return ("-" if tup.sign else "") + body


def jsonl_bytes(records: Sequence[JsonObject]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SHA256_FILE_CHUNK: Final = 64 * 1024 * 1024


def sha256_file(path: Path) -> str:
    # Stream: read_bytes() needs the whole file in one allocation, which raised
    # MemoryError on an 18.3 GB GGUF at manifest collection after a completed
    # 21-hour run (2026-07-11). Digest output is unchanged.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_SHA256_FILE_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_file(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def deterministic_zip(path: Path, files: Mapping[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name in _zip_order(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = ZIP_MODE
            archive.writestr(info, files[name])


def _zip_order(files: Mapping[str, bytes]) -> tuple[str, ...]:
    preferred = ("manifest.json", "items.jsonl", "run.original.json", "attestations.jsonl", "environment.json")
    present = [name for name in preferred if name in files]
    extras = sorted(name for name in files if name not in preferred)
    return (*present, *extras)
