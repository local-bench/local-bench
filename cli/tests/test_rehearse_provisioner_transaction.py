from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from localbench.appliance.manifest import RuntimeManifestError

MODULE_PATH = Path(__file__).parents[1] / "tools" / "rehearse_provisioner_transaction.py"
SPEC = importlib.util.spec_from_file_location("rehearse_provisioner_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
rehearsal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rehearsal)


def test_rehearsal_manifest_uses_production_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    raw = b"canonical signed bytes\n"
    path.write_bytes(raw)
    observed: list[bytes] = []

    def verify(value: bytes) -> dict[str, object]:
        observed.append(value)
        return {"runtime_id": "verified"}

    monkeypatch.setattr(rehearsal, "verify_manifest_bytes", verify)
    assert rehearsal._verified_manifest(path) == {"runtime_id": "verified"}
    assert observed == [raw]


def test_rehearsal_aborts_when_production_manifest_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"tampered\n")

    def reject(_raw: bytes) -> dict[str, object]:
        raise RuntimeManifestError("manifest_digest_unpinned", "pin mismatch")

    monkeypatch.setattr(rehearsal, "verify_manifest_bytes", reject)
    with pytest.raises(RuntimeError, match="manifest_digest_unpinned"):
        rehearsal._verified_manifest(path)
