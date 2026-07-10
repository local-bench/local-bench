from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec.protocol_c_loop import SandboxLike
from localbench.scoring.agentic_exec.sandbox import FINALIZATION_PROVENANCE, SandboxError
from localbench.scoring.agentic_exec.wsl_process import WslWorkerConfig
from localbench.scoring.agentic_exec.wsl_proxy import WslSandboxProxy, WslVerdict as WslVerdict
from localbench.scoring.agentic_exec.worker_identity import worker_implementation_identity


@dataclass(frozen=True, slots=True)
class WslPreflightResult:
    identity: JsonObject
    task_ids: tuple[str, ...]

    def provenance(self) -> JsonObject:
        return provenance_from_identity(self.identity)


def wsl_sandbox_factory(
    repo_root_wsl_path: str,
    venv_python: str,
    appworld_root: str,
    *,
    log_dir: Path | None = None,
    worker_argv: tuple[str, ...] | None = None,
) -> Callable[[str], AbstractContextManager[SandboxLike]]:
    config = WslWorkerConfig(
        repo_root_wsl_path=repo_root_wsl_path,
        venv_python=venv_python,
        appworld_root=appworld_root,
        log_dir=log_dir or Path("runs") / "agentic-wsl",
        worker_argv=worker_argv,
    )

    def _factory(task_id: str) -> WslSandboxProxy:
        return WslSandboxProxy(task_id, config)

    return _factory


def wsl_list_scored_task_ids(config: WslWorkerConfig) -> list[str]:
    with WslSandboxProxy(None, config) as worker:
        return worker.list_tasks("scored")


def preflight_wsl_agentic(
    *,
    repo_root_wsl_path: str,
    venv_python: str,
    appworld_root: str,
    log_dir: Path,
    max_items: int | None = None,
) -> WslPreflightResult:
    config = WslWorkerConfig(
        repo_root_wsl_path=repo_root_wsl_path,
        venv_python=venv_python,
        appworld_root=appworld_root,
        log_dir=log_dir,
    )
    with WslSandboxProxy(None, config) as worker:
        identity = worker.identity
        if identity is None:
            raise SandboxError("wsl preflight did not collect worker identity")
        _assert_identity(identity, worker_implementation_identity())
        task_ids = tuple(worker.list_tasks("scored"))
    if not task_ids:
        raise SandboxError("wsl preflight list_tasks returned no scored tasks")
    selected = task_ids[:max_items] if max_items is not None else task_ids
    return WslPreflightResult(identity=identity, task_ids=tuple(selected))


def provenance_from_identity(identity: JsonObject) -> JsonObject:
    published_identity = {
        key: value
        for key, value in identity.items()
        if key not in {"venv_path", "bwrap_path", "appworld_root"}
    }
    return {
        "topology": {
            "scorecard_assembly": "single-campaign-no-merge",
            "model_call_location": "windows_campaign_process",
        },
        "wsl_identity": published_identity,
        "agentic_sandbox_identity": {
            "bubblewrap_sha256": _string(identity.get("bwrap_sha256")),
            "bubblewrap_version": _string(identity.get("bwrap_version")),
            "appworld_root_sha256": _string(identity.get("appworld_root_sha256")),
            "appworld_root_filesystem": _string(identity.get("appworld_root_filesystem")),
        },
        "single_campaign_integrity": {
            "merge_step_used": False,
        },
        # Run-level trust-tier note for the agentic harness: the verdict is host-derived over
        # the env-host stdin control channel; the untrusted runner is not in the verdict path.
        "agentic_verdict_channel": {
            **FINALIZATION_PROVENANCE,
            "trust_note": "host-derived+direct-finalize-v1",
        },
    }


def default_wsl_repo_path(windows_repo_root: Path) -> str:
    resolved = windows_repo_root.resolve()
    drive_value = resolved.drive
    if len(drive_value) != 2 or drive_value[1] != ":" or not drive_value[0].isalpha():
        raise SandboxError(
            f"cannot map non-drive-colon checkout path into WSL: {resolved}",
        )
    drive = drive_value[0].lower()
    rest = resolved.as_posix()[2:].lstrip("/")
    return f"/mnt/{drive}/{rest}"


def _assert_identity(identity: JsonObject, expected: JsonObject) -> None:
    if identity.get("appworld_root_under_mnt") is True:
        raise SandboxError("wsl preflight failed: APPWORLD_ROOT is under /mnt")
    if not identity.get("bwrap_path"):
        raise SandboxError("wsl preflight failed: bwrap is missing")
    expected_version = expected.get("localbench_distribution_version")
    actual_version = identity.get("localbench_distribution_version")
    if not isinstance(expected_version, str) or not expected_version:
        raise SandboxError("wsl preflight failed: host localbench distribution version is unavailable")
    if actual_version != expected_version:
        raise SandboxError(
            "wsl preflight failed: localbench distribution version mismatch: "
            f"worker={actual_version!r} host={expected_version!r}",
        )
    expected_digest = expected.get("worker_content_sha256")
    actual_digest = identity.get("worker_content_sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise SandboxError("wsl preflight failed: host worker content digest is unavailable")
    if actual_digest != expected_digest:
        raise SandboxError(
            "wsl preflight failed: worker content digest mismatch: "
            f"worker={actual_digest!r} host={expected_digest!r}",
        )


def _string(value: JsonValue | None) -> str:
    return value if isinstance(value, str) else ""
