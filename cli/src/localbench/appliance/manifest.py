"""C1 signed runtime-manifest trust boundary.

The signature is checked over canonical JSON with a distinct domain before any
manifest URL, hash, or command is returned to the provisioner.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

from localbench._types import JsonObject
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.crypto import load_private_key, sign_bytes, verify_bytes

MANIFEST_SCHEMA: Final = "localbench.agentic_runtime_manifest.v1"
MANIFEST_SIGNATURE_DOMAIN: Final = b"localbench.agentic-runtime-manifest.v1\n"
PINNED_RUNTIME_ID: Final = "aw013p1-pypi28113a7a-ubuntu2404-py312-c0v3-r2"
RUNTIME_KEY_ID: Final = "localbench-runtime-root-2026-07"
RUNTIME_PUBLIC_KEYS: Final = {
    RUNTIME_KEY_ID: "46dd1ea90d4b227b45a8786189f68ed2657af539eb5ce6eda332287cee765ece"
}
# Filled from the accepted release evidence before publication. A non-matching
# manifest for the pinned runtime is rejected even when correctly signed.
PINNED_INITIAL_MANIFEST_SHA256: Final = ""
MANIFEST_URL: Final = (
    f"https://local-bench.ai/artifacts/agentic/{PINNED_RUNTIME_ID}/manifest.json"
)
ALLOWED_ARTIFACT_HOSTS: Final = frozenset(
    {"local-bench.ai", "files.pythonhosted.org", "s3.us-west-2.amazonaws.com"}
)
MAX_MANIFEST_BYTES: Final = 512 * 1024
MAX_ARTIFACT_BYTES: Final = 2 * 1024 * 1024 * 1024

REQUIRED_CRITICAL_HASHES: Final = (
    "worker_entrypoint_sha256",
    "worker_wheel_tree_sha256",
    "bubblewrap_sha256",
    "appworld_installed_tree_sha256",
    "appworld_data_tree_sha256",
    "wsl_conf_sha256",
)


@dataclass(slots=True)
class RuntimeManifestError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def signed_manifest(payload: JsonObject, signing_key: Path) -> JsonObject:
    key = load_private_key(signing_key)
    payload_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return {
        "payload": payload,
        "payload_sha256": payload_digest,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": RUNTIME_KEY_ID,
            "public_key": key.public_key.hex(),
            "signature": sign_bytes(
                MANIFEST_SIGNATURE_DOMAIN + bytes.fromhex(payload_digest), signing_key
            ),
        },
    }


def verify_manifest_bytes(
    raw: bytes,
    *,
    expected_runtime_id: str = PINNED_RUNTIME_ID,
    trust_state: JsonObject | None = None,
    expected_manifest_sha256: str | None = None,
) -> JsonObject:
    if len(raw) > MAX_MANIFEST_BYTES:
        raise RuntimeManifestError(
            "manifest_too_large", f"maximum is {MAX_MANIFEST_BYTES} bytes"
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeManifestError(
            "manifest_invalid", "manifest is not UTF-8 JSON"
        ) from error
    if not isinstance(document, dict):
        raise RuntimeManifestError(
            "manifest_invalid", "signed manifest must be an object"
        )
    if raw != canonical_json_bytes(document) + b"\n":
        raise RuntimeManifestError(
            "manifest_noncanonical",
            "presented bytes differ from canonical UTF-8 JSON encoding",
        )
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        raise RuntimeManifestError(
            "manifest_invalid", "payload/signature objects are required"
        )
    key_id = signature.get("key_id")
    trusted_keys = dict(RUNTIME_PUBLIC_KEYS)
    revoked: set[str] = set()
    killed: set[str] = set()
    if trust_state is not None:
        admitted = trust_state.get("admitted_keys", {})
        if isinstance(admitted, dict):
            trusted_keys.update(
                {str(key): str(value) for key, value in admitted.items()}
            )
        revoked = {str(value) for value in trust_state.get("revoked_key_ids", [])}
        killed = {
            str(value) for value in trust_state.get("kill_switched_runtime_ids", [])
        }
    trusted_key = trusted_keys.get(key_id) if isinstance(key_id, str) else None
    signature_hex = signature.get("signature")
    if (
        signature.get("algorithm") != "Ed25519"
        or signature.get("public_key") != trusted_key
        or not isinstance(signature_hex, str)
        or trusted_key is None
        or not verify_bytes(
            MANIFEST_SIGNATURE_DOMAIN
            + bytes.fromhex(hashlib.sha256(canonical_json_bytes(payload)).hexdigest()),
            signature_hex,
            trusted_key,
        )
    ):
        raise RuntimeManifestError(
            "manifest_signature_invalid", "untrusted or invalid signature"
        )
    if key_id in revoked:
        raise RuntimeManifestError("runtime_key_revoked", str(key_id))
    actual_payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    if document.get("payload_sha256") != actual_payload_sha:
        raise RuntimeManifestError("manifest_digest_invalid", "payload digest mismatch")
    _validate_payload(payload, expected_runtime_id=expected_runtime_id)
    if expected_runtime_id in killed:
        raise RuntimeManifestError("runtime_kill_switched", expected_runtime_id)
    pinned = expected_manifest_sha256
    if pinned is None and expected_runtime_id == PINNED_RUNTIME_ID:
        pinned = PINNED_INITIAL_MANIFEST_SHA256
    if pinned is not None and hashlib.sha256(raw).hexdigest() != pinned:
        raise RuntimeManifestError(
            "manifest_digest_unpinned", "manifest differs from the CLI-pinned release"
        )
    return payload


def _validate_payload(
    payload: JsonObject, *, expected_runtime_id: str
) -> None:
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeManifestError(
            "manifest_schema_unsupported", repr(payload.get("schema"))
        )
    if payload.get("runtime_id") != expected_runtime_id:
        raise RuntimeManifestError(
            "runtime_replay_or_downgrade",
            f"CLI pins {expected_runtime_id!r}, manifest has {payload.get('runtime_id')!r}",
        )
    artifact = _object(payload.get("rootfs"), "rootfs")
    _sha(artifact.get("sha256"), "rootfs.sha256")
    size = artifact.get("size_bytes")
    if not isinstance(size, int) or size <= 0 or size > MAX_ARTIFACT_BYTES:
        raise RuntimeManifestError("artifact_size_invalid", repr(size))
    _allowed_https_url(artifact.get("url"))
    if artifact.get("format") != "tar.xz":
        raise RuntimeManifestError(
            "archive_format_unsupported", repr(artifact.get("format"))
        )
    if artifact.get("uncompressed_size_bytes", 0) <= 0:
        raise RuntimeManifestError(
            "manifest_invalid", "rootfs.uncompressed_size_bytes is required"
        )
    for field in (
        "worker",
        "python",
        "bubblewrap",
        "appworld",
        "execution_contract_sha256",
        "task_identity",
        "canary_suite_id",
        "cli_compatibility",
        "critical_hashes",
        "provenance",
        "sbom",
        "protected_content_scan",
        "disk_requirements",
    ):
        if field not in payload:
            raise RuntimeManifestError("manifest_invalid", f"missing {field}")
    execution_digest = payload.get("execution_contract_sha256")
    _sha(execution_digest, "execution_contract_sha256")
    worker = _object(payload.get("worker"), "worker")
    _sha(worker.get("sha256"), "worker.sha256")
    if worker.get("protocol_version") != "localbench.agentic-worker.v1":
        raise RuntimeManifestError(
            "manifest_invalid", "worker.protocol_version is unsupported"
        )
    python = _object(payload.get("python"), "python")
    if not isinstance(python.get("version"), str):
        raise RuntimeManifestError("manifest_invalid", "python.version is required")
    bubblewrap = _object(payload.get("bubblewrap"), "bubblewrap")
    if not isinstance(bubblewrap.get("version"), str):
        raise RuntimeManifestError("manifest_invalid", "bubblewrap.version is required")
    appworld = _object(payload.get("appworld"), "appworld")
    if not isinstance(appworld.get("version"), str):
        raise RuntimeManifestError("manifest_invalid", "appworld.version is required")
    for digest_name in ("installed_tree_sha256", "data_tree_sha256"):
        _sha(appworld.get(digest_name), f"appworld.{digest_name}")
    package = _object(appworld.get("package"), "appworld.package")
    if not isinstance(package.get("filename"), str) or not str(
        package["filename"]
    ).endswith(".whl"):
        raise RuntimeManifestError(
            "manifest_invalid", "appworld.package.filename must be a wheel"
        )
    locks = _object(appworld.get("dependency_locks"), "appworld.dependency_locks")
    if set(locks) != {"x86_64"}:
        raise RuntimeManifestError(
            "manifest_invalid", "x86_64 dependency lock is required"
        )
    distribution = _object(
        appworld.get("data_distribution"), "appworld.data_distribution"
    )
    for item_name, item_value in (
        ("package", package),
        ("dependency_locks.x86_64", locks["x86_64"]),
        ("data_distribution", distribution),
    ):
        item = _object(item_value, f"appworld.{item_name}")
        _sha(item.get("sha256"), f"appworld.{item_name}.sha256")
        _allowed_https_url(item.get("url"))
        item_size = item.get("size_bytes")
        if (
            not isinstance(item_size, int)
            or item_size <= 0
            or item_size > MAX_ARTIFACT_BYTES
        ):
            raise RuntimeManifestError(
                "artifact_size_invalid", f"appworld.{item_name}={item_size!r}"
            )
    tasks = _object(payload.get("task_identity"), "task_identity")
    ids = tasks.get("ordered_task_ids")
    if (
        not isinstance(ids, list)
        or len(ids) != 96
        or not all(isinstance(item, str) for item in ids)
    ):
        raise RuntimeManifestError(
            "manifest_invalid", "exactly 96 ordered task IDs are required"
        )
    for field in (
        "ordered_task_ids_sha256",
        "selection_recipe_sha256",
        "semantic_task_sha256",
    ):
        _sha(tasks.get(field), f"task_identity.{field}")
    hashes = _object(payload.get("critical_hashes"), "critical_hashes")
    if set(hashes) != set(REQUIRED_CRITICAL_HASHES) or len(hashes) != len(
        REQUIRED_CRITICAL_HASHES
    ):
        raise RuntimeManifestError(
            "critical_hash_set_invalid", "enumerated set differs"
        )
    for name in REQUIRED_CRITICAL_HASHES:
        _sha(hashes.get(name), f"critical_hashes.{name}")
    scan = _object(payload.get("protected_content_scan"), "protected_content_scan")
    _sha(scan.get("sha256"), "protected_content_scan.sha256")


def _object(value: object, name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise RuntimeManifestError("manifest_invalid", f"{name} must be an object")
    return value


def _sha(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise RuntimeManifestError(
            "manifest_invalid", f"{name} must be 64 hex characters"
        )
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise RuntimeManifestError(
            "manifest_invalid", f"{name} is not hexadecimal"
        ) from error


def _allowed_https_url(value: object) -> None:
    if not isinstance(value, str):
        raise RuntimeManifestError("artifact_url_invalid", "URL must be a string")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_ARTIFACT_HOSTS:
        raise RuntimeManifestError(
            "artifact_url_disallowed",
            f"HTTPS host must be one of {sorted(ALLOWED_ARTIFACT_HOSTS)}",
        )
    if parsed.username or parsed.password or parsed.fragment:
        raise RuntimeManifestError(
            "artifact_url_invalid", "credentials/fragments are forbidden"
        )


def _public_key(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise RuntimeManifestError(
            "manifest_invalid", f"{name} must be a 32-byte hex key"
        )
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise RuntimeManifestError(
            "manifest_invalid", f"{name} is not hexadecimal"
        ) from error


__all__ = [
    "MANIFEST_SCHEMA",
    "MANIFEST_SIGNATURE_DOMAIN",
    "MANIFEST_URL",
    "MAX_ARTIFACT_BYTES",
    "MAX_MANIFEST_BYTES",
    "PINNED_RUNTIME_ID",
    "PINNED_INITIAL_MANIFEST_SHA256",
    "REQUIRED_CRITICAL_HASHES",
    "RuntimeManifestError",
    "signed_manifest",
    "verify_manifest_bytes",
]
