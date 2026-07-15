from __future__ import annotations

import copy
import json
import sys
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from localbench._types import ChatMessage, JsonObject, JsonValue
from localbench.scoring.agentic_exec import benchmark, execution_contract
from localbench.scoring.agentic_exec.model_client import GenerationParams, ModelResponse


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
    )


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
    ],
)
def test_comparator_names_each_perturbed_field(field: str, perturb) -> None:
    repo = _side_run()
    appliance = copy.deepcopy(repo)
    perturb(repo)

    comparison = differential.compare_sides(repo, appliance, ("fac291d_1",))

    assert comparison.verdict == "fail"
    assert comparison.field_verdicts[field] is False
    assert {str(item["field"]) for item in comparison.diffs} == {field}


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


def test_spawn_argv_pins_clean_environment_and_repo_path() -> None:
    distro = "LocalBench-Staging-runtime-1"

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
