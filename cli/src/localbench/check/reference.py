from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from localbench._types import JsonObject
from localbench.check.types import ReferenceEdition
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import (
    sign_manifest_payload,
    verify_manifest_signature,
)

_EDITION_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")


class ReferenceEditionError(ValueError):
    pass


def create_reference_bundle(edition: ReferenceEdition, signing_key: Path) -> JsonObject:
    _validate_edition(edition)
    payload: JsonObject = {"schema_version": "localbench-reference-edition-v1", **edition.as_dict()}
    return {"payload": payload, "signature": sign_manifest_payload(payload, signing_key)}


def store_reference_bundle(store: Path, bundle: JsonObject) -> Path:
    payload = bundle.get("payload")
    edition_id = payload.get("edition_id") if isinstance(payload, dict) else None
    if not isinstance(edition_id, str) or _EDITION_ID.fullmatch(edition_id) is None:
        raise ReferenceEditionError("reference edition id is invalid")
    data = canonical_json_bytes(bundle) + b"\n"
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"{edition_id}.json"
    if path.exists():
        if path.read_bytes() != data:
            raise ReferenceEditionError(f"reference edition {edition_id!r} is immutable")
        return path
    _ = path.write_bytes(data)
    return path


def load_reference_bundle(path: Path, *, expected_public_key: str) -> ReferenceEdition:
    try:
        raw = path.read_bytes()
        parsed = cast(object, json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReferenceEditionError("reference bundle is not readable canonical JSON") from error
    if not isinstance(parsed, dict):
        raise ReferenceEditionError("reference bundle is not canonical JSON")
    document = cast(JsonObject, parsed)
    if raw != canonical_json_bytes(document) + b"\n":
        raise ReferenceEditionError("reference bundle is not canonical JSON")
    signature = document.get("signature")
    if (
        not isinstance(signature, dict)
        or signature.get("public_key") != expected_public_key
        or not verify_manifest_signature(document)
    ):
        raise ReferenceEditionError("reference bundle signature is invalid")
    payload = document.get("payload")
    if not isinstance(payload, dict) or payload.get("schema_version") != "localbench-reference-edition-v1":
        raise ReferenceEditionError("reference bundle schema is invalid")
    try:
        edition = ReferenceEdition(
            edition_id=_required(payload, "edition_id"),
            family=_required(payload, "family"),
            artifact_sha256=_sha(payload, "artifact_sha256"),
            tokenizer_sha256=_sha(payload, "tokenizer_sha256"),
            template_sha256=_sha(payload, "template_sha256"),
            class_label=_required(payload, "class_label"),
            created_utc=_required(payload, "created_utc"),
            checkset_edition=_required(payload, "checkset_edition"),
            execution_edition=_required(payload, "execution_edition"),
        )
    except (KeyError, TypeError) as error:
        raise ReferenceEditionError("reference bundle payload is invalid") from error
    _validate_edition(edition)
    return edition


def _validate_edition(edition: ReferenceEdition) -> None:
    if _EDITION_ID.fullmatch(edition.edition_id) is None:
        raise ReferenceEditionError("reference edition id is invalid")
    if edition.class_label not in {"BF16 source", "Q8 operational proxy", "Q5_K_M operational proxy"}:
        raise ReferenceEditionError("reference class label is invalid")
    for digest in (edition.artifact_sha256, edition.tokenizer_sha256, edition.template_sha256):
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ReferenceEditionError("reference edition digest is invalid")


def _required(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(key)
    return value


def _sha(payload: JsonObject, key: str) -> str:
    value = _required(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise TypeError(key)
    return value
