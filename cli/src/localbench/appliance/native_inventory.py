from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from localbench._types import JsonObject
from localbench.appliance.native_materialization import assert_native_ownership
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    ProvisioningError,
    runtime_lock,
)


class NativeRuntimeInventory:
    def __init__(self, owner: ApplianceProvisioner) -> None:
        self.owner = owner

    def list_runtimes(self) -> list[JsonObject]:
        base = self.owner.root / "native"
        if not base.exists():
            return []
        result: list[JsonObject] = []
        for path in sorted(base.iterdir()):
            if path.name.startswith("."):
                continue
            state = self.owner._read_json(path / "state.json")
            if state is not None:
                result.append(state)
        return result

    def remove(self, runtime_id: str, *, confirm_active: bool) -> None:
        runtime_dir = self.owner.root / "native" / runtime_id
        if not (runtime_dir / "state.json").exists():
            return
        tombstone: Path | None = None
        with (
            runtime_lock(self.owner.root / "inventory.lock"),
            runtime_lock(self.owner.root / "locks" / f"{runtime_id}.lock"),
        ):
            state = self.owner._read_json(runtime_dir / "state.json")
            if state is None:
                return
            pointer = self.owner.root / "active.json"
            active = self.owner._read_json(pointer)
            is_active = active is not None and active.get("runtime_id") == runtime_id
            if is_active and not confirm_active:
                raise ProvisioningError(
                    "active_runtime_confirmation_required",
                    runtime_id,
                    "Repeat with --confirm-active",
                )
            rootfs = runtime_dir / "rootfs"
            if rootfs.exists():
                assert_native_ownership(rootfs, runtime_id)
            if is_active:
                pointer.unlink(missing_ok=True)
            tombstone = runtime_dir.with_name(
                f".{runtime_id}.removed-{os.getpid()}-{time.time_ns()}"
            )
            os.replace(runtime_dir, tombstone)
        if tombstone is not None:
            shutil.rmtree(tombstone)

    def prune(self, *, pinned_runtime_id: str) -> list[str]:
        active = self.owner._read_json(self.owner.root / "active.json") or {}
        runtimes = self.list_runtimes()
        pinned = next(
            (item for item in runtimes if item.get("runtime_id") == pinned_runtime_id),
            None,
        )
        if pinned is None or not isinstance(pinned.get("updated_at"), str):
            return []
        candidates = [
            (str(item.get("updated_at", "")), str(item["runtime_id"]))
            for item in runtimes
            if item.get("runtime_id")
            not in {active.get("runtime_id"), pinned_runtime_id}
            and item.get("state") != "active"
            and isinstance(item.get("updated_at"), str)
            and str(item["updated_at"]) < str(pinned["updated_at"])
        ]
        removed: list[str] = []
        for _updated_at, runtime_id in sorted(candidates, reverse=True)[1:]:
            self.remove(runtime_id, confirm_active=False)
            removed.append(runtime_id)
        return removed
