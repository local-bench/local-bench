"""GPU-free unit tests for the AppWorld-C funnel harness + the chat-completions client.

These prove the whole staged-campaign orchestration end-to-end with NO model, NO server, NO GPU,
and NO bwrap/appworld:

  * **ChatCompletionsClient** — request shape (against a MOCK transport), response parsing, and the
    documented graceful-degradation contract (timeout / non-200 / malformed -> empty format-failure
    ModelResponse). The transport is monkeypatched; there is NO live endpoint.
  * **Frozen subset selection** — determinism (same inputs -> same ids + same manifest hash),
    stratified coverage, seed sensitivity, size clamping, and the freeze-hash stability.
  * **Funnel orchestration** — run + persist a stage (JSON shape on disk via tmp_path), the LOCKED
    2-rerun rule + run-to-run abs-delta + the 3rd-run-on->5pp-drift trigger, the early-stop check
    (near-zero / near-perfect / harness-dominated / within-noise), and rerun aggregation.

The loop + sandbox are reused via a deterministic in-memory ``FakeSandbox`` (the same kind of
double the Protocol C unit tests use) and the scripted / mock model clients. Runs anywhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench._types import ChatMessage  # noqa: E402
from localbench.scoring.agentic_exec import funnel as fn  # noqa: E402
from localbench.scoring.agentic_exec import scripted_agent as sa  # noqa: E402
from localbench.scoring.agentic_exec.chat_client import (  # noqa: E402
    ERROR_FINISH_REASON,
    ChatCompletionsClient,
)
from localbench.scoring.agentic_exec.loop_config import LoopConfig  # noqa: E402
from localbench.scoring.agentic_exec.loop_types import (  # noqa: E402
    BenchmarkReport,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.model_client import (  # noqa: E402
    GenerationParams,
    ModelResponse,
)

# Reuse the in-memory sandbox double + stub instruction constants from the Protocol C unit tests.
from test_appworld_protocol_c_units import (  # noqa: E402
    _50E_INSTR,
    _FAC_INSTR,
    FakeSandbox,
)


# ==================================================================================================
# ChatCompletionsClient — request shape + parsing + error handling (MOCK transport).
# ==================================================================================================
def _ok_body(content: str, finish_reason: str = "stop", completion_tokens: int = 17) -> str:
    return json.dumps(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": completion_tokens},
        }
    )


def test_chat_client_builds_openai_request_shape() -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000/", "qwen-test", api_key="secret")
    msgs: list[ChatMessage] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    params = GenerationParams(temperature=0.0, top_p=1.0, seed=0, max_output_tokens=1024)
    payload = client._build_payload(msgs, params)

    assert payload["model"] == "qwen-test"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    # the locked sampler intent is mapped onto the request body
    assert payload["temperature"] == 0.0
    assert payload["top_p"] == 1.0
    assert payload["seed"] == 0
    assert payload["max_tokens"] == 1024
    assert payload["stream"] is False
    # endpoint assembled from base_url + standard chat path (trailing slash stripped)
    assert client.endpoint == "http://127.0.0.1:8000/v1/chat/completions"
    # auth header present when api_key given
    req = client._build_request(payload)
    assert req.headers["Authorization"] == "Bearer secret"
    assert req.get_method() == "POST"


def test_chat_client_parses_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    captured: dict[str, object] = {}

    def fake_post(payload: dict[str, object]) -> tuple[int, str]:
        captured["payload"] = payload
        return 200, _ok_body("```python\nprint(1)\n```", "stop", completion_tokens=42)

    monkeypatch.setattr(client, "_post", fake_post)
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())

    assert isinstance(resp, ModelResponse)
    assert resp.text == "```python\nprint(1)\n```"
    assert resp.finish_reason == "stop"
    assert resp.output_tokens == 42
    # the payload actually carried the messages through
    assert captured["payload"]["messages"] == [{"role": "user", "content": "go"}]  # type: ignore[index]


def test_chat_client_maps_length_finish_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    monkeypatch.setattr(
        client, "_post", lambda p: (200, _ok_body("trunc", "length", completion_tokens=1024))
    )
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    # "length" passes through so the loop can treat it as a token-cap format failure
    assert resp.finish_reason == "length"
    assert resp.text == "trunc"


def test_chat_client_non_200_is_format_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    monkeypatch.setattr(client, "_post", lambda p: (500, "internal error"))
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    assert resp.text == ""
    assert resp.finish_reason == ERROR_FINISH_REASON
    assert resp.output_tokens == 0


def test_chat_client_timeout_sentinel_is_format_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    # status 0 == no response at all (timeout / connection refused)
    monkeypatch.setattr(client, "_post", lambda p: (0, "TimeoutError: timed out"))
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    assert resp.text == ""
    assert resp.finish_reason == ERROR_FINISH_REASON


def test_chat_client_malformed_json_is_format_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    monkeypatch.setattr(client, "_post", lambda p: (200, "not json {"))
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    assert resp.text == ""
    assert resp.finish_reason == ERROR_FINISH_REASON


def test_chat_client_missing_content_is_format_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    body = json.dumps({"choices": [{"index": 0, "message": {"role": "assistant"}}]})
    monkeypatch.setattr(client, "_post", lambda p: (200, body))
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    assert resp.text == ""
    assert resp.finish_reason == ERROR_FINISH_REASON


def test_chat_client_missing_usage_yields_none_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")
    body = json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}
    )
    monkeypatch.setattr(client, "_post", lambda p: (200, body))
    resp = client.complete([{"role": "user", "content": "go"}], GenerationParams())
    assert resp.text == "ok"
    assert resp.finish_reason == "stop"
    assert resp.output_tokens is None  # loop then falls back to its own estimate


def test_chat_client_no_auth_header_when_keyless() -> None:
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")  # no api_key
    req = client._build_request(client._build_payload([], GenerationParams()))
    assert "Authorization" not in req.headers


def test_chat_client_post_uses_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    """_post returns (status, body) by reading urlopen — exercised via a fake urlopen (no socket)."""
    client = ChatCompletionsClient("http://127.0.0.1:8000", "m")

    class _Resp:
        status = 200

        def read(self) -> bytes:
            return _ok_body("hello").encode("utf-8")

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    import urllib.request as _u

    monkeypatch.setattr(_u, "urlopen", lambda req, timeout=0: _Resp())
    status, body = client._post(client._build_payload([], GenerationParams()))
    assert status == 200
    assert "hello" in body


def test_chat_client_drives_loop_through_fakesandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: a ChatCompletionsClient whose transport REPLAYS the scripted solver solves a
    task through the real loop + FakeSandbox — proving the client is a drop-in for the GPU run."""
    from localbench.scoring.agentic_exec.protocol_c_loop import run_task

    scripted = sa.ScriptedSolverAgent("fac291d_1")
    client = ChatCompletionsClient("http://127.0.0.1:8000", "replayer")

    def replay_post(payload: dict[str, object]) -> tuple[int, str]:
        # Turn the OpenAI messages back into the loop's ChatMessage list, ask the scripted agent
        # what it would say, and wrap it as a chat-completions 200 — a faithful server stand-in.
        msgs = [
            {"role": m["role"], "content": m["content"]}
            for m in payload["messages"]  # type: ignore[union-attr]
        ]
        rsp = scripted.complete(msgs, GenerationParams())  # type: ignore[arg-type]
        return 200, _ok_body(rsp.text, rsp.finish_reason, completion_tokens=len(rsp.text) // 4)

    monkeypatch.setattr(client, "_post", replay_post)

    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    result = run_task(sandbox, client, "fac291d_1")
    assert result.success is True
    assert result.outcome == TaskOutcome.SUCCESS
    assert result.diagnostics.total_output_tokens > 0  # real completion_tokens threaded through


# ==================================================================================================
# Frozen subset selection — determinism, freeze hash, stratification, seed sensitivity.
# ==================================================================================================
def _synthetic_ids(n: int, prefix: str = "t") -> list[str]:
    # ids that look like AppWorld ids: 7-hex-ish + _1. Deterministic, not tied to selection.
    return [f"{prefix}{i:06x}_1" for i in range(n)]


def test_select_subset_is_deterministic_and_hash_stable() -> None:
    ids = _synthetic_ids(168)
    a = fn.select_subset("scored96", "test_normal", 96, ids, seed=fn.SELECTION_SEED)
    b = fn.select_subset("scored96", "test_normal", 96, list(reversed(ids)), seed=fn.SELECTION_SEED)
    assert a.task_ids == b.task_ids  # order of the input pool must not matter
    assert a.manifest_hash == b.manifest_hash
    assert len(a.task_ids) == 96
    assert len(set(a.task_ids)) == 96  # no duplicates


def test_select_subset_seed_changes_selection() -> None:
    ids = _synthetic_ids(168)
    a = fn.select_subset("s", "test_normal", 96, ids, seed=1)
    b = fn.select_subset("s", "test_normal", 96, ids, seed=2)
    assert a.task_ids != b.task_ids  # a different pre-registration seed yields a different sample
    assert a.manifest_hash != b.manifest_hash


def test_select_subset_clamps_to_pool_size() -> None:
    ids = _synthetic_ids(40)
    spec = fn.select_subset("lite", "dev", 96, ids)  # ask for more than exist
    assert spec.size == 40
    assert set(spec.task_ids) == set(ids)


def test_select_subset_stratifies_across_difficulty() -> None:
    # 30 tasks across 3 difficulty bands; selecting 9 should pull ~3 from each band (round-robin).
    ids = _synthetic_ids(30)
    metadata = {
        tid: fn.TaskMeta(task_id=tid, difficulty=(i % 3) + 1, primary_app=("spotify", "venmo")[i % 2])
        for i, tid in enumerate(ids)
    }
    spec = fn.select_subset("strat", "dev", 9, ids, metadata=metadata)
    bands = [metadata[t].difficulty for t in spec.task_ids]
    # each of the 3 bands is represented (stratified, not all from one band)
    assert set(bands) == {1, 2, 3}
    # round-robin keeps the bands balanced (no band has more than ceil(9/3)+1)
    for band in (1, 2, 3):
        assert bands.count(band) >= 2


def test_subset_for_stage_maps_splits_and_sizes() -> None:
    pools = {
        "dev": _synthetic_ids(57, "d"),
        "test_normal": _synthetic_ids(168, "n"),
    }
    smoke = fn.subset_for_stage(fn.Stage.SMOKE, pools)
    lite = fn.subset_for_stage(fn.Stage.LITE, pools)
    scored = fn.subset_for_stage(fn.Stage.SCORED, pools)
    assert smoke.split == "dev" and smoke.size == fn.SMOKE_SIZE
    assert lite.split == "dev" and lite.size == fn.LITE_SIZE == 36
    assert scored.split == "test_normal" and scored.size == fn.SCORED_SIZE == 96
    # wide smoke option
    wide = fn.subset_for_stage(fn.Stage.SMOKE, pools, wide_smoke=True)
    assert wide.size == fn.SMOKE_SIZE_EXT
    # smoke is a strict subset prefix-stable relative to itself across calls (determinism)
    assert smoke.task_ids == fn.subset_for_stage(fn.Stage.SMOKE, pools).task_ids


def test_subset_for_stage_missing_pool_raises() -> None:
    with pytest.raises(KeyError):
        fn.subset_for_stage(fn.Stage.SCORED, {"dev": _synthetic_ids(57)})  # no test_normal pool


def test_smoke_lite_drawn_from_dev_scored_from_test_normal() -> None:
    # lock the pre-registered split assignment (calibration dev vs scored test_normal).
    assert fn.SMOKE_SPLIT == "dev"
    assert fn.LITE_SPLIT == "dev"
    assert fn.SCORED_SPLIT == "test_normal"


# ==================================================================================================
# Funnel orchestration — run+persist, reruns+delta, early-stop, aggregation (FakeSandbox).
# ==================================================================================================
_GOLDS = {"fac291d_1": (5, _FAC_INSTR), "50e1ac9_1": ("Bravo, Delta, Alpha", _50E_INSTR)}


def _fake_sandbox_factory(task_id: str) -> FakeSandbox:
    gold, instr = _GOLDS[task_id]
    return FakeSandbox(gold_answer=gold, instruction=instr, supervisor_email="b@x.com")


def _scripted_factory(task_id: str) -> sa.ScriptedSolverAgent:
    return sa.ScriptedSolverAgent(task_id)


def _two_task_subset() -> fn.SubsetSpec:
    # a tiny frozen subset using the two solvable tasks, so the loop actually runs to success.
    return fn.SubsetSpec(
        name="mock2", split="dev", size=2, seed=0, task_ids=("fac291d_1", "50e1ac9_1")
    )


def test_run_stage_runs_and_persists_report(tmp_path: Path) -> None:
    subset = _two_task_subset()
    res = fn.run_stage(
        label="mock-model",
        stage=fn.Stage.SMOKE,
        subset=subset,
        model_factory=_scripted_factory,
        sandbox_factory=_fake_sandbox_factory,
        run_index=1,
        results_dir=tmp_path,
        endpoint="http://127.0.0.1:8000/v1/chat/completions",
        model_id="mock-model",
    )
    assert res.report.agentic_success_rate == 1.0
    assert res.report.tasks_total == 2
    assert res.subset_hash == subset.manifest_hash
    # a results JSON was written with the documented self-describing shape
    assert res.results_path is not None
    on_disk = json.loads(Path(res.results_path).read_text(encoding="utf-8"))
    assert on_disk["schema"] == "appworld-c-funnel-run/v1"
    assert on_disk["label"] == "mock-model"
    assert on_disk["stage"] == "smoke"
    assert on_disk["subset"]["manifest_hash"] == subset.manifest_hash
    assert on_disk["subset"]["task_ids"] == ["fac291d_1", "50e1ac9_1"]
    # the full BenchmarkReport (ASR + diagnostic rates + per-task rows) is embedded
    rep = on_disk["report"]
    assert rep["agentic_success_rate"] == 1.0
    assert len(rep["results"]) == 2
    assert {r["task_id"] for r in rep["results"]} == {"fac291d_1", "50e1ac9_1"}
    assert "syntax_error_rate" in rep and "format_failure_rate" in rep
    # loop config captured for provenance
    assert on_disk["loop_config"]["max_turns"] == LoopConfig().max_turns


def test_run_stage_filename_convention(tmp_path: Path) -> None:
    res = fn.run_stage(
        label="Qwen 3.5/0.8b",
        stage=fn.Stage.LITE,
        subset=_two_task_subset(),
        model_factory=_scripted_factory,
        sandbox_factory=_fake_sandbox_factory,
        run_index=2,
        results_dir=tmp_path,
    )
    # label slugified, stage + run index in the filename
    assert res.results_path is not None
    assert Path(res.results_path).name == "Qwen-3.5-0.8b.lite.run2.json"


def test_run_with_reruns_two_runs_no_third_when_stable(tmp_path: Path) -> None:
    agg = fn.run_with_reruns(
        label="stable",
        stage=fn.Stage.SMOKE,
        subset=_two_task_subset(),
        model_factory=_scripted_factory,          # deterministic -> identical ASR each run
        sandbox_factory=_fake_sandbox_factory,
        results_dir=tmp_path,
    )
    assert len(agg.runs) == 2                      # LOCKED base = 2, no 3rd needed
    assert agg.asr_series == (1.0, 1.0)
    assert agg.max_abs_delta_pp == 0.0
    assert agg.triggered_third_run is False
    assert agg.mean_asr == 1.0
    # both runs persisted with run1/run2 filenames
    names = sorted(p.name for p in tmp_path.glob("*.json"))
    assert names == ["stable.smoke.run1.json", "stable.smoke.run2.json"]


def test_run_with_reruns_triggers_third_on_large_delta(tmp_path: Path) -> None:
    """A model whose ASR swings >5pp between runs must trigger a 3rd run + mean reporting."""

    # A factory whose success flips by run: we encode the run index in the FakeSandbox gold so that
    # run 1 succeeds (gold matches) and run 2 fails (gold mismatched), a 100pp swing -> 3rd run.
    state = {"call": 0}

    def flaky_sandbox_factory(task_id: str) -> FakeSandbox:
        # Each task opens a sandbox; count sandbox opens to know which run we're in.
        # 2 tasks per run: opens 0,1 -> run1 ; 2,3 -> run2 ; 4,5 -> run3.
        idx = state["call"]
        state["call"] += 1
        run_no = idx // 2
        gold, instr = _GOLDS[task_id]
        # break the gold on run 2 (idx 2,3) so ASR drops to 0 that run.
        bad = run_no == 1
        return FakeSandbox(
            gold_answer=(object() if bad else gold), instruction=instr, supervisor_email="b@x.com"
        )

    agg = fn.run_with_reruns(
        label="flaky",
        stage=fn.Stage.SCORED,
        subset=_two_task_subset(),
        model_factory=_scripted_factory,
        sandbox_factory=flaky_sandbox_factory,
        results_dir=tmp_path,
    )
    assert agg.triggered_third_run is True
    assert len(agg.runs) == 3
    assert agg.asr_series[0] == 1.0 and agg.asr_series[1] == 0.0
    assert agg.max_abs_delta_pp == 100.0
    # mean over the 3 runs (run3 succeeds again -> 1.0): (1+0+1)/3
    assert abs(agg.mean_asr - (2 / 3)) < 1e-9
    assert {p.name for p in tmp_path.glob("*.json")} == {
        "flaky.scored.run1.json",
        "flaky.scored.run2.json",
        "flaky.scored.run3.json",
    }


def test_run_with_reruns_aggregate_is_json_serialisable(tmp_path: Path) -> None:
    agg = fn.run_with_reruns(
        label="ser",
        stage=fn.Stage.SMOKE,
        subset=_two_task_subset(),
        model_factory=_scripted_factory,
        sandbox_factory=_fake_sandbox_factory,
        results_dir=tmp_path,
    )
    json.dumps(agg.as_dict())  # must not raise


# ---- early-stop conditions -------------------------------------------------------------------
def _report_with(
    *,
    succeeded: int,
    total: int,
    outcome_for_failures: TaskOutcome = TaskOutcome.FAILURE,
    failure_has_mechanics: bool = False,
) -> BenchmarkReport:
    """Hand-build a BenchmarkReport with a chosen ASR + failure character for early-stop tests."""
    results: list[TaskRunResult] = []
    for i in range(total):
        success = i < succeeded
        outcome = TaskOutcome.SUCCESS if success else outcome_for_failures
        diag = TaskDiagnostics(
            task_id=f"task_{i}",
            outcome=outcome,
            success=success,
            collateral_damage=False,
            turns_used=3,
            blocks_run=3,
            format_failures=(1 if (not success and failure_has_mechanics) else 0),
            syntax_errors=0,
            runtime_errors=(1 if (not success and failure_has_mechanics) else 0),
            cap_exceeded=(outcome == TaskOutcome.CAP_EXCEEDED),
            total_api_calls=5,
            api_docs_uses=0,
            observation_truncations=0,
            total_output_tokens=100,
        )
        results.append(
            TaskRunResult(
                task_id=f"task_{i}",
                success=success,
                outcome=outcome,
                collateral_damage=False,
                diagnostics=diag,
            )
        )
    from localbench.scoring.agentic_exec.benchmark import aggregate

    return aggregate(results)


def test_early_stop_near_zero() -> None:
    rep = _report_with(succeeded=1, total=96)  # ~1% ASR
    sig = fn.evaluate_early_stop(rep)
    assert sig.should_stop is True
    assert any("near_zero" in r for r in sig.reasons)


def test_early_stop_near_perfect() -> None:
    rep = _report_with(succeeded=95, total=96)  # ~99% ASR
    sig = fn.evaluate_early_stop(rep)
    assert sig.should_stop is True
    assert any("near_perfect" in r for r in sig.reasons)


def test_early_stop_harness_dominated_cap() -> None:
    # half succeed, the rest all cap_exceeded -> harness mechanics dominate the failures.
    rep = _report_with(succeeded=48, total=96, outcome_for_failures=TaskOutcome.CAP_EXCEEDED)
    sig = fn.evaluate_early_stop(rep)
    assert sig.should_stop is True
    assert any("harness_dominated" in r for r in sig.reasons)
    assert sig.harness_failure_share == 1.0


def test_early_stop_failure_with_mechanics_is_not_harness_dominated() -> None:
    # A FAILURE outcome means the model finalized and AppWorld's evaluate() returned False — a
    # GENUINE on-merits failure — even when the trajectory carried recoverable format/runtime
    # errors. The metric keys on TERMINAL OUTCOMES, so these do NOT trigger harness_dominated.
    # (Regression guard for the over-flagging fix: wide-smoke Qwen had 5 genuine failures + 1
    # success and was wrongly reported share 1.00; the correct share is 0.00.)
    rep = _report_with(
        succeeded=48, total=96, outcome_for_failures=TaskOutcome.FAILURE, failure_has_mechanics=True
    )
    sig = fn.evaluate_early_stop(rep)
    assert sig.should_stop is False
    assert sig.harness_failure_share == 0.0
    assert not any("harness_dominated" in r for r in sig.reasons)


def test_early_stop_healthy_midrange_does_not_stop() -> None:
    # ~50% ASR with clean failures (no harness mechanics) -> a usable, discriminating column.
    rep = _report_with(
        succeeded=48, total=96, outcome_for_failures=TaskOutcome.FAILURE, failure_has_mechanics=False
    )
    sig = fn.evaluate_early_stop(rep)
    assert sig.should_stop is False
    assert sig.reasons == ()


def test_early_stop_within_noise_cross_model() -> None:
    rep = _report_with(succeeded=48, total=96, failure_has_mechanics=False)
    # three models all within ~2pp of each other -> ranks not meaningful.
    sig = fn.evaluate_early_stop(rep, cross_model_asr=[0.50, 0.51, 0.52])
    assert sig.should_stop is True
    assert any("within_noise" in r for r in sig.reasons)


def test_early_stop_signal_json_serialisable() -> None:
    rep = _report_with(succeeded=10, total=96)
    json.dumps(fn.evaluate_early_stop(rep).as_dict())


def test_chat_client_factory_builds_clients() -> None:
    factory = fn.chat_client_factory("http://127.0.0.1:8000", "qwen-x", api_key="k")
    client = factory("any_task")
    assert isinstance(client, ChatCompletionsClient)
    assert client.config.model == "qwen-x"
    assert client.config.base_url == "http://127.0.0.1:8000"
