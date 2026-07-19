from __future__ import annotations

import json
import platform
from pathlib import Path

from localbench._types import JsonObject
from localbench.appliance.handshake import accept_handshake_identity
from localbench.appliance.native_inventory import NativeRuntimeInventory
from localbench.appliance.native_materialization import (
    materialize_rootfs,
    verify_materialized_rootfs,
)
from localbench.appliance.native_worker import NativeWorkerSpec, run_native_worker
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    ProvisioningError,
    _assert_file_hash,
    _atomic_bytes,
    _decode,
    _decompress_xz,
    _download_environment,
    runtime_lock,
)
from localbench.persistence import atomic_write_json


class NativeApplianceProvisioner:
    def __init__(self, owner: ApplianceProvisioner) -> None:
        self.owner = owner
        self.inventory = NativeRuntimeInventory(owner)

    def ensure_active(self, runtime_id: str) -> JsonObject:
        runtime_dir = self.owner.root / "native" / runtime_id
        with (
            runtime_lock(self.owner.root / "inventory.lock"),
            runtime_lock(self.owner.root / "locks" / f"{runtime_id}.lock"),
        ):
            runtime_dir.mkdir(parents=True, exist_ok=True)
            self._feature_preflight()
            state = self.owner._read_state(runtime_dir, runtime_id)
            verified = self.owner._resolve_manifest(runtime_dir, runtime_id)
            manifest = verified.payload
            self.owner._bind_manifest(runtime_dir, manifest, verified.raw)
            if state.get("state") == "active":
                rootfs = runtime_dir / "rootfs"
                verify_materialized_rootfs(rootfs, manifest)
                result = self._handshake(rootfs, manifest)
                active = self.owner._read_json(self.owner.root / "active.json")
                if active is None or active.get("runtime_id") != runtime_id:
                    self._activate(runtime_id)
                return result
            return self._resume(runtime_dir, state, manifest)

    def list_runtimes(self) -> list[JsonObject]:
        return self.inventory.list_runtimes()

    def remove(self, runtime_id: str, *, confirm_active: bool) -> None:
        self.inventory.remove(runtime_id, confirm_active=confirm_active)

    def prune(self, *, pinned_runtime_id: str) -> list[str]:
        return self.inventory.prune(pinned_runtime_id=pinned_runtime_id)

    def _resume(
        self, runtime_dir: Path, state: JsonObject, manifest: JsonObject
    ) -> JsonObject:
        runtime_id = str(manifest["runtime_id"])
        rootfs_info = manifest["rootfs"]
        if not isinstance(rootfs_info, dict):
            raise ProvisioningError("manifest_invalid", "rootfs", "Reprovision")
        archive = runtime_dir / f"localbench-agentic-runtime-{runtime_id}.tar.xz"
        rootfs = runtime_dir / "rootfs"
        current = str(state.get("state", "absent"))
        if current in {"absent", "downloading"}:
            self.owner._require_disk(
                runtime_dir, self._manifest_object(manifest, "disk_requirements")
            )
            self.owner._write_state(runtime_dir, runtime_id, "downloading")
            if hasattr(self.owner.downloader, "download_to"):
                self.owner.downloader.download_to(
                    str(rootfs_info["url"]),
                    archive,
                    exact_bytes=int(rootfs_info["size_bytes"]),
                )
            else:
                body = self.owner.downloader.get(
                    str(rootfs_info["url"]),
                    maximum_bytes=int(rootfs_info["size_bytes"]),
                )
                if len(body) != int(rootfs_info["size_bytes"]):
                    raise ProvisioningError(
                        "download_size_invalid",
                        str(len(body)),
                        "Use the signed artifact",
                    )
                _atomic_bytes(archive, body)
            current = "downloading"
        if current == "downloading":
            _assert_file_hash(archive, str(rootfs_info["sha256"]), "rootfs")
            self.owner._write_state(runtime_dir, runtime_id, "verified")
            current = "verified"
        if current == "verified":
            tar_archive = archive.with_suffix("")
            try:
                _decompress_xz(
                    archive,
                    tar_archive,
                    int(rootfs_info["uncompressed_size_bytes"]),
                )
                materialize_rootfs(tar_archive, rootfs, manifest)
            finally:
                tar_archive.unlink(missing_ok=True)
            self.owner._write_state(runtime_dir, runtime_id, "imported")
            current = "imported"
        if current == "imported":
            self._provision_appworld(rootfs, manifest)
            self.owner._write_state(runtime_dir, runtime_id, "provisioned")
            current = "provisioned"
        if current == "provisioned":
            self._run_canaries(rootfs)
            self.owner._write_state(runtime_dir, runtime_id, "canary-green")
            current = "canary-green"
        if current == "canary-green":
            verify_materialized_rootfs(rootfs, manifest)
            self._run_canaries(rootfs)
            result = self._handshake(rootfs, manifest)
            self.owner._write_state(runtime_dir, runtime_id, "active")
            self._activate(runtime_id)
            return result
        return self._handshake(rootfs, manifest)

    def _provision_appworld(self, rootfs: Path, manifest: JsonObject) -> None:
        environment = self._worker_environment()
        ca = self.owner.environ.get("LOCALBENCH_CA_BUNDLE")
        if ca:
            source = Path(ca).expanduser()
            destination = rootfs / "opt/localbench/ca/corporate-ca.pem"
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            destination.write_bytes(data)
            environment["SSL_CERT_FILE"] = "/opt/localbench/ca/corporate-ca.pem"
        document = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        result = run_native_worker(
            self.owner.runner,
            NativeWorkerSpec(
                rootfs=rootfs,
                command=("/opt/localbench/bin/provision-appworld", document),
                environment=environment,
                writable=True,
                network=True,
                timeout_s=1800,
            ),
        )
        if result.returncode != 0:
            raise ProvisioningError(
                "appworld_provision_failed", _decode(result.stderr), "Retry setup"
            )

    def _run_canaries(self, rootfs: Path) -> None:
        result = run_native_worker(
            self.owner.runner,
            NativeWorkerSpec(
                rootfs=rootfs,
                command=("/opt/localbench/bin/localbench-worker", "canary", "--full"),
                environment=self._worker_environment(),
                writable=False,
                network=False,
                timeout_s=600,
            ),
        )
        if result.returncode != 0:
            raise ProvisioningError(
                "runtime_canary_failed", _decode(result.stderr), "Reprovision"
            )

    def _handshake(self, rootfs: Path, manifest: JsonObject) -> JsonObject:
        result = run_native_worker(
            self.owner.runner,
            NativeWorkerSpec(
                rootfs=rootfs,
                command=(
                    "/opt/localbench/bin/localbench-worker",
                    "handshake",
                    "--json",
                ),
                environment=self._worker_environment(),
                writable=False,
                network=False,
                timeout_s=180,
            ),
        )
        try:
            identity = json.loads(_decode(result.stdout))
        except json.JSONDecodeError as error:
            raise ProvisioningError(
                "runtime_handshake_invalid", "non-JSON response", "Reprovision"
            ) from error
        if result.returncode != 0 or not isinstance(identity, dict):
            raise ProvisioningError(
                "runtime_handshake_failed", _decode(result.stderr), "Reprovision"
            )
        return accept_handshake_identity(manifest, identity)

    def _activate(self, runtime_id: str) -> None:
        atomic_write_json(
            {
                "schema": "localbench.appliance_active.v1",
                "runtime_id": runtime_id,
                "activated_at": _now(),
            },
            self.owner.root / "active.json",
        )

    def _feature_preflight(self) -> None:
        if platform.machine().lower() not in {"amd64", "x86_64"}:
            raise ProvisioningError(
                "unsupported_architecture", platform.machine(), "Use x86_64 Linux"
            )

    def _worker_environment(self) -> dict[str, str]:
        return {
            **_download_environment(self.owner.environ),
            "HOME": "/home/lbworker",
            "APPWORLD_ROOT": "/home/lbworker/appworld",
            "LOCALBENCH_RUNTIME_TOPOLOGY": "native-linux-bubblewrap",
            "PATH": "/opt/localbench/venv/bin:/usr/bin:/bin",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TZ": "UTC",
            "LC_ALL": "C.UTF-8",
        }

    @staticmethod
    def _manifest_object(manifest: JsonObject, key: str) -> JsonObject:
        value = manifest.get(key)
        if not isinstance(value, dict):
            raise ProvisioningError("manifest_invalid", key, "Reprovision")
        return value


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
