from __future__ import annotations

from pathlib import Path
import json

import pytest

from localbench.appliance import manifest as runtime_manifest
from localbench.appliance.manifest import (
    MANIFEST_SCHEMA,
    PINNED_RUNTIME_ID,
    REQUIRED_CRITICAL_HASHES,
    RuntimeManifestError,
    signed_manifest,
    verify_manifest_bytes,
)
from localbench.submissions.canon import canonical_json_bytes
from localbench.submissions.keys import write_private_key

SHA = "ab" * 32


def payload() -> dict[str, object]:
    critical = {name: SHA for name in REQUIRED_CRITICAL_HASHES}
    return {
        "schema": MANIFEST_SCHEMA,
        "runtime_id": PINNED_RUNTIME_ID,
        "rootfs": {
            "url": "https://local-bench.ai/artifacts/rootfs.tar.xz",
            "sha256": SHA,
            "size_bytes": 100,
            "uncompressed_size_bytes": 200,
            "format": "tar.xz",
        },
        "worker": {"sha256": SHA, "protocol_version": "localbench.agentic-worker.v1"},
        "python": {"version": "3.12.3"},
        "bubblewrap": {"version": "0.9.0"},
        "appworld": {
            "version": "0.1.3.post1",
            "installed_tree_sha256": SHA,
            "data_tree_sha256": SHA,
            "package": {
                "filename": "appworld-0.1.3.post1-py3-none-any.whl",
                "url": "https://local-bench.ai/artifacts/appworld.whl",
                "sha256": SHA,
                "size_bytes": 1,
            },
            "dependency_locks": {
                "x86_64": {
                    "url": "https://local-bench.ai/artifacts/appworld.lock",
                    "sha256": SHA,
                    "size_bytes": 1,
                }
            },
            "data_distribution": {
                "filename": "data-0.1.0.bundle",
                "url": "https://s3.us-west-2.amazonaws.com/appworld.dev/data-0.1.0.bundle",
                "sha256": SHA,
                "size_bytes": 1,
            },
        },
        "execution_contract_sha256": SHA,
        "task_identity": {
            "ordered_task_ids": [f"task-{index}" for index in range(96)],
            "ordered_task_ids_sha256": SHA,
            "selection_recipe_sha256": SHA,
            "semantic_task_sha256": SHA,
        },
        "canary_suite_id": "localbench-appliance-canaries-v1",
        "cli_compatibility": {"minimum": "0.4.0", "maximum_exclusive": "0.5.0"},
        "critical_hashes": critical,
        "provenance": {"sha256": SHA},
        "sbom": {"sha256": SHA},
        "protected_content_scan": {"sha256": SHA},
        "disk_requirements": {"peak_free_bytes": 3, "steady_free_bytes": 1, "download_bytes": 1, "import_bytes": 1, "provision_growth_bytes": 1},
    }


@pytest.fixture
def signer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    key = tmp_path / "runtime-root.pem"
    public = write_private_key(key, seed=bytes(range(32)))
    monkeypatch.setattr(
        runtime_manifest,
        "RUNTIME_PUBLIC_KEYS",
        {runtime_manifest.RUNTIME_KEY_ID: public},
    )
    return key


def encoded(document: dict[str, object]) -> bytes:
    return canonical_json_bytes(document) + b"\n"


def verified(document: dict[str, object], **kwargs):
    raw = encoded(document)
    import hashlib
    return verify_manifest_bytes(raw, expected_manifest_sha256=hashlib.sha256(raw).hexdigest(), **kwargs)


def test_manifest_signature_domain_and_payload_validate(signer: Path) -> None:
    document = signed_manifest(payload(), signer)
    assert verified(document)["runtime_id"] == PINNED_RUNTIME_ID


def test_signature_is_checked_before_tampered_url_is_considered(signer: Path) -> None:
    document = signed_manifest(payload(), signer)
    document["payload"]["rootfs"]["url"] = "https://evil.invalid/rootfs.tar.xz"  # type: ignore[index]
    with pytest.raises(RuntimeManifestError) as caught:
        verified(document)
    assert caught.value.code == "manifest_signature_invalid"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value.update(runtime_id="older-valid-runtime"),
            "runtime_replay_or_downgrade",
        ),
        (
            lambda value: value["rootfs"].update(url="https://evil.invalid/a.tar.xz"),
            "artifact_url_disallowed",
        ),
        (
            lambda value: value["rootfs"].update(
                size_bytes=runtime_manifest.MAX_ARTIFACT_BYTES + 1
            ),
            "artifact_size_invalid",
        ),
    ],
)
def test_signed_policy_failures_are_typed(signer: Path, mutation, code: str) -> None:
    value = payload()
    mutation(value)
    with pytest.raises(RuntimeManifestError) as caught:
        verified(signed_manifest(value, signer))
    assert caught.value.code == code


def test_manifest_rejects_builder_selected_critical_subset(signer: Path) -> None:
    value = payload()
    value["critical_hashes"].pop("wsl_conf_sha256")  # type: ignore[union-attr]
    with pytest.raises(RuntimeManifestError, match="enumerated set"):
        verified(signed_manifest(value, signer))


@pytest.mark.parametrize(
    ("trust_state", "code"),
    [
        ({"admitted_keys": {}, "revoked_key_ids": [], "kill_switched_runtime_ids": [PINNED_RUNTIME_ID]}, "runtime_kill_switched"),
        ({"admitted_keys": {}, "revoked_key_ids": [runtime_manifest.RUNTIME_KEY_ID], "kill_switched_runtime_ids": []}, "runtime_key_revoked"),
    ],
)
def test_mutable_trust_policy_is_separate_from_manifest(signer: Path, trust_state, code: str) -> None:
    with pytest.raises(RuntimeManifestError) as caught:
        verified(signed_manifest(payload(), signer), trust_state=trust_state)
    assert caught.value.code == code


def test_manifest_size_bound_precedes_json_parse() -> None:
    with pytest.raises(RuntimeManifestError) as caught:
        verify_manifest_bytes(b"{" + b" " * runtime_manifest.MAX_MANIFEST_BYTES)
    assert caught.value.code == "manifest_too_large"


@pytest.mark.parametrize(
    "noncanonical",
    [
        lambda document: json.dumps(document, sort_keys=False, separators=(",", ":")).encode() + b"\n",
        lambda document: json.dumps(document, sort_keys=True, indent=2).encode() + b"\n",
        lambda document: json.dumps(document, sort_keys=True, ensure_ascii=True, separators=(",", ":")).replace("localbench", "local\\u0062ench", 1).encode() + b"\n",
        lambda document: json.dumps({**document, "noncanonical_float": 1.0}, sort_keys=True, separators=(",", ":")).replace('"noncanonical_float":1.0', '"noncanonical_float":1e0').encode() + b"\n",
    ],
    ids=["reordered-keys", "whitespace", "unicode-escape", "float-form"],
)
def test_manifest_rejects_noncanonical_presented_bytes(signer: Path, noncanonical) -> None:
    document = signed_manifest(payload(), signer)
    raw = noncanonical(document)
    with pytest.raises(RuntimeManifestError) as caught:
        verify_manifest_bytes(raw, expected_manifest_sha256=__import__("hashlib").sha256(raw).hexdigest())
    assert caught.value.code == "manifest_noncanonical"
