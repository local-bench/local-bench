"""Transactional C2 Windows-side provisioner for the managed WSL2 runtime."""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import lzma
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

import httpx

from localbench._types import JsonObject
from localbench.appliance.manifest import (
    MANIFEST_URL,
    MAX_MANIFEST_BYTES,
    PINNED_RUNTIME_ID,
    REQUIRED_CRITICAL_HASHES,
    RUNTIME_PUBLIC_KEYS,
    RuntimeManifestError,
    verify_manifest_bytes,
)
from localbench.appliance.trust import (
    MAX_TRUST_BYTES,
    TRUST_URL,
    TrustMetadataError,
    admit_trust_metadata,
)
from localbench.persistence import atomic_write_bytes, atomic_write_json
from localbench.submissions.canon import canonical_json_hash

STATE_ORDER: Final = (
    "absent",
    "downloading",
    "verified",
    "imported",
    "provisioned",
    "canary-green",
    "active",
)
OWNERSHIP_MARKER: Final = "/etc/localbench-appliance-owner.json"
FINAL_DISTRO_PREFIX: Final = "LocalBench-Agentic-"
STAGING_DISTRO_PREFIX: Final = "LocalBench-Staging-"
MIN_WINDOWS_BUILD: Final = (
    22000  # Windows 11 initial x64 release; feature probes remain authoritative.
)
MIN_STORE_WSL: Final = (2, 6, 3, 0)  # Conservative baseline measured on 2026-07-11.
WSL_CONF: Final = """[automount]
enabled=false
mountFsTab=false

[interop]
enabled=false
appendWindowsPath=false

[user]
default=lbworker
"""


@dataclass(slots=True)
class ProvisioningError(Exception):
    code: str
    detail: str
    remediation: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}. {self.remediation}"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


class CommandRunner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, timeout: float | None = None
    ) -> CommandResult: ...


class Downloader(Protocol):
    def get(self, url: str, *, maximum_bytes: int) -> bytes: ...

    def download_to(self, url: str, path: Path, *, exact_bytes: int) -> None: ...


class HttpDownloader:
    def __init__(self, *, ca_bundle: Path | None = None) -> None:
        verify: ssl.SSLContext | bool = True
        if ca_bundle is not None:
            verify = ssl.create_default_context(cafile=str(ca_bundle))
        self._client = httpx.Client(
            follow_redirects=False, timeout=120, verify=verify, trust_env=True
        )

    def get(self, url: str, *, maximum_bytes: int) -> bytes:
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared is not None and int(declared) > maximum_bytes:
                    raise ProvisioningError(
                        "download_too_large",
                        declared,
                        "Check the signed release manifest",
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > maximum_bytes:
                        raise ProvisioningError(
                            "download_too_large",
                            f"stream exceeded {maximum_bytes} bytes",
                            "Check the signed release manifest",
                        )
                return bytes(body)
        except (httpx.HTTPError, OSError, ValueError) as error:
            raise ProvisioningError(
                "download_failed",
                str(error),
                "Check HTTPS_PROXY/NO_PROXY or pass --ca-bundle for your corporate CA",
            ) from error

    def download_to(self, url: str, path: Path, *, exact_bytes: int) -> None:
        temporary = path.with_suffix(path.suffix + ".partial")
        total = 0
        try:
            with self._client.stream("GET", url) as response, temporary.open("wb") as output:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared is not None and int(declared) != exact_bytes:
                    raise ProvisioningError("download_size_invalid", declared, "Check the signed release manifest")
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > exact_bytes:
                        raise ProvisioningError("download_too_large", str(total), "Check the signed release manifest")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if total != exact_bytes:
                raise ProvisioningError("download_size_invalid", str(total), "Discard the partial download and retry")
            _replace_retry(temporary, path)
        except OSError as error:
            if error.errno == errno.ENOSPC:
                raise _disk_error(error) from error
            raise ProvisioningError("download_failed", str(error), "Check disk space, proxy, or CA settings") from error
        finally:
            temporary.unlink(missing_ok=True)


def subprocess_runner(
    argv: Sequence[str], *, timeout: float | None = None
) -> CommandResult:
    completed = subprocess.run(
        list(argv), capture_output=True, check=False, timeout=timeout
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class ApplianceProvisioner:
    def __init__(
        self,
        *,
        root: Path | None = None,
        runner: CommandRunner = subprocess_runner,
        downloader: Downloader | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.root = root or appliance_root(self.environ)
        self.runner = runner
        ca_value = self.environ.get("LOCALBENCH_CA_BUNDLE")
        self.downloader = downloader or HttpDownloader(
            ca_bundle=Path(ca_value).expanduser() if ca_value else None
        )

    def ensure_active(self, runtime_id: str = PINNED_RUNTIME_ID) -> JsonObject:
        _validate_runtime_id(runtime_id)
        validate_storage_root(self.root, self.environ)
        runtime_dir = self.root / "WSL" / runtime_id
        with runtime_lock(self.root / "inventory.lock"):
            with runtime_lock(self.root / "locks" / f"{runtime_id}.lock"):
                runtime_dir.mkdir(parents=True, exist_ok=True)
                self._feature_preflight()
                state = self._read_state(runtime_dir, runtime_id)
                manifest = self._fetch_manifest()
                self._bind_manifest(runtime_dir, manifest)
                if state.get("state") == "active":
                    result = self._handshake(runtime_dir, state, manifest)
                    active = self._read_json(self.root / "active.json")
                    if active is None or active.get("runtime_id") != runtime_id:
                        atomic_write_json(
                            {
                                "schema": "localbench.appliance_active.v1",
                                "runtime_id": runtime_id,
                                "distro_name": state.get("distro_name"),
                                "activated_at": _now(),
                            },
                            self.root / "active.json",
                        )
                    return result
                return self._resume(runtime_dir, state, manifest)

    def list_runtimes(self) -> list[JsonObject]:
        base = self.root / "WSL"
        if not base.exists():
            return []
        result: list[JsonObject] = []
        for path in sorted(base.iterdir()):
            if path.name.startswith("."):
                continue
            state = self._read_json(path / "state.json")
            if state is not None:
                result.append(state)
        return result

    def remove(self, runtime_id: str, *, confirm_active: bool = False) -> None:
        _validate_runtime_id(runtime_id)
        runtime_dir = self.root / "WSL" / runtime_id
        if not (runtime_dir / "state.json").exists():
            return
        tombstone: Path | None = None
        with runtime_lock(self.root / "inventory.lock"), runtime_lock(self.root / "locks" / f"{runtime_id}.lock"):
            state = self._read_json(runtime_dir / "state.json")
            if state is None:
                return
            pointer = self.root / "active.json"
            active = self._read_json(pointer)
            is_active = active is not None and active.get("runtime_id") == runtime_id
            if is_active and not confirm_active:
                raise ProvisioningError(
                    "active_runtime_confirmation_required",
                    runtime_id,
                    "Repeat with --confirm-active",
                )
            distro = state.get("distro_name")
            if isinstance(distro, str) and distro in self._distro_names():
                self._assert_owned(distro, runtime_id)
                self._wsl(["--unregister", distro], timeout=300)
            if is_active:
                pointer.unlink(missing_ok=True)
            tombstone = runtime_dir.with_name(f".{runtime_id}.removed-{os.getpid()}-{time.time_ns()}")
            os.replace(runtime_dir, tombstone)
        if tombstone is not None:
            shutil.rmtree(tombstone, ignore_errors=False)

    def prune(self, *, pinned_runtime_id: str = PINNED_RUNTIME_ID) -> list[str]:
        active = self._read_json(self.root / "active.json") or {}
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
        # Preserve the newest non-active runtime as the only rollback-capable runtime.
        ordered = sorted(candidates, reverse=True)
        removed: list[str] = []
        for _updated_at, runtime_id in ordered[1:]:
            self.remove(runtime_id)
            removed.append(runtime_id)
        return removed

    def _resume(
        self, runtime_dir: Path, state: JsonObject, manifest: JsonObject
    ) -> JsonObject:
        runtime_id = str(manifest["runtime_id"])
        rootfs = _object(manifest["rootfs"])
        archive = runtime_dir / f"localbench-agentic-runtime-{runtime_id}.tar.xz"
        tar_path = runtime_dir / f"localbench-agentic-runtime-{runtime_id}.tar"
        current = str(state.get("state", "absent"))
        if current in {"absent", "downloading"}:
            self._require_disk(runtime_dir, _object(manifest["disk_requirements"]))
            self._write_state(runtime_dir, runtime_id, "downloading")
            if hasattr(self.downloader, "download_to"):
                self.downloader.download_to(
                    str(rootfs["url"]), archive, exact_bytes=int(rootfs["size_bytes"])
                )
            else:  # Compatibility for injected test downloaders.
                body = self.downloader.get(str(rootfs["url"]), maximum_bytes=int(rootfs["size_bytes"]))
                if len(body) != int(rootfs["size_bytes"]):
                    raise ProvisioningError("download_size_invalid", str(len(body)), "Use the signed artifact")
                _atomic_bytes(archive, body)
            current = "downloading"
        if current == "downloading":
            _assert_file_hash(archive, str(rootfs["sha256"]), "rootfs")
            self._write_state(runtime_dir, runtime_id, "verified")
            current = "verified"
        if current == "verified":
            self._require_disk(runtime_dir, _object(manifest["disk_requirements"]))
            _decompress_xz(archive, tar_path, int(rootfs["uncompressed_size_bytes"]))
            distro = self._import_hardened(runtime_dir, runtime_id, tar_path)
            self._write_state(runtime_dir, runtime_id, "imported", distro_name=distro)
            current = "imported"
        state = self._read_state(runtime_dir, runtime_id)
        distro = str(state.get("distro_name", ""))
        if current == "imported":
            self._provision_appworld(distro, manifest)
            self._write_state(
                runtime_dir, runtime_id, "provisioned", distro_name=distro
            )
            current = "provisioned"
        if current == "provisioned":
            self._run_canaries(distro)
            self._write_state(
                runtime_dir, runtime_id, "canary-green", distro_name=distro
            )
            current = "canary-green"
        if current == "canary-green":
            self._wsl(["--terminate", distro], timeout=60)
            self._prove_hardening(distro)
            self._run_canaries(distro)
            result = self._handshake(
                runtime_dir, self._read_state(runtime_dir, runtime_id), manifest
            )
            active = {
                "schema": "localbench.appliance_active.v1",
                "runtime_id": runtime_id,
                "distro_name": distro,
                "activated_at": _now(),
            }
            self._write_state(runtime_dir, runtime_id, "active", distro_name=distro)
            atomic_write_json(active, self.root / "active.json")
            return result
        return self._handshake(
            runtime_dir, self._read_state(runtime_dir, runtime_id), manifest
        )

    def _fetch_manifest(self) -> JsonObject:
        trust_state: JsonObject | None = None
        try:
            trust_raw = self.downloader.get(TRUST_URL, maximum_bytes=MAX_TRUST_BYTES)
            trust_state = admit_trust_metadata(
                trust_raw,
                embedded_roots=dict(RUNTIME_PUBLIC_KEYS),
                state_path=self.root / "trust-state.json",
            )
        except TrustMetadataError as error:
            raise ProvisioningError("trust_metadata_invalid", str(error), "Retry with an untampered current trust document") from error
        raw = self.downloader.get(MANIFEST_URL, maximum_bytes=MAX_MANIFEST_BYTES)
        try:
            return verify_manifest_bytes(raw, trust_state=trust_state)
        except RuntimeManifestError as error:
            raise ProvisioningError(
                error.code, error.detail, "Install an untampered current CLI release"
            ) from error

    @staticmethod
    def _bind_manifest(runtime_dir: Path, manifest: JsonObject) -> None:
        digest = canonical_json_hash(manifest)
        path = runtime_dir / "manifest-payload.sha256"
        try:
            existing = path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            atomic_write_bytes((digest + "\n").encode("ascii"), path)
            return
        if existing != digest:
            raise ProvisioningError(
                "runtime_id_retargeted",
                f"first-seen payload {existing}, fetched {digest}",
                "Keep the existing runtime; install a CLI release that pins a new runtime ID",
            )

    def _feature_preflight(self) -> None:
        if self.runner is subprocess_runner and platform.system() != "Windows":
            raise ProvisioningError(
                "unsupported_platform", platform.system(), "Use x64 Windows 11"
            )
        machine = platform.machine().lower()
        if machine not in {"amd64", "x86_64"}:
            raise ProvisioningError(
                "unsupported_architecture", machine, "Use an x64 Windows 11 machine"
            )
        if self.runner is subprocess_runner:
            build = int(sys.getwindowsversion().build)
            if build < MIN_WINDOWS_BUILD:
                raise ProvisioningError(
                    "windows_build_unsupported",
                    str(build),
                    f"Upgrade to x64 Windows 11 build {MIN_WINDOWS_BUILD} or newer",
                )
        if shutil.which("wsl.exe") is None and self.runner is subprocess_runner:
            raise ProvisioningError(
                "wsl_absent",
                "wsl.exe was not found",
                "Run 'wsl --install --no-distribution', reboot, then retry (administrator required)",
            )
        version = self._wsl(["--version"], timeout=30, check=False)
        if version.returncode != 0:
            raise ProvisioningError(
                "store_wsl_required",
                _decode(version.stderr or version.stdout).strip(),
                "Install/update Windows Subsystem for Linux from Microsoft Store, then retry",
            )
        observed = _parse_wsl_version(_decode(version.stdout))
        if observed < MIN_STORE_WSL:
            raise ProvisioningError(
                "wsl_version_unsupported",
                ".".join(map(str, observed)),
                f"Update Store WSL to at least {'.'.join(map(str, MIN_STORE_WSL))}",
            )
        listing = self._wsl(["--list", "--verbose"], timeout=30, check=False)
        if listing.returncode != 0:
            detail = _decode(listing.stderr or listing.stdout)
            # Microsoft documents 0x80370102 under WSL installation issues:
            # https://learn.microsoft.com/en-us/windows/wsl/troubleshooting#installation-issues
            code = (
                "virtualization_disabled"
                if "0x80370102" in detail
                else "wsl_unavailable_unclassified"
            )
            raise ProvisioningError(
                code,
                detail.strip(),
                "Enable WSL and Virtual Machine Platform, ensure firmware virtualization is enabled, reboot, then retry",
            )

    def _import_hardened(
        self, runtime_dir: Path, runtime_id: str, tar_path: Path
    ) -> str:
        final = FINAL_DISTRO_PREFIX + runtime_id
        staging = STAGING_DISTRO_PREFIX + runtime_id
        final_journal = runtime_dir / "final-import.json"
        journal = self._read_json(final_journal)
        names = self._distro_names()
        if final in names:
            if journal is not None and journal.get("status") == "completed":
                self._assert_owned(final, runtime_id)
                self._prove_wsl2(final)
                self._prove_hardening(final)
                tar_path.unlink(missing_ok=True)
                return final
            # A durable matching intent proves this registration was created by
            # LocalBench even if interruption happened before its marker became readable.
            if not (
                journal is not None
                and journal.get("status") == "intent"
                and journal.get("runtime_id") == runtime_id
                and journal.get("distro_name") == final
            ):
                self._assert_owned(final, runtime_id)
            self._wsl(["--unregister", final], timeout=300)
        if staging in names:
            self._assert_owned(staging, runtime_id)
            self._wsl(["--unregister", staging], timeout=300)
        staging_dir = runtime_dir / "staging-import"
        staging_dir.mkdir(exist_ok=True)
        try:
            self._wsl(
                ["--import", staging, str(staging_dir), str(tar_path), "--version", "2"],
                timeout=900,
            )
        except ProvisioningError:
            if staging in self._distro_names():
                try:
                    self._assert_owned(staging, runtime_id)
                except ProvisioningError as marker_error:
                    atomic_write_json(
                        {"schema": "localbench.partial_registration.v1", "distro_name": staging, "runtime_id": runtime_id, "recovery": "retry marker proof; never unregister without it"},
                        runtime_dir / "partial-registration.json",
                    )
                    raise ProvisioningError("partial_registration_unowned", staging, "Retry setup; if the marker remains unreadable, inspect the named LocalBench staging distro without unregistering it") from marker_error
                self._wsl(["--unregister", staging], timeout=300)
            raise
        self._assert_owned(staging, runtime_id)
        self._prove_wsl2(staging)
        self._install_wsl_conf(staging)
        self._wsl(["--terminate", staging], timeout=60)
        self._prove_hardening(staging)
        self._wsl(["--unregister", staging], timeout=300)
        shutil.rmtree(staging_dir, ignore_errors=True)
        final_dir = runtime_dir / "vhd"
        final_dir.mkdir(exist_ok=True)
        atomic_write_json(
            {
                "schema": "localbench.final_import.v1",
                "status": "intent",
                "runtime_id": runtime_id,
                "distro_name": final,
                "rootfs_tar_sha256": _sha256_file(tar_path),
                "started_at": _now(),
            },
            final_journal,
        )
        self._wsl(
            ["--import", final, str(final_dir), str(tar_path), "--version", "2"],
            timeout=900,
        )
        self._assert_owned(final, runtime_id)
        self._prove_wsl2(final)
        self._install_wsl_conf(final)
        self._wsl(["--terminate", final], timeout=60)
        self._prove_hardening(final)
        atomic_write_json(
            {
                "schema": "localbench.final_import.v1",
                "status": "completed",
                "runtime_id": runtime_id,
                "distro_name": final,
                "rootfs_tar_sha256": _sha256_file(tar_path),
                "completed_at": _now(),
            },
            final_journal,
        )
        tar_path.unlink(missing_ok=True)
        return final

    def _install_wsl_conf(self, distro: str) -> None:
        import base64

        encoded = base64.b64encode(WSL_CONF.encode()).decode("ascii")
        script = (
            f"printf %s {encoded} | base64 -d > /etc/wsl.conf; chmod 0644 /etc/wsl.conf"
        )
        self._exec(distro, ["/bin/sh", "-c", script], user="root")
        fstab = "tmpfs /run/localbench-fstab-probe tmpfs defaults 0 0"
        self._exec(
            distro,
            [
                "/bin/sh",
                "-c",
                f"mkdir -p /run/localbench-fstab-probe; printf '%s\\n' '{fstab}' >> /etc/fstab",
            ],
            user="root",
        )

    def _prove_hardening(self, distro: str) -> None:
        proof = self._exec(
            distro,
            [
                "/bin/sh",
                "-c",
                'printf \'%s\\n\' "$(id -un)" "$(id -gn)"; '
                "test ! -e /mnt/c; ! command -v cmd.exe >/dev/null 2>&1; "
                "! cmd.exe /c exit 0 >/dev/null 2>&1; "
                "! printf '%s' \"$PATH\" | grep -Eq '(^|:)/mnt/[A-Za-z]/'; "
                "! grep -F ' /run/localbench-fstab-probe ' /proc/self/mountinfo >/dev/null",
            ],
        )
        lines = _decode(proof.stdout).splitlines()
        if proof.returncode != 0 or lines[:2] != ["lbworker", "lbworker"]:
            raise ProvisioningError(
                "wsl_hardening_proof_failed",
                _decode(proof.stderr or proof.stdout),
                "Remove the staging runtime and retry provisioning",
            )
        self._exec(
            distro,
            [
                "/bin/sh",
                "-c",
                "sed -i '\\|^tmpfs /run/localbench-fstab-probe |d' /etc/fstab",
            ],
            user="root",
        )

    def _provision_appworld(self, distro: str, manifest: JsonObject) -> None:
        env = _download_environment(self.environ)
        ca = self.environ.get("LOCALBENCH_CA_BUNDLE")
        if ca:
            source = Path(ca).expanduser()
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            import base64
            encoded = base64.b64encode(data).decode("ascii")
            linux_ca = "/opt/localbench/ca/corporate-ca.pem"
            self._exec(distro, ["/bin/sh", "-c", f"umask 077; mkdir -p /opt/localbench/ca; printf %s {encoded} | base64 -d > {linux_ca}; chown root:root {linux_ca}; chmod 0644 {linux_ca}"], user="root")
            observed = self._exec(distro, ["/usr/bin/sha256sum", linux_ca])
            if observed.returncode != 0 or _decode(observed.stdout).split()[0] != digest:
                raise ProvisioningError("ca_copy_hash_mismatch", str(source), "Retry setup with an intact CA bundle")
            env["SSL_CERT_FILE"] = linux_ca
        document = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        result = self._exec(
            distro,
            [
                "/usr/bin/env",
                "-i",
                *[f"{key}={value}" for key, value in env.items()],
                "/opt/localbench/bin/provision-appworld",
                document,
            ],
            timeout=1800,
        )
        if result.returncode != 0:
            raise ProvisioningError(
                "appworld_provision_failed",
                _decode(result.stderr),
                "Retry setup; if upstream bytes changed, wait for a new signed runtime release",
            )

    def _run_canaries(self, distro: str) -> None:
        result = self._exec(
            distro,
            ["/usr/bin/env", "-i", "HOME=/home/lbworker", "APPWORLD_ROOT=/home/lbworker/appworld", "PATH=/opt/localbench/venv/bin:/usr/bin:/bin", "PYTHONHASHSEED=0", "TZ=UTC", "LC_ALL=C.UTF-8", "/opt/localbench/bin/localbench-worker", "canary", "--full"],
            timeout=600,
        )
        if result.returncode != 0:
            raise ProvisioningError(
                "runtime_canary_failed",
                _decode(result.stderr),
                "Remove the runtime and reprovision",
            )

    def _handshake(
        self, runtime_dir: Path, state: JsonObject, manifest: JsonObject | None = None
    ) -> JsonObject:
        distro = state.get("distro_name")
        if not isinstance(distro, str) or distro not in self._distro_names():
            raise ProvisioningError(
                "runtime_missing", repr(distro), "Run localbench setup-agentic"
            )
        if manifest is None:
            manifest = self._fetch_manifest()
        result = self._exec(
            distro,
            ["/usr/bin/env", "-i", "HOME=/home/lbworker", "PATH=/opt/localbench/venv/bin:/usr/bin:/bin", "PYTHONHASHSEED=0", "TZ=UTC", "LC_ALL=C.UTF-8", "/opt/localbench/bin/localbench-worker", "handshake", "--json"],
            timeout=180,
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
        expected_hashes = _object(manifest["critical_hashes"])
        observed_hashes = identity.get("critical_hashes", {})
        if not isinstance(observed_hashes, dict) or set(observed_hashes) != set(
            REQUIRED_CRITICAL_HASHES
        ):
            raise ProvisioningError(
                "critical_hash_set_invalid", "worker set differs", "Reprovision"
            )
        if identity.get("critical_hashes") != expected_hashes:
            raise ProvisioningError(
                "runtime_mutated", "critical hash mismatch", "Reprovision"
            )
        if identity.get("execution_contract_sha256") != manifest.get(
            "execution_contract_sha256"
        ):
            raise ProvisioningError(
                "execution_contract_mismatch", "worker contract differs", "Reprovision"
            )
        tasks = _object(manifest["task_identity"])
        for field in (
            "ordered_task_ids_sha256",
            "selection_recipe_sha256",
            "semantic_task_sha256",
        ):
            if identity.get(field) != tasks.get(field):
                raise ProvisioningError("task_contract_mismatch", field, "Reprovision")
        required = {
            "runtime_id": manifest["runtime_id"],
            "protocol_version": _object(manifest["worker"])["protocol_version"],
            "uid": "lbworker",
            "gid": "lbworker",
            "mnt_c_absent": True,
            "interop_blocked": True,
            "windows_path_absent": True,
        }
        for field, expected in required.items():
            if identity.get(field) != expected:
                raise ProvisioningError(
                    "runtime_identity_mismatch", field, "Reprovision"
                )
        return identity

    def _assert_owned(self, distro: str, runtime_id: str) -> None:
        result = self._exec(
            distro, ["/bin/cat", OWNERSHIP_MARKER], user="root", timeout=30
        )
        try:
            marker = json.loads(_decode(result.stdout))
        except json.JSONDecodeError as error:
            raise ProvisioningError(
                "ownership_marker_missing", distro, "Choose a different runtime name"
            ) from error
        if result.returncode != 0 or marker != {
            "owner": "localbench",
            "runtime_id": runtime_id,
            "schema": "localbench.appliance_owner.v1",
        }:
            raise ProvisioningError(
                "ownership_marker_mismatch",
                distro,
                "Refusing to unregister this distro",
            )

    def _prove_wsl2(self, distro: str) -> None:
        text = _decode(self._wsl(["--list", "--verbose"], timeout=30).stdout)
        matched = _parse_wsl_verbose(text).get(distro) == 2
        if not matched:
            raise ProvisioningError("wsl2_proof_failed", distro, "Update WSL and retry")

    def _distro_names(self) -> set[str]:
        result = self._wsl(["--list", "--quiet"], timeout=30)
        return {
            line.strip() for line in _decode(result.stdout).splitlines() if line.strip()
        }

    def _exec(
        self,
        distro: str,
        command: Sequence[str],
        *,
        user: str | None = None,
        timeout: float = 300,
    ) -> CommandResult:
        argv = ["--distribution", distro]
        if user is not None:
            argv.extend(["--user", user])
        argv.extend(["--exec", *command])
        return self._wsl(argv, timeout=timeout, check=False)

    def _wsl(
        self, args: Sequence[str], *, timeout: float, check: bool = True
    ) -> CommandResult:
        try:
            result = self.runner(["wsl.exe", *args], timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProvisioningError(
                "wsl_command_failed", str(error), "Check WSL status and retry"
            ) from error
        if check and result.returncode != 0:
            detail = _decode(result.stderr or result.stdout).strip()
            if _looks_disk_full(detail):
                raise ProvisioningError("disk_space_exhausted", detail, "Free disk space and retry; no ready state was created")
            code = (
                "virtualization_disabled"
                if "0x80370102" in detail
                else "wsl_command_failed"
            )
            raise ProvisioningError(code, detail, "Check WSL status and retry")
        return result

    def _require_disk(self, runtime_dir: Path, requirements: JsonObject) -> None:
        peak = requirements.get("peak_free_bytes")
        steady = requirements.get("steady_free_bytes")
        parts = [requirements.get(name) for name in ("download_bytes", "import_bytes", "provision_growth_bytes")]
        if not isinstance(peak, int) or peak <= 0 or not isinstance(steady, int) or steady <= 0 or any(not isinstance(item, int) or item <= 0 for item in parts):
            raise ProvisioningError(
                "manifest_invalid", "disk requirement fields", "Use a valid manifest"
            )
        free = shutil.disk_usage(runtime_dir).free
        calculated_peak = sum(int(item) for item in parts)
        if peak < calculated_peak:
            raise ProvisioningError("manifest_invalid", "peak disk math understates components", "Use a valid manifest")
        required = max(peak, steady)
        if free < required:
            raise ProvisioningError(
                "disk_space_insufficient",
                f"need {required} bytes, have {free}",
                "Free disk space and retry; no ready state was created",
            )

    def _read_state(self, runtime_dir: Path, runtime_id: str) -> JsonObject:
        value = self._read_json(runtime_dir / "state.json")
        if value is None:
            return {
                "schema": "localbench.appliance_state.v1",
                "runtime_id": runtime_id,
                "state": "absent",
            }
        if (
            value.get("runtime_id") != runtime_id
            or value.get("state") not in STATE_ORDER
        ):
            raise ProvisioningError(
                "state_journal_invalid",
                str(runtime_dir),
                "Remove the runtime directory",
            )
        return value

    @staticmethod
    def _read_json(path: Path) -> JsonObject | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProvisioningError(
                "state_journal_invalid", str(path), "Remove the corrupt state"
            ) from error
        if not isinstance(value, dict):
            raise ProvisioningError(
                "state_journal_invalid", str(path), "Remove the corrupt state"
            )
        return value

    @staticmethod
    def _write_state(
        runtime_dir: Path,
        runtime_id: str,
        state: str,
        *,
        distro_name: str | None = None,
    ) -> None:
        payload: JsonObject = {
            "schema": "localbench.appliance_state.v1",
            "runtime_id": runtime_id,
            "state": state,
            "updated_at": _now(),
        }
        if distro_name is not None:
            payload["distro_name"] = distro_name
        atomic_write_json(payload, runtime_dir / "state.json")


def appliance_root(environ: Mapping[str, str]) -> Path:
    value = environ.get("LOCALAPPDATA")
    if not value:
        raise ProvisioningError(
            "localappdata_missing",
            "LOCALAPPDATA is unset",
            "Repair the Windows user profile",
        )
    return Path(value) / "LocalBench"


def validate_storage_root(path: Path, environ: Mapping[str, str]) -> None:
    resolved = path.resolve()
    for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        cloud = environ.get(variable)
        if cloud and _is_relative_to(resolved, Path(cloud).resolve()):
            raise ProvisioningError(
                "cloud_storage_disallowed",
                str(path),
                "Choose a local LOCALAPPDATA profile",
            )
    if str(resolved).startswith("\\\\"):
        raise ProvisioningError(
            "network_storage_disallowed", str(path), "Use a fixed local NTFS volume"
        )
    for ancestor in (resolved, *resolved.parents):
        if (
            ancestor.exists()
            and getattr(ancestor.stat(), "st_file_attributes", 0) & 0x400
        ):
            raise ProvisioningError(
                "reparse_storage_disallowed",
                str(ancestor),
                "Use a non-reparse local path",
            )
    if os.name == "nt":
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(resolved.anchor)
        if drive_type != 3:  # DRIVE_FIXED, documented Win32 GetDriveTypeW value.
            raise ProvisioningError(
                "non_fixed_storage_disallowed", str(path), "Use a fixed local drive"
            )


@contextlib.contextmanager
def runtime_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    handle = path.open("r+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def _parse_wsl_version(text: str) -> tuple[int, int, int, int]:
    # Exact label captured from wsl.exe 2.6.3.0 on 2026-07-11.
    match = re.search(r"(?mi)^WSL version:\s*(\d+)\.(\d+)\.(\d+)\.(\d+)\s*$", text)
    if match is None:
        raise ProvisioningError(
            "wsl_version_unparseable", text.strip(), "Install Store WSL and retry"
        )
    return tuple(int(item) for item in match.groups())  # type: ignore[return-value]


def _parse_wsl_verbose(text: str) -> dict[str, int]:
    rows: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip().removeprefix("* ").strip()
        match = re.fullmatch(r"(.+?)\s{2,}.+?\s{2,}(\d+)", stripped)
        if match:
            rows[match.group(1).strip()] = int(match.group(2))
    return rows


def _decode(value: bytes) -> str:
    encoding = "utf-16-le" if b"\x00" in value[:8] else "utf-8"
    return value.decode(encoding, errors="replace").lstrip("\ufeff")


def _download_environment(environ: Mapping[str, str]) -> dict[str, str]:
    allowed = {}
    for key in ("HTTPS_PROXY", "NO_PROXY", "https_proxy", "no_proxy", "SSL_CERT_FILE"):
        value = environ.get(key)
        if value:
            allowed[key] = value
    ca = environ.get("LOCALBENCH_CA_BUNDLE")
    if ca:
        allowed["SSL_CERT_FILE"] = ca
    return allowed


def _decompress_xz(source: Path, destination: Path, expected_size: int) -> None:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    total = 0
    try:
        with lzma.open(source, "rb") as reader, temporary.open("wb") as writer:
            while chunk := reader.read(1024 * 1024):
                total += len(chunk)
                if total > expected_size:
                    raise ProvisioningError(
                        "archive_size_invalid", str(total), "Discard and retry"
                    )
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        if total != expected_size:
            raise ProvisioningError(
                "archive_size_invalid", str(total), "Discard and retry"
            )
        _replace_retry(temporary, destination)
    except OSError as error:
        if error.errno == errno.ENOSPC:
            raise _disk_error(error) from error
        raise
    finally:
        temporary.unlink(missing_ok=True)


def _assert_file_hash(path: Path, expected: str, label: str) -> None:
    last_error: OSError | None = None
    digest = hashlib.sha256()
    for attempt in range(3):
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            last_error = None
            break
        except OSError as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1))
    if last_error is not None:
        raise ProvisioningError(
            "artifact_unreadable",
            str(last_error),
            "Retry after your antivirus releases or restores the signed artifact; do not disable it",
        ) from last_error
    if digest.hexdigest() != expected:
        raise ProvisioningError(
            "artifact_hash_mismatch", label, "Discard the cache and retry"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(data)
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    _replace_retry(temporary, path)


def _replace_retry(source: Path, destination: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(3):
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1))
    raise ProvisioningError(
        "artifact_locked_or_quarantined",
        str(last_error),
        "Allow your antivirus to finish scanning or restore the signed artifact, then retry; do not disable it",
    ) from last_error


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ProvisioningError(
            "manifest_invalid", "object expected", "Use a valid signed manifest"
        )
    return value


def _validate_runtime_id(value: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", value):
        raise ProvisioningError(
            "runtime_id_invalid", value, "Use the CLI-pinned runtime ID"
        )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _looks_disk_full(detail: str) -> bool:
    lowered = detail.lower()
    # Microsoft documents HRESULT 0x80070070 as insufficient disk space:
    # https://learn.microsoft.com/en-us/troubleshoot/windows-server/installing-updates-features-roles/troubleshoot-windows-update-error-0x80070070
    disk_full_hresult = "0x80070070"
    return disk_full_hresult in lowered


def _disk_error(error: OSError) -> ProvisioningError:
    return ProvisioningError("disk_space_exhausted", str(error), "Free disk space and retry; no ready state was created")


__all__ = [
    "ApplianceProvisioner",
    "CommandResult",
    "HttpDownloader",
    "MIN_STORE_WSL",
    "MIN_WINDOWS_BUILD",
    "ProvisioningError",
    "STATE_ORDER",
    "WSL_CONF",
    "appliance_root",
    "runtime_lock",
    "validate_storage_root",
]
