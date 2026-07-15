from __future__ import annotations

# noqa: SIZE_OK — one authorized test module mirrors the single repo-only driver lifecycle

import copy
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from localbench._types import ChatMessage, JsonObject, JsonValue
from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.scoring.agentic_exec import benchmark, execution_contract
from localbench.scoring.agentic_exec.model_client import GenerationParams, ModelResponse
from localbench.scoring.agentic_exec.sandbox import WorkerSetupError
from localbench.scoring.agentic_exec.worker_identity import _WORKER_MODULES
from localbench.scoring.agentic_exec.wsl_process import WslWorkerConfig
from localbench.submissions.canon import canonical_json_hash


_TOOL_PATH = Path(__file__).parents[1] / "tools/packaging_differential.py"
sys.path.insert(0, str(_TOOL_PATH.parent))

import packaging_differential as differential  # noqa: E402


@pytest.fixture(autouse=True)
def _passed_execution_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "contract")


def test_packaging_differential_tool_is_repo_only() -> None:
    assert _TOOL_PATH.is_file()


def _side_run() -> differential.SideRun:
    trace = differential.TaskTrace(
        model_turn_requests=[
            {
                "messages": [{"role": "user", "content": "request"}],
                "params": {"seed": 0},
            }
        ],
        sandbox_operations=[
            {"request": {"op": "run_block", "code": "print(1)"}, "reply": {"kind": "ok"}},
            {"request": {"op": "finalize", "answer": 1}, "reply": {"kind": "ok"}},
        ],
        finalize_verdict={"success": True, "collateral_damage": False},
        scored_envelopes=[{"result": {"success": True}, "payload_sha256": "a" * 64}],
    )
    return differential.SideRun(
        worker_identity={"worker_content_sha256": "b" * 64},
        per_task={"fac291d_1": trace},
        aggregates={"tasks_total": 1, "agentic_success_rate": 1.0},
        spawn_argv=("wsl.exe", "--worker"),
        module_origins=_module_origins("/opt/localbench/diff-src/"),
        cwd="/tmp/differential-neutral-cwd",
    )


def _staging_distro() -> str:
    return f"LocalBench-Staging-test-{PINNED_RUNTIME_ID}"


def _module_origins(prefix: str) -> JsonObject:
    origins: JsonObject = {
        module_name: f"{prefix}{module_name.replace('.', '/')}.py"
        for module_name in _WORKER_MODULES
    }
    origins.update(
        {
            "localbench": f"{prefix}localbench/__init__.py",
            "sys_prefix": "/opt/localbench/venv",
            "sys_path": [
                prefix.rstrip("/"),
                "/opt/localbench/venv/lib/python3.12/site-packages",
            ],
        }
    )
    return origins


def _worker_source_tree(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    source = tmp_path / "src"
    files: dict[str, bytes] = {}
    for index, module_name in enumerate(_WORKER_MODULES):
        relative = f"{module_name.replace('.', '/')}.py"
        content = f"VALUE = {index}\n".encode()
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        files[relative] = content
    return source, files


def test_comparator_passes_equal_traces() -> None:
    repo = _side_run()
    appliance = copy.deepcopy(repo)

    comparison = differential.compare_sides(repo, appliance, ("fac291d_1",))

    assert comparison.verdict == "pass"
    assert comparison.field_verdicts == {
        "model_turn_requests": True,
        "sandbox_operations": True,
        "finalize_verdict": True,
        "scored_envelopes": True,
        "aggregates": True,
        "worker_identity": True,
    }
    assert comparison.diffs == []


@pytest.mark.parametrize(
    ("field", "perturb"),
    [
        (
            "model_turn_requests",
            lambda side: side.per_task["fac291d_1"].model_turn_requests[0]["messages"][0].__setitem__(
                "content", "requesu"
            ),
        ),
        (
            "sandbox_operations",
            lambda side: side.per_task["fac291d_1"].sandbox_operations.reverse(),
        ),
        (
            "finalize_verdict",
            lambda side: side.per_task["fac291d_1"].finalize_verdict.__setitem__(
                "success", False
            ),
        ),
        (
            "scored_envelopes",
            lambda side: side.per_task["fac291d_1"].scored_envelopes[0]["result"].__setitem__(
                "success", False
            ),
        ),
        (
            "aggregates",
            lambda side: side.aggregates.__setitem__("agentic_success_rate", 0.0),
        ),
        (
            "worker_identity",
            lambda side: side.worker_identity.__setitem__(
                "worker_content_sha256", "c" * 64
            ),
        ),
    ],
)
def test_comparator_names_each_perturbed_field(field: str, perturb) -> None:
    repo = _side_run()
    appliance = copy.deepcopy(repo)
    perturb(repo)

    comparison = differential.compare_sides(repo, appliance, ("fac291d_1",))

    assert comparison.verdict == "fail"
    assert comparison.field_verdicts[field] is False
    diff_fields = {str(item["field"]) for item in comparison.diffs}
    assert field in diff_fields
    assert diff_fields <= {field, "task_success"}


def test_evidence_writer_is_byte_deterministic(tmp_path: Path) -> None:
    repo = _side_run()
    appliance = copy.deepcopy(repo)
    comparison = differential.compare_sides(repo, appliance, ("fac291d_1",))
    evidence = differential.build_evidence(
        runtime_id="runtime-1",
        distro_name="LocalBench-Staging-runtime-1",
        contract_id="contract-1",
        contract_payload_sha256="c" * 64,
        rootfs_sha256="d" * 64,
        worker_wheel_sha256="e" * 64,
        task_ids=("fac291d_1",),
        repo=repo,
        appliance=appliance,
        comparison=comparison,
        staged_source=differential.StagedSource(
            staged_file_count=42,
            staged_manifest_sha256="f" * 64,
        ),
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    differential.write_evidence(first, evidence)
    differential.write_evidence(second, evidence)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")
    parsed = json.loads(first.read_text(encoding="utf-8"))
    assert parsed["schema"] == "localbench.packaging_differential.v1"
    assert parsed["verdict"] == "pass"
    assert set(parsed["per_side"]) == {"appliance", "repo"}
    assert set(parsed["per_side"]["repo"]["per_task"]["fac291d_1"]) == {
        "finalize_verdict",
        "model_turn_requests",
        "sandbox_operations",
        "scored_envelopes",
    }
    assert parsed["per_side"]["repo"]["spawn_argv"] == ["wsl.exe", "--worker"]
    assert parsed["per_side"]["repo"]["module_origins"] == repo.module_origins
    assert parsed["per_side"]["repo"]["cwd"] == "/tmp/differential-neutral-cwd"
    assert parsed["per_side"]["repo"]["aggregates"]["agentic_success_rate"] == 1.0
    assert parsed["staged_source"] == {
        "staged_file_count": 42,
        "staged_manifest_sha256": "f" * 64,
    }


def test_spawn_argv_pins_clean_environment_and_repo_path() -> None:
    distro = _staging_distro()

    appliance = differential.build_worker_argv(distro, side="appliance")
    repo = differential.build_worker_argv(distro, side="repo")

    assert appliance == (
        "wsl.exe",
        "-d",
        distro,
        "--exec",
        "/usr/bin/env",
        "-i",
        "HOME=/home/lbworker",
        "APPWORLD_ROOT=/home/lbworker/appworld",
        "PYTHONHASHSEED=0",
        "TZ=UTC",
        "LC_ALL=C.UTF-8",
        "PATH=/opt/localbench/venv/bin:/usr/bin:/bin",
        "/opt/localbench/venv/bin/python",
        "-m",
        "localbench.scoring.agentic_exec.wsl_worker",
    )
    assert repo == (*appliance[:11], "PYTHONPATH=/opt/localbench/diff-src", *appliance[11:])


def test_spawn_argv_refuses_non_staging_distro() -> None:
    with pytest.raises(differential.PackagingDifferentialError, match="LocalBench-Staging-"):
        differential.build_worker_argv("LocalBench-runtime-1", side="appliance")


def test_spawn_argv_refuses_staging_distro_for_foreign_runtime() -> None:
    with pytest.raises(differential.PackagingDifferentialError, match="pinned runtime"):
        differential.build_worker_argv(
            "LocalBench-Staging-foreign-runtime",
            side="appliance",
        )


@pytest.mark.parametrize(
    ("side", "prefix"),
    [
        ("repo", "/opt/localbench/diff-src/"),
        ("appliance", "/opt/localbench/venv/"),
    ],
)
def test_module_origin_assertion_accepts_expected_tree(
    side: differential.SideName,
    prefix: str,
) -> None:
    differential.assert_module_origins(side, _module_origins(prefix))


def test_module_origin_assertion_rejects_repo_fallback_to_venv() -> None:
    with pytest.raises(differential.PackagingDifferentialError, match="diff-src"):
        differential.assert_module_origins(
            "repo",
            _module_origins("/opt/localbench/venv/"),
        )


def test_module_origin_assertion_rejects_mixed_trees() -> None:
    origins = _module_origins("/opt/localbench/diff-src/")
    mismatched_module = _WORKER_MODULES[-1]
    origins[mismatched_module] = (
        "/opt/localbench/venv/lib/python3.12/site-packages/mixed.py"
    )

    with pytest.raises(
        differential.PackagingDifferentialError, match=mismatched_module
    ):
        differential.assert_module_origins("repo", origins)


def test_module_origin_probe_reuses_spawn_environment_and_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "neutral"
    cwd.mkdir()
    context = differential.SpawnContext(distro_name=_staging_distro(), cwd=cwd)
    config = WslWorkerConfig(
        venv_python=differential.VENV_PYTHON,
        appworld_root=differential.APPWORLD_ROOT,
        distro_name=context.distro_name,
        log_dir=tmp_path / "logs",
    )
    origins = _module_origins("/opt/localbench/diff-src/")
    captured: dict[str, JsonValue] = {}

    def fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["cwd"] = str(kwargs["cwd"])
        captured["env"] = dict(kwargs["env"])
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(origins, sort_keys=True, separators=(",", ":")) + "\n",
            stderr="",
        )

    monkeypatch.setattr(differential.subprocess, "run", fake_run)

    observed = differential.run_module_origin_probe("repo", context, config)

    worker_argv = differential.build_worker_argv(context.distro_name, side="repo")
    assert captured["argv"][:-2] == list(worker_argv[:-2])
    assert captured["argv"][-2] == "-c"
    assert captured["cwd"] == str(cwd)
    assert observed == origins


def test_worker_spawn_pins_neutral_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "neutral"
    cwd.mkdir()
    config = WslWorkerConfig(
        venv_python=differential.VENV_PYTHON,
        appworld_root=differential.APPWORLD_ROOT,
        distro_name=_staging_distro(),
        log_dir=tmp_path / "logs",
    )
    captured: dict[str, JsonValue] = {}

    def fake_popen(argv: list[str], **kwargs):
        captured["argv"] = argv
        captured["cwd"] = str(kwargs["cwd"])
        return object()

    monkeypatch.setattr(differential.subprocess, "Popen", fake_popen)
    proxy = differential._ExplicitArgvWslProxy("task", config, ("worker",), cwd)

    proxy._start()
    proxy._close_log()

    assert captured == {"argv": ["worker"], "cwd": str(cwd)}


def test_stage_repo_source_fails_closed_when_worker_module_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src"
    (source / "localbench").mkdir(parents=True)
    (source / "localbench/__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(differential, "_run_wsl", lambda *_args, **_kwargs: b"")

    with pytest.raises(differential.PackagingDifferentialError, match="worker modules"):
        differential.stage_repo_source(_staging_distro(), source)


def test_stage_repo_source_verifies_hashes_and_mutates_only_archived_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, original_files = _worker_source_tree(tmp_path)
    archived_files: dict[str, bytes] = {}

    def fake_run_wsl(_distro: str, *command: str, stdin: bytes | None = None) -> bytes:
        if command[0] == "/bin/tar":
            assert stdin is not None
            with tarfile.open(fileobj=io.BytesIO(stdin), mode="r") as archive:
                for member in archive.getmembers():
                    extracted = archive.extractfile(member)
                    assert extracted is not None
                    archived_files[member.name] = extracted.read()
        if command[0] == "/usr/bin/sha256sum":
            return "".join(
                f"{hashlib.sha256(archived_files[path.removeprefix(differential.REPO_SOURCE_ROOT + '/')]).hexdigest()}  {path}\n"
                for path in command[1:]
            ).encode()
        return b""

    monkeypatch.setattr(differential, "_run_wsl", fake_run_wsl)

    staged = differential.stage_repo_source(
        _staging_distro(),
        source,
        mutate_module="localbench.scoring.agentic_exec.wsl_worker",
    )

    changed = [
        name
        for name, content in archived_files.items()
        if content != original_files[name]
    ]
    assert changed == ["localbench/scoring/agentic_exec/wsl_worker.py"]
    assert archived_files[changed[0]].endswith(
        b"# packaging differential self-test mutation\n"
    )
    assert {
        name: (source / name).read_bytes() for name in original_files
    } == original_files
    manifest = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in archived_files.items()
    }
    assert staged == differential.StagedSource(
        staged_file_count=len(original_files),
        staged_manifest_sha256=canonical_json_hash(manifest),
    )


def test_stage_repo_source_fails_closed_on_extracted_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _original_files = _worker_source_tree(tmp_path)

    def fake_run_wsl(_distro: str, *command: str, stdin: bytes | None = None) -> bytes:
        if command[0] == "/usr/bin/sha256sum":
            return "".join(f"{'0' * 64}  {path}\n" for path in command[1:]).encode()
        return b""

    monkeypatch.setattr(differential, "_run_wsl", fake_run_wsl)

    with pytest.raises(differential.PackagingDifferentialError, match="hash mismatch"):
        differential.stage_repo_source(_staging_distro(), source)


def test_comparison_fails_when_equal_task_verdicts_are_unsuccessful() -> None:
    repo = _side_run()
    appliance = copy.deepcopy(repo)
    repo.per_task["fac291d_1"].finalize_verdict["success"] = False
    appliance.per_task["fac291d_1"].finalize_verdict["success"] = False

    comparison = differential.compare_sides(repo, appliance, ("fac291d_1",))

    assert comparison.verdict == "fail"
    assert comparison.field_verdicts["finalize_verdict"] is True
    assert comparison.diffs == [
        {
            "field": "task_success",
            "side": "repo",
            "task_id": "fac291d_1",
            "verdict": repo.per_task["fac291d_1"].finalize_verdict,
        },
        {
            "field": "task_success",
            "side": "appliance",
            "task_id": "fac291d_1",
            "verdict": appliance.per_task["fac291d_1"].finalize_verdict,
        },
    ]


def test_self_test_accepts_identity_failure_and_writes_fail_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "self-test.json"
    removed: list[str] = []
    spawned: list[tuple[tuple[str, ...], Path]] = []
    staged = differential.StagedSource(9, "a" * 64)

    def fake_stage(
        distro_name: str,
        repo_source: Path,
        *,
        mutate_module: str | None = None,
    ) -> differential.StagedSource:
        assert distro_name == _staging_distro()
        assert repo_source == differential.DEFAULT_REPO_SOURCE
        assert mutate_module == "localbench.scoring.agentic_exec.wsl_worker"
        return staged

    class IdentityFailingSpawn(AbstractContextManager["IdentityFailingSpawn"]):
        def __init__(
            self,
            _task_id: str,
            _config: WslWorkerConfig,
            worker_argv: tuple[str, ...],
            cwd: Path,
        ) -> None:
            spawned.append((worker_argv, cwd))

        def __enter__(self) -> IdentityFailingSpawn:
            raise WorkerSetupError("wsl worker error: agentic execution contract drift")

        def __exit__(self, *_exc) -> None:
            return None

    monkeypatch.setattr(differential, "stage_repo_source", fake_stage)
    monkeypatch.setattr(differential, "_ExplicitArgvWslProxy", IdentityFailingSpawn)
    monkeypatch.setattr(
        differential,
        "run_module_origin_probe",
        lambda *_args: _module_origins("/opt/localbench/diff-src/"),
    )
    monkeypatch.setattr(differential, "remove_staged_source", removed.append)
    monkeypatch.setattr(
        differential,
        "load_execution_contract",
        lambda: {"payload": {"contract_id": "contract-1"}, "payload_sha256": "b" * 64},
    )

    exit_code = differential.main(
        [
            "--distro",
            _staging_distro(),
            "--out",
            str(out),
            "--rootfs-sha256",
            "c" * 64,
            "--worker-wheel-sha256",
            "d" * 64,
            "--self-test",
        ]
    )

    evidence = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "SELF-TEST OK"
    assert evidence["verdict"] == "fail"
    assert evidence["staged_source"] == asdict(staged)
    assert evidence["diffs"] == [
        {
            "field": "startup_failure",
            "side": "repo",
            "error_type": "WorkerSetupError",
            "detail": "wsl worker error: agentic execution contract drift",
        }
    ]
    assert removed == [_staging_distro()]
    assert len(spawned) == 1
    assert spawned[0][0] == differential.build_worker_argv(_staging_distro(), side="repo")
    assert spawned[0][1].parent == tmp_path


@pytest.mark.parametrize(
    ("failure", "expected_verdict"),
    [(None, "pass"), (differential.PackagingDifferentialError("spawn failed"), "fail")],
)
def test_self_test_rejects_pass_or_non_identity_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: differential.PackagingDifferentialError | None,
    expected_verdict: str,
) -> None:
    out = tmp_path / "self-test-failed.json"
    monkeypatch.setattr(
        differential,
        "stage_repo_source",
        lambda *_args, **_kwargs: differential.StagedSource(9, "a" * 64),
    )

    def fake_run_side(
        _side_name: str,
        _context: differential.SpawnContext,
        _run: differential.SideRun,
    ) -> None:
        if failure is not None:
            raise failure

    monkeypatch.setattr(differential, "run_side", fake_run_side)
    monkeypatch.setattr(differential, "remove_staged_source", lambda _distro: None)
    monkeypatch.setattr(
        differential,
        "load_execution_contract",
        lambda: {"payload": {"contract_id": "contract-1"}, "payload_sha256": "b" * 64},
    )

    exit_code = differential.main(
        [
            "--distro",
            _staging_distro(),
            "--out",
            str(out),
            "--rootfs-sha256",
            "c" * 64,
            "--worker-wheel-sha256",
            "d" * 64,
            "--self-test",
        ]
    )

    evidence = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert capsys.readouterr().out.startswith("SELF-TEST FAILED")
    assert evidence["verdict"] == expected_verdict


def test_capture_validation_fails_closed_on_capture_gap() -> None:
    side = differential.SideRun(
        worker_identity={"worker_content_sha256": "a" * 64},
        per_task={"fac291d_1": differential.TaskTrace()},
    )

    with pytest.raises(differential.PackagingDifferentialError, match="model turn"):
        differential.validate_side_capture(side, ("fac291d_1",))


@dataclass(frozen=True, slots=True)
class _Observation:
    stdout: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _Verdict:
    success: bool
    collateral_damage: bool = False
    passes: tuple[str, ...] = ("passed",)
    failures: tuple[str, ...] = ()


class _FakeSandbox(AbstractContextManager["_FakeSandbox"]):
    def __init__(self) -> None:
        self.answer: JsonValue = None
        self.requests: list[JsonObject] = []

    def __enter__(self) -> _FakeSandbox:
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def run_block(self, code: str) -> _Observation:
        self.requests.append({"op": "run_block", "code": code})
        if "__LB_CTX__" in code:
            return _Observation(
                stdout='__LB_CTX__{"instruction":"Return one","email":"boss@example.com"}'
            )
        if "__LB_ANSWER__" in code:
            return _Observation(stdout=f"__LB_ANSWER__{json.dumps(self.answer)}")
        self.answer = 1
        return _Observation(stdout="set")

    def finalize(self, answer: JsonValue) -> _Verdict:
        self.requests.append({"op": "finalize", "answer": answer})
        return _Verdict(success=answer == 1)

class _OneTurnModel:
    def __init__(self) -> None:
        self.requests: list[tuple[list[ChatMessage], GenerationParams]] = []

    def complete(
        self,
        messages: list[ChatMessage],
        params: GenerationParams,
    ) -> ModelResponse:
        self.requests.append((copy.deepcopy(messages), params))
        return ModelResponse("```python\nanswer = 1\n```\nFINAL_ANSWER")


def test_capture_wrappers_are_observation_only_for_report() -> None:
    plain_model = _OneTurnModel()
    plain_sandbox = _FakeSandbox()
    plain_report = benchmark.run_appworld_c_benchmark(
        task_ids=["fake-task"],
        model_factory=lambda _task_id: plain_model,
        sandbox_factory=lambda _task_id: plain_sandbox,
    )
    captured_model = _OneTurnModel()
    captured_sandbox = _FakeSandbox()
    trace = differential.TaskTrace()
    captured_report = benchmark.run_appworld_c_benchmark(
        task_ids=["fake-task"],
        model_factory=lambda _task_id: differential.RecordingModel(captured_model, trace),
        sandbox_factory=lambda _task_id: differential.RecordingSandboxContext(
            captured_sandbox,
            trace,
        ),
    )

    assert captured_report.as_dict() == plain_report.as_dict()
    assert trace.model_turn_requests == [
        {
            "messages": captured_model.requests[0][0],
            "params": asdict(captured_model.requests[0][1]),
        }
    ]
    assert [event["request"] for event in trace.sandbox_operations] == captured_sandbox.requests
    assert trace.finalize_verdict == {
        "success": True,
        "collateral_damage": False,
        "passes": ["passed"],
        "failures": [],
        "num_passes": 1,
        "num_failures": 0,
    }
