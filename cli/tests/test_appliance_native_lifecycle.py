from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.provisioner import ProvisioningError
from test_appliance_native_provisioner import _native_provisioner


def _write_runtime(root: Path, runtime_id: str, updated_at: str) -> None:
    runtime_dir = root / "native" / runtime_id
    marker = {
        "owner": "localbench",
        "runtime_id": runtime_id,
        "schema": "localbench.appliance_owner.v1",
    }
    (runtime_dir / "rootfs/etc").mkdir(parents=True)
    (runtime_dir / "rootfs/etc/localbench-appliance-owner.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    (runtime_dir / "state.json").write_text(
        json.dumps(
            {
                "schema": "localbench.appliance_state.v1",
                "runtime_id": runtime_id,
                "state": "canary-green",
                "updated_at": updated_at,
            }
        ),
        encoding="utf-8",
    )


def test_native_prune_preserves_newest_non_active_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, _boundary, _runtime_dir = _native_provisioner(tmp_path, monkeypatch)
    provisioner.ensure_active()
    _write_runtime(tmp_path, "runtime-oldest", "2026-01-01T00:00:00+00:00")
    _write_runtime(tmp_path, "runtime-newest", "2026-01-02T00:00:00+00:00")

    removed = provisioner.prune(pinned_runtime_id=PINNED_RUNTIME_ID)

    assert removed == ["runtime-oldest"]
    assert not (tmp_path / "native/runtime-oldest").exists()
    assert (tmp_path / "native/runtime-newest").exists()


def test_native_remove_refuses_mismatched_ownership_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, _boundary, runtime_dir = _native_provisioner(tmp_path, monkeypatch)
    provisioner.ensure_active()
    marker_path = runtime_dir / "rootfs/etc/localbench-appliance-owner.json"
    marker_path.write_text('{"owner":"someone-else"}', encoding="utf-8")

    with pytest.raises(ProvisioningError) as caught:
        provisioner.remove(PINNED_RUNTIME_ID, confirm_active=True)

    assert caught.value.code == "ownership_marker_mismatch"
    assert runtime_dir.exists()


def test_native_remove_cleans_partial_runtime_before_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provisioner, _boundary, _runtime_dir = _native_provisioner(tmp_path, monkeypatch)
    partial = tmp_path / "native/runtime-partial"
    partial.mkdir(parents=True)
    (partial / "state.json").write_text(
        json.dumps(
            {
                "schema": "localbench.appliance_state.v1",
                "runtime_id": "runtime-partial",
                "state": "downloading",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    provisioner.remove("runtime-partial")

    assert not partial.exists()
