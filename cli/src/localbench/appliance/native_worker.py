from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from localbench.appliance.provisioner import (
    CommandResult,
    CommandRunner,
    ProvisioningError,
)
from localbench.scoring.agentic_exec.sandbox_policy import (
    mandatory_bubblewrap_isolation,
    provisioning_bubblewrap_isolation,
)


@dataclass(frozen=True, slots=True)
class NativeWorkerSpec:
    rootfs: Path
    command: tuple[str, ...]
    environment: Mapping[str, str]
    writable: bool
    network: bool
    timeout_s: float = 300.0


def native_worker_argv(spec: NativeWorkerSpec) -> tuple[str, ...]:
    loader = spec.rootfs / "lib64/ld-linux-x86-64.so.2"
    bwrap = spec.rootfs / "usr/bin/bwrap"
    if not loader.exists() or not bwrap.exists():
        raise ProvisioningError(
            "runtime_mutated", "signed bubblewrap launcher is missing", "Reprovision"
        )
    libraries = ":".join(
        str(spec.rootfs / relative)
        for relative in ("lib/x86_64-linux-gnu", "usr/lib/x86_64-linux-gnu")
    )
    isolation = (
        provisioning_bubblewrap_isolation("localbench-provision")
        if spec.network
        else mandatory_bubblewrap_isolation("localbench-agentic")
    )
    argv = [
        str(loader),
        "--library-path",
        libraries,
        str(bwrap),
        *isolation,
        "--ro-bind",
        str(spec.rootfs),
        "/",
        "--bind",
        str(spec.rootfs / "home/lbworker"),
        "/home/lbworker",
    ]
    if spec.writable:
        argv.extend(
            [
                "--bind",
                str(spec.rootfs / "opt/localbench/venv"),
                "/opt/localbench/venv",
            ]
        )
    argv.extend(
        [
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/run",
            "--uid",
            "10001",
            "--gid",
            "10001",
            "--chdir",
            "/home/lbworker",
            "--clearenv",
        ]
    )
    for key, value in sorted(spec.environment.items()):
        argv.extend(("--setenv", key, value))
    argv.extend(spec.command)
    return tuple(argv)


def run_native_worker(
    runner: CommandRunner,
    spec: NativeWorkerSpec,
) -> CommandResult:
    return runner(native_worker_argv(spec), timeout=spec.timeout_s)
