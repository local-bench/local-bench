"""Exercise the real ensure_active entrypoint and final-import crash recovery on WSL."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import localbench.appliance.provisioner as provisioner_module
from localbench.appliance.provisioner import (
    ApplianceProvisioner,
    CommandResult,
    ProvisioningError,
)
from localbench.appliance.manifest import RuntimeManifestError, verify_manifest_bytes
from localbench.submissions.canon import write_json_file


class Recorder:
    def __init__(self, evidence: dict[str, object], *, fail_final_start: bool = False):
        self.evidence = evidence
        self.fail_final_start = fail_final_start

    def __call__(self, argv, timeout=None) -> CommandResult:
        arguments = list(argv)
        final_import = (
            len(arguments) > 3
            and arguments[1] == "--import"
            and arguments[2].startswith("LocalBench-Staging-Final-")
        )
        if final_import and self.fail_final_start:
            self.fail_final_start = False
            self._record(arguments, -1, b"", b"injected kill before final import command")
            raise ProvisioningError(
                "rehearsal_fault", "kill at final import start", "restart ensure_active"
            )
        completed = subprocess.run(
            arguments, capture_output=True, check=False, timeout=timeout
        )
        self._record(
            arguments, completed.returncode, completed.stdout, completed.stderr
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    def _record(
        self, arguments: list[str], exit_code: int, stdout: bytes, stderr: bytes
    ) -> None:
        commands = self.evidence.setdefault("commands", [])
        assert isinstance(commands, list)
        commands.append(
            {
                "arguments": arguments,
                "exit_code": exit_code,
                "stdout_encoding": _encoding(stdout),
                "stdout_base64": base64.b64encode(stdout).decode("ascii"),
                "stderr_encoding": _encoding(stderr),
                "stderr_base64": base64.b64encode(stderr).decode("ascii"),
            }
        )

    def run_with_stdin(
        self, arguments: list[str], data: bytes, *, timeout: float
    ) -> CommandResult:
        completed = subprocess.run(
            arguments,
            input=data,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        self._record(
            arguments, completed.returncode, completed.stdout, completed.stderr
        )
        commands = self.evidence["commands"]
        assert isinstance(commands, list)
        commands[-1]["stdin_size_bytes"] = len(data)
        commands[-1]["stdin_sha256"] = hashlib.sha256(data).hexdigest()
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class RehearsalProvisioner(ApplianceProvisioner):
    def __init__(
        self,
        *,
        manifest: dict[str, object],
        local_inputs: dict[str, Path],
        interrupt_after_final_import: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.rehearsal_manifest = manifest
        self.local_inputs = local_inputs
        self.interrupt_after_final_import = interrupt_after_final_import

    def _fetch_manifest(self):
        return copy.deepcopy(self.rehearsal_manifest)

    def _install_wsl_conf(self, distro: str) -> None:
        if (
            self.interrupt_after_final_import
            and distro.startswith("LocalBench-Staging-Final-")
        ):
            self.interrupt_after_final_import = False
            raise ProvisioningError(
                "rehearsal_fault",
                "kill between final import and completion journal",
                "restart ensure_active",
            )
        super()._install_wsl_conf(distro)

    def _provision_appworld(self, distro: str, manifest) -> None:
        local_manifest = copy.deepcopy(manifest)
        appworld = local_manifest["appworld"]
        targets = {
            "package": "/tmp/appworld-official.whl",
            "dependency_lock": "/tmp/appworld.lock",
            "data_distribution": "/tmp/appworld-data.bundle",
        }
        for name, target in targets.items():
            data = self.local_inputs[name].read_bytes()
            if not isinstance(self.runner, Recorder):
                raise RuntimeError("rehearsal input copy requires the recording runner")
            result = self.runner.run_with_stdin(
                [
                    "wsl.exe",
                    "--distribution",
                    distro,
                    "--user",
                    "root",
                    "--exec",
                    "/bin/sh",
                    "-c",
                    f"cat > {target}; chmod 0644 {target}",
                ],
                data,
                timeout=300,
            )
            if result.returncode != 0:
                raise ProvisioningError(
                    "rehearsal_input_copy_failed", target, "inspect WSL transcript"
                )
        appworld["package"]["url"] = "file:///tmp/appworld-official.whl"
        appworld["dependency_locks"]["x86_64"]["url"] = "file:///tmp/appworld.lock"
        appworld["data_distribution"]["url"] = "file:///tmp/appworld-data.bundle"
        super()._provision_appworld(distro, local_manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--appworld-wheel", required=True, type=Path)
    parser.add_argument("--dependency-lock", required=True, type=Path)
    parser.add_argument("--data-bundle", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = _verified_manifest(args.manifest)
    runtime_id = str(manifest["runtime_id"])
    compressed_sha = _sha(args.archive)
    if compressed_sha != manifest["rootfs"]["sha256"]:
        raise RuntimeError("compressed rootfs differs from signed manifest")
    evidence: dict[str, object] = {
        "schema": "localbench.ensure_active_rehearsal.v1",
        "runtime_id": runtime_id,
        "entrypoint": "ApplianceProvisioner.ensure_active",
        "signed_compressed_rootfs_sha256": compressed_sha,
        "commands": [],
    }
    local_inputs = {
        "package": args.appworld_wheel,
        "dependency_lock": args.dependency_lock,
        "data_distribution": args.data_bundle,
    }
    provisioner_module.FINAL_DISTRO_PREFIX = "LocalBench-Staging-Final-"
    runtime_dir = args.root / "WSL" / runtime_id
    runtime_dir.mkdir(parents=True, exist_ok=False)
    cached = runtime_dir / f"localbench-agentic-runtime-{runtime_id}.tar.xz"
    shutil.copy2(args.archive, cached)
    recorder = Recorder(evidence, fail_final_start=True)
    first = RehearsalProvisioner(
        root=args.root,
        runner=recorder,
        environ={},
        manifest=manifest,
        local_inputs=local_inputs,
    )
    first._write_state(runtime_dir, runtime_id, "verified")
    _expect_fault(first, "kill at final import start", evidence)

    second = RehearsalProvisioner(
        root=args.root,
        runner=recorder,
        environ={},
        manifest=manifest,
        local_inputs=local_inputs,
        interrupt_after_final_import=True,
    )
    _expect_fault(second, "kill between final import and completion journal", evidence)

    third = RehearsalProvisioner(
        root=args.root,
        runner=recorder,
        environ={},
        manifest=manifest,
        local_inputs=local_inputs,
    )
    try:
        third.ensure_active(runtime_id)
    except ProvisioningError as error:
        evidence["terminal_fail_closed_code"] = error.code
        if error.code != "runtime_canary_failed":
            raise
    final = provisioner_module.FINAL_DISTRO_PREFIX + runtime_id
    journal = json.loads((runtime_dir / "final-import.json").read_text(encoding="utf-8"))
    if journal.get("status") != "completed":
        raise RuntimeError("final import completion journal missing")
    tar_path = runtime_dir / f"localbench-agentic-runtime-{runtime_id}.tar"
    evidence["decompressed_rootfs_sha256"] = _sha(tar_path) if tar_path.exists() else journal["rootfs_tar_sha256"]
    evidence["decompression_relationship"] = (
        "signed tar.xz was decompressed by ensure_active into the tar whose SHA-256 is recorded"
    )
    third._assert_owned(final, runtime_id)
    third._wsl(["--unregister", final], timeout=300)
    remaining = third._distro_names()
    if any(name.startswith("LocalBench-Staging-") and runtime_id in name for name in remaining):
        raise RuntimeError("rehearsal distro cleanup failed")
    shutil.rmtree(args.root)
    evidence["result"] = "passed-transaction-recovery-and-fail-closed-admission"
    evidence["cleanup_verified"] = True
    write_json_file(args.out, evidence)
    return 0


def _expect_fault(
    provisioner: ApplianceProvisioner,
    expected: str,
    evidence: dict[str, object],
) -> None:
    try:
        provisioner.ensure_active()
    except ProvisioningError as error:
        if expected not in error.detail:
            raise
        checkpoints = evidence.setdefault("fault_checkpoints", [])
        assert isinstance(checkpoints, list)
        checkpoints.append(expected)
        return
    raise RuntimeError(f"expected rehearsal fault did not occur: {expected}")


def _verified_manifest(path: Path) -> dict[str, object]:
    """Use the production verifier for canonical bytes, hash, signature, trust, and pin."""
    try:
        return verify_manifest_bytes(path.read_bytes())
    except RuntimeManifestError as error:
        raise RuntimeError(f"rehearsal manifest verification failed: {error}") from error


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _encoding(raw: bytes) -> str:
    return "utf-16-le" if b"\x00" in raw[:8] else "utf-8"


if __name__ == "__main__":
    raise SystemExit(main())
