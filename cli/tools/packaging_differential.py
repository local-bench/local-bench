#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# noqa: SIZE_OK — one repo-only driver; splitting would obscure its fail-closed lifecycle

# ─── How to run ───
# uv run --project cli python cli/tools/packaging_differential.py \
#   --distro LocalBench-Staging-<runtime-id> --out evidence.json \
#   --rootfs-sha256 <sha256> --worker-wheel-sha256 <sha256>
# ──────────────────

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
import time
from collections.abc import Sequence
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Callable, Final, Literal, Protocol, assert_never

from localbench._types import ChatMessage, JsonObject, JsonValue
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.scoring.agentic_exec.benchmark import run_appworld_c_benchmark
from localbench.scoring.agentic_exec.execution_contract import CONTRACT_ID, load_execution_contract
from localbench.scoring.agentic_exec.funnel import _report_envelopes
from localbench.scoring.agentic_exec.model_client import (
    GenerationParams,
    ModelClient,
    ModelResponse,
)
from localbench.scoring.agentic_exec.scripted_agent import ScriptedSolverAgent, _TASK_BLOCKS
from localbench.scoring.agentic_exec.wsl_process import (
    WslWorkerConfig,
    creation_flags,
    safe_label,
    worker_env,
)
from localbench.scoring.agentic_exec.wsl_proxy import WslSandboxProxy, WslTransportError
from localbench.submissions.canon import canonical_json_bytes, canonical_json_hash, write_json_file

SCHEMA: Final = "localbench.packaging_differential.v1"
STAGING_PREFIX: Final = "LocalBench-Staging-"
REPO_SOURCE_ROOT: Final = "/opt/localbench/diff-src"
TASK_IDS: Final = ("fac291d_1", "50e1ac9_1")
DEFAULT_REPO_SOURCE: Final = Path(__file__).resolve().parents[1] / "src"
VENV_PYTHON: Final = "/opt/localbench/venv/bin/python"
APPWORLD_ROOT: Final = "/home/lbworker/appworld"
EqualField = Literal[
    "model_turn_requests",
    "sandbox_operations",
    "finalize_verdict",
    "scored_envelopes",
    "aggregates",
]
EQUAL_FIELDS: Final[tuple[EqualField, ...]] = (
    "model_turn_requests",
    "sandbox_operations",
    "finalize_verdict",
    "scored_envelopes",
    "aggregates",
)
SideName = Literal["repo", "appliance"]


@dataclass(frozen=True, slots=True)
class PackagingDifferentialError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)  # noqa: MUTABLE_OK
class TaskTrace:
    """Mutable accumulator populated while one task flows through the host loop."""

    model_turn_requests: list[JsonObject] = field(default_factory=list)
    sandbox_operations: list[JsonObject] = field(default_factory=list)
    finalize_verdict: JsonObject | None = None
    scored_envelopes: list[JsonObject] = field(default_factory=list)


@dataclass(slots=True)  # noqa: MUTABLE_OK
class SideRun:
    """Mutable accumulator populated sequentially for one differential side."""

    worker_identity: JsonObject = field(default_factory=dict)
    per_task: dict[str, TaskTrace] = field(default_factory=dict)
    aggregates: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Comparison:
    field_verdicts: dict[str, bool]
    verdict: Literal["pass", "fail"]
    diffs: list[JsonObject]


class _ObservationLike(Protocol):
    stdout: str
    error: str | None


class _VerdictLike(Protocol):
    success: bool
    collateral_damage: bool
    passes: Sequence[str]
    failures: Sequence[str]


class _SandboxLike(Protocol):
    def run_block(self, code: str) -> _ObservationLike: ...

    def finalize(self, answer: JsonValue) -> _VerdictLike: ...


class _SandboxContextLike(Protocol):
    def __enter__(self) -> _SandboxLike: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class RecordingModel:
    def __init__(self, inner: ModelClient, trace: TaskTrace) -> None:
        self._inner = inner
        self._trace = trace

    def complete(
        self,
        messages: list[ChatMessage],
        params: GenerationParams,
    ) -> ModelResponse:
        self._trace.model_turn_requests.append(
            {"messages": deepcopy(messages), "params": asdict(params)}
        )
        return self._inner.complete(messages, params)


class RecordingSandboxContext(AbstractContextManager[_SandboxLike]):
    def __init__(
        self,
        inner: _SandboxContextLike,
        trace: TaskTrace,
        identity_sink: Callable[[JsonObject], None] | None = None,
    ) -> None:
        self._inner = inner
        self._trace = trace
        self._identity_sink = identity_sink
        self._sandbox: _SandboxLike | None = None
        self._teardown_failure: str | None = None

    def __enter__(self) -> RecordingSandboxContext:
        self._sandbox = self._inner.__enter__()
        identity = getattr(self._sandbox, "identity", None)
        if self._identity_sink is not None and isinstance(identity, dict):
            self._identity_sink(identity)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        try:
            return self._inner.__exit__(exc_type, exc, traceback)
        finally:
            value = getattr(self._sandbox, "teardown_failure", None)
            self._teardown_failure = value if isinstance(value, str) else None
            self._sandbox = None

    def run_block(self, code: str) -> _ObservationLike:
        request: JsonObject = {"op": "run_block", "code": code}
        event: JsonObject = {"request": request}
        self._trace.sandbox_operations.append(event)
        observation = self._require_sandbox().run_block(code)
        event["reply"] = {
            "kind": "ok",
            "stdout": observation.stdout,
            "error": observation.error,
        }
        return observation

    def finalize(self, answer: JsonValue) -> _VerdictLike:
        request: JsonObject = {"op": "finalize", "answer": deepcopy(answer)}
        event: JsonObject = {"request": request}
        self._trace.sandbox_operations.append(event)
        verdict = self._require_sandbox().finalize(answer)
        payload = _verdict_payload(verdict)
        event["reply"] = {"kind": "ok", "verdict": payload}
        self._trace.finalize_verdict = deepcopy(payload)
        return verdict

    def __getattr__(self, name: str) -> Callable[[], JsonObject]:
        if name != "finalization_provenance":
            raise AttributeError(name)
        provenance = getattr(self._require_sandbox(), name, None)
        if not callable(provenance):
            raise AttributeError(name)
        return provenance

    @property
    def teardown_failure(self) -> str | None:
        if self._sandbox is None:
            return self._teardown_failure
        value = getattr(self._sandbox, "teardown_failure", None)
        return value if isinstance(value, str) else None

    def force_kill(self) -> None:
        force_kill = getattr(self._require_sandbox(), "force_kill", None)
        if callable(force_kill):
            force_kill()

    def _require_sandbox(self) -> _SandboxLike:
        if self._sandbox is None:
            raise PackagingDifferentialError("recording sandbox is not open")
        return self._sandbox


def build_worker_argv(distro_name: str, *, side: SideName) -> tuple[str, ...]:
    _require_staging_distro(distro_name)
    match side:
        case "repo":
            source_env = (f"PYTHONPATH={REPO_SOURCE_ROOT}",)
        case "appliance":
            source_env = ()
        case unreachable:
            assert_never(unreachable)
    return (
        "wsl.exe",
        "-d",
        distro_name,
        "--exec",
        "/usr/bin/env",
        "-i",
        "HOME=/home/lbworker",
        "APPWORLD_ROOT=/home/lbworker/appworld",
        "PYTHONHASHSEED=0",
        "TZ=UTC",
        "LC_ALL=C.UTF-8",
        *source_env,
        "PATH=/opt/localbench/venv/bin:/usr/bin:/bin",
        "/opt/localbench/venv/bin/python",
        "-m",
        "localbench.scoring.agentic_exec.wsl_worker",
    )


def compare_sides(
    repo: SideRun,
    appliance: SideRun,
    task_ids: Sequence[str],
) -> Comparison:
    verdicts: dict[str, bool] = {}
    diffs: list[JsonObject] = []
    for field_name in EQUAL_FIELDS:
        field_equal = True
        if field_name == "aggregates":
            field_equal = _append_diff(diffs, field_name, None, repo.aggregates, appliance.aggregates)
        else:
            for task_id in task_ids:
                repo_value = _trace_field(repo, task_id, field_name)
                appliance_value = _trace_field(appliance, task_id, field_name)
                field_equal = (
                    _append_diff(
                        diffs,
                        field_name,
                        task_id,
                        repo_value,
                        appliance_value,
                    )
                    and field_equal
                )
        verdicts[field_name] = field_equal
    return Comparison(
        field_verdicts=verdicts,
        verdict="pass" if all(verdicts.values()) else "fail",
        diffs=diffs,
    )


def build_evidence(
    *,
    runtime_id: str,
    distro_name: str,
    contract_id: str,
    contract_payload_sha256: str,
    rootfs_sha256: str,
    worker_wheel_sha256: str,
    task_ids: Sequence[str],
    repo: SideRun,
    appliance: SideRun,
    comparison: Comparison,
) -> JsonObject:
    return {
        "schema": SCHEMA,
        "runtime_id": runtime_id,
        "distro_name": distro_name,
        "contract_id": contract_id,
        "contract_payload_sha256": contract_payload_sha256,
        "rootfs_sha256": rootfs_sha256,
        "worker_wheel_sha256": worker_wheel_sha256,
        "task_ids": list(task_ids),
        "per_side": {
            "repo": _side_digest_view(repo, task_ids),
            "appliance": _side_digest_view(appliance, task_ids),
        },
        "equal_fields_verdicts": dict(comparison.field_verdicts),
        "verdict": comparison.verdict,
        "diffs": deepcopy(comparison.diffs),
    }


def write_evidence(path: Path, evidence: JsonObject) -> None:
    write_json_file(path, evidence)


def validate_side_capture(side: SideRun, task_ids: Sequence[str]) -> None:
    if not side.worker_identity:
        raise PackagingDifferentialError("worker hello identity was not captured")
    for task_id in task_ids:
        try:
            trace = side.per_task[task_id]
        except KeyError as error:
            raise PackagingDifferentialError(f"capture is missing task {task_id!r}") from error
        if not trace.model_turn_requests:
            raise PackagingDifferentialError(f"capture is missing model turn requests for {task_id}")
        if not trace.sandbox_operations:
            raise PackagingDifferentialError(f"capture is missing sandbox operations for {task_id}")
        if any("reply" not in event for event in trace.sandbox_operations):
            raise PackagingDifferentialError(f"capture is missing a sandbox reply for {task_id}")
        if trace.finalize_verdict is None:
            raise PackagingDifferentialError(f"capture is missing finalize verdict for {task_id}")
        if len(trace.scored_envelopes) != 1:
            raise PackagingDifferentialError(f"capture requires one scored envelope for {task_id}")
    if not side.aggregates:
        raise PackagingDifferentialError("capture is missing benchmark aggregates")


class _ExplicitArgvWslProxy(WslSandboxProxy):
    def __init__(
        self,
        task_id: str,
        config: WslWorkerConfig,
        argv: tuple[str, ...],
    ) -> None:
        super().__init__(task_id, config)
        self._explicit_argv = argv

    def _start(self) -> None:
        self._worker_token = None
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = (
            self.config.log_dir
            / f"{safe_label(self.task_id or 'preflight')}.{time.time_ns()}.stderr.log"
        )
        self._stderr_handle = log_path.open("ab")
        try:
            self._proc = subprocess.Popen(
                list(self._explicit_argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_handle,
                env=worker_env(self.config, worker_token=None),
                creationflags=creation_flags(),
                start_new_session=sys.platform != "win32",
            )
        except OSError as error:
            self._close_log()
            raise WslTransportError(operation="spawn", detail=str(error)) from error


def stage_repo_source(distro_name: str, repo_source: Path) -> None:
    _require_staging_distro(distro_name)
    source = repo_source.resolve()
    if not source.is_dir() or not (source / "localbench").is_dir():
        raise PackagingDifferentialError(
            f"repo source must contain the localbench package: {source}"
        )
    _run_wsl(distro_name, "/bin/rm", "-rf", "--", REPO_SOURCE_ROOT)
    _run_wsl(distro_name, "/bin/mkdir", "-p", REPO_SOURCE_ROOT)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(source)
            if not path.is_file() or "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            content = path.read_bytes()
            info = tarfile.TarInfo(relative.as_posix())
            info.size = len(content)
            info.mode = path.stat().st_mode & 0o777
            info.mtime = 0
            tar.addfile(info, io.BytesIO(content))
    _run_wsl(distro_name, "/bin/tar", "-xf", "-", "-C", REPO_SOURCE_ROOT, stdin=archive.getvalue())


def remove_staged_source(distro_name: str) -> None:
    _require_staging_distro(distro_name)
    _run_wsl(distro_name, "/bin/rm", "-rf", "--", REPO_SOURCE_ROOT)


def run_side(side_name: SideName, distro_name: str, run: SideRun) -> None:
    missing_scripts = [task_id for task_id in TASK_IDS if task_id not in _TASK_BLOCKS]
    if missing_scripts:
        raise PackagingDifferentialError(
            f"scripted agent has no task script for: {', '.join(missing_scripts)}"
        )
    run.per_task = {task_id: TaskTrace() for task_id in TASK_IDS}
    config = WslWorkerConfig(
        venv_python=VENV_PYTHON,
        appworld_root=APPWORLD_ROOT,
        distro_name=distro_name,
        log_dir=Path("runs") / "packaging-differential" / side_name,
    )
    argv = build_worker_argv(distro_name, side=side_name)

    def model_factory(task_id: str) -> RecordingModel:
        return RecordingModel(ScriptedSolverAgent(task_id), run.per_task[task_id])

    def sandbox_factory(task_id: str) -> RecordingSandboxContext:
        proxy = _ExplicitArgvWslProxy(task_id, config, argv)
        return RecordingSandboxContext(
            proxy,
            run.per_task[task_id],
            identity_sink=lambda identity: _record_worker_identity(run, identity),
        )

    report = run_appworld_c_benchmark(
        task_ids=list(TASK_IDS),
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
    )
    for envelope in _report_envelopes(report, 1):
        identity = envelope.get("identity")
        task_id = identity.get("task_id") if isinstance(identity, dict) else None
        if not isinstance(task_id, str) or task_id not in run.per_task:
            raise PackagingDifferentialError("scored envelope has no supported task identity")
        run.per_task[task_id].scored_envelopes.append(deepcopy(envelope))
    report_payload = report.as_dict()
    report_payload.pop("results", None)
    run.aggregates = report_payload
    validate_side_capture(run, TASK_IDS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare current repo worker behavior with a staged appliance worker"
    )
    parser.add_argument("--distro", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rootfs-sha256", required=True, type=_sha256_argument)
    parser.add_argument("--worker-wheel-sha256", required=True, type=_sha256_argument)
    parser.add_argument("--repo-src", type=Path, default=DEFAULT_REPO_SOURCE)
    parser.add_argument("--keep-staging-copy", action="store_true")
    args = parser.parse_args(argv)
    repo = SideRun(per_task={task_id: TaskTrace() for task_id in TASK_IDS})
    appliance = SideRun(per_task={task_id: TaskTrace() for task_id in TASK_IDS})
    contract_id = CONTRACT_ID
    contract_payload_sha256 = ""
    try:
        _require_staging_distro(args.distro)
        contract = load_execution_contract()
        payload = contract.get("payload")
        if not isinstance(payload, dict):
            raise PackagingDifferentialError("active contract payload is not an object")
        contract_id = str(payload.get("contract_id", CONTRACT_ID))
        contract_payload_sha256 = str(contract.get("payload_sha256", ""))
        try:
            stage_repo_source(args.distro, args.repo_src)
            run_side("appliance", args.distro, appliance)
            run_side("repo", args.distro, repo)
        finally:
            if not args.keep_staging_copy:
                remove_staged_source(args.distro)
        comparison = compare_sides(repo, appliance, TASK_IDS)
    except Exception as error:  # noqa: BROAD_EXCEPT_OK
        comparison = Comparison(
            field_verdicts={field_name: False for field_name in EQUAL_FIELDS},
            verdict="fail",
            diffs=[
                {
                    "field": "driver",
                    "error_type": type(error).__name__,
                    "detail": str(error),
                }
            ],
        )
    evidence = build_evidence(
        runtime_id=PINNED_RUNTIME_ID,
        distro_name=args.distro,
        contract_id=contract_id,
        contract_payload_sha256=contract_payload_sha256,
        rootfs_sha256=args.rootfs_sha256,
        worker_wheel_sha256=args.worker_wheel_sha256,
        task_ids=TASK_IDS,
        repo=repo,
        appliance=appliance,
        comparison=comparison,
    )
    write_evidence(args.out, evidence)
    print(f"verdict={comparison.verdict} evidence={args.out}")
    return 0 if comparison.verdict == "pass" else 1


def _record_worker_identity(run: SideRun, identity: JsonObject) -> None:
    if not run.worker_identity:
        run.worker_identity = deepcopy(identity)
        return
    if canonical_json_bytes(run.worker_identity) != canonical_json_bytes(identity):
        raise PackagingDifferentialError("worker hello identity changed between tasks")


def _run_wsl(
    distro_name: str,
    *command: str,
    stdin: bytes | None = None,
) -> None:
    completed = subprocess.run(
        ["wsl.exe", "-d", distro_name, "--exec", *command],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise PackagingDifferentialError(
            f"WSL command failed with exit {completed.returncode}: {detail or command[0]}"
        )


def _sha256_argument(value: str) -> str:
    normalized = value.lower()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise argparse.ArgumentTypeError("expected a 64-character hexadecimal sha256")
    return normalized


def _require_staging_distro(distro_name: str) -> None:
    if not distro_name.startswith(STAGING_PREFIX):
        raise PackagingDifferentialError(
            f"distro name must start with {STAGING_PREFIX!r}: {distro_name!r}"
        )


def _verdict_payload(verdict: _VerdictLike) -> JsonObject:
    passes = [str(item) for item in verdict.passes]
    failures = [str(item) for item in verdict.failures]
    return {
        "success": bool(verdict.success),
        "collateral_damage": bool(verdict.collateral_damage),
        "passes": passes,
        "failures": failures,
        "num_passes": len(passes),
        "num_failures": len(failures),
    }


def _trace_field(side: SideRun, task_id: str, field_name: EqualField) -> JsonValue:
    try:
        trace = side.per_task[task_id]
    except KeyError as error:
        raise PackagingDifferentialError(f"capture is missing task {task_id!r}") from error
    match field_name:
        case "model_turn_requests":
            return trace.model_turn_requests
        case "sandbox_operations":
            return trace.sandbox_operations
        case "finalize_verdict":
            return trace.finalize_verdict
        case "scored_envelopes":
            return trace.scored_envelopes
        case "aggregates":
            raise PackagingDifferentialError("aggregates are not a per-task trace field")
        case unreachable:
            assert_never(unreachable)


def _append_diff(
    diffs: list[JsonObject],
    field_name: str,
    task_id: str | None,
    repo_value: JsonValue,
    appliance_value: JsonValue,
) -> bool:
    if canonical_json_bytes(repo_value) == canonical_json_bytes(appliance_value):
        return True
    difference: JsonObject = {
        "field": field_name,
        "repo_sha256": canonical_json_hash(repo_value),
        "appliance_sha256": canonical_json_hash(appliance_value),
        "repo": deepcopy(repo_value),
        "appliance": deepcopy(appliance_value),
    }
    if task_id is not None:
        difference["task_id"] = task_id
    diffs.append(difference)
    return False


def _side_digest_view(side: SideRun, task_ids: Sequence[str]) -> JsonObject:
    per_task: JsonObject = {}
    for task_id in task_ids:
        per_task[task_id] = {
            field_name: canonical_json_hash(_trace_field(side, task_id, field_name))
            for field_name in EQUAL_FIELDS
            if field_name != "aggregates"
        }
    return {
        "worker_identity": deepcopy(side.worker_identity),
        "per_task": per_task,
        "aggregates_sha256": canonical_json_hash(side.aggregates),
    }


if __name__ == "__main__":
    raise SystemExit(main())
