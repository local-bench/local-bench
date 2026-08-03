from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import localbench.check.live_full as live_full
import localbench.check.live_runner as live_runner
import localbench.check.run as check_run

from localbench.check.execution import DEFAULT_LCE_SERVER_BIN, LceLaunchConfig, lce_server_argv
from localbench._types import JsonObject
from localbench.check.live_full import FullLiveProgress, FullLiveRequest, run_full_live_check
from localbench.check.live_runner import LiveExecutionResult, LiveRunOptions
from localbench.check.live_runner import LiveItem, run_live_items
from localbench.check.live_reference import attach_reference_rows, validate_execution_pair
from localbench.check.run import CheckRequest, run_check
from localbench.check.run_progress import ItemJournal
from localbench.check.live_server import InfrastructureFailure, LiveRunnerConfig, ServerController
from localbench.check.live_sources import PINNED_SMOKE_ITEMS, load_smoke_items
from localbench.check.stateful_live import run_stateful_item
from localbench.check.types import CheckError, ReferenceEdition
from localbench.checkset.input_runs import read_json
from live_stub_server import CrashedController as _CrashedController
from live_stub_server import FakeController as _FakeController
from live_stub_server import StubState as _StubState
from live_stub_server import stub_server as _stub_server


def test_lce_argv_pins_binary_context_batch_and_all_normative_flags(tmp_path: Path) -> None:
    config = LceLaunchConfig(
        model_file=tmp_path / "model.gguf",
        run_dir=tmp_path,
        host="127.0.0.1",
        port=8088,
        api_key="secret",
    )

    argv = lce_server_argv(config)

    assert DEFAULT_LCE_SERVER_BIN == Path(r"C:\Users\Michael\llamacpp\b10076\llama-server.exe")
    assert argv[0] == str(DEFAULT_LCE_SERVER_BIN)
    for pair in (
        ("--ctx-size", "32768"),
        ("--batch-size", "2048"),
        ("--ubatch-size", "512"),
        ("--parallel", "1"),
    ):
        index = argv.index(pair[0])
        assert argv[index : index + 2] == list(pair)
    for pair in (("-ctk", "f16"), ("-ctv", "f16"), ("--fit", "off"), ("--reasoning-format", "none"), ("-lv", "4")):
        index = argv.index(pair[0])
        assert argv[index : index + 2] == list(pair)


def test_live_runner_streams_forced_budget_and_restarts_determinism_canary(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.gguf"
    binary = tmp_path / "llama-server.exe"
    _ = model.write_bytes(b"model")
    _ = binary.write_bytes(b"server")
    state = _StubState(model)
    stopped: list[int] = []
    launched_argv: list[list[str]] = []

    def factory(argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        launched_argv.append(argv)
        state.health_failures_remaining = 1
        return _FakeController(8100 + len(launched_argv), stopped)

    item = LiveItem(
        item_id="gate-determinism-short",
        module="sanity-gates",
        source={
            "category": "determinism",
            "expected": {"answer": "101"},
            "gate_kind": "validity",
            "item_id": "gate-determinism-short",
            "prompt": "Return the next prime after 100.",
        },
    )
    with _stub_server(state) as (host, port):
        result = run_live_items(
            LiveRunnerConfig(
                model_file=model,
                run_dir=tmp_path / "run",
                server_bin=binary,
                host=host,
                port=port,
                startup_timeout_seconds=2,
                poll_interval_seconds=0.01,
            ),
            (item,),
            LiveRunOptions(server_factory=factory),
        )

    assert len(launched_argv) == 2
    assert stopped == [8101, 8102]
    assert state.health_calls >= 4
    assert state.props_calls == 2
    row = result.items[0]
    candidate = row["candidate"]
    repeated = row["candidate_repeat"]
    assert isinstance(candidate, dict) and isinstance(repeated, dict)
    assert candidate["server_start_id"] != repeated["server_start_id"]
    assert candidate["protocol_flag"] is None
    assert candidate["token_ids"] == [31, 32, 33]
    completions = [request for request in state.requests if request.get("stream") is True]
    assert len(completions) == 4
    requested_budgets = [request.get("max_tokens") for request in completions]
    assert all(isinstance(value, int) for value in requested_budgets)
    assert set(cast(list[int], requested_budgets)) == {4096, 512}
    assert all(request["temperature"] == 0 and request["seed"] == 1234 for request in completions)
    tokenized = [
        content
        for request in state.requests
        for content in [request.get("content")]
        if isinstance(content, str) and content.startswith("<think>")
    ]
    assert tokenized == ["<think>stub reasoning101", "<think>stub reasoning101"]
    assert result.execution["effective_server_config"] == {
        "backend": "CUDA",
        "chat_template": "{{ messages }}",
        "driver_version": "stub-driver",
        "model_path": str(model.resolve()),
        "total_slots": 1,
    }
    assert result.execution["prompt_template_sha256"] == hashlib.sha256(b"{{ messages }}").hexdigest()
    first_completion = state.request_paths.index("/v1/completions")
    assert state.request_paths[:first_completion] == ["/apply-template", "/tokenize"]


def test_fit_preflight_selects_ten_longest_with_deterministic_ties_and_all_needles() -> None:
    items = tuple(
        LiveItem(f"item-{index:02d}", "instruction", {"prompt": "x" * (index + 1)})
        for index in range(15)
    ) + tuple(
        LiveItem(
            item_id,
            "sanity-gates",
            {"category": "long-context-needle", "prompt": "short"},
        )
        for item_id in (
            "gate-long-context-08192",
            "gate-long-context-16384",
            "gate-long-context-24576",
        )
    )

    selected = live_runner.select_fit_preflight_items(items)
    selected_ids = [item.item_id for item in selected]

    assert selected_ids[:10] == [f"item-{index:02d}" for index in range(14, 4, -1)]
    assert selected_ids[10:] == [
        "gate-long-context-08192",
        "gate-long-context-16384",
        "gate-long-context-24576",
    ]


def test_fit_preflight_real_http_covers_full_selected_set_before_generation(tmp_path: Path) -> None:
    # Given twelve differently sized non-needle items and three short needle gates.
    model = tmp_path / "model.gguf"
    binary = tmp_path / "llama-server.exe"
    _ = model.write_bytes(b"model")
    _ = binary.write_bytes(b"server")
    state = _StubState(model)
    stopped: list[int] = []
    non_needles = tuple(
        LiveItem(
            f"item-{index:02d}",
            "instruction",
            {"prompt": f"NON_NEEDLE_{index:02d}_" + "x" * (100 + index)},
        )
        for index in range(12)
    )
    needles = tuple(
        LiveItem(
            item_id,
            "sanity-gates",
            {"category": "long-context-needle", "prompt": marker},
        )
        for item_id, marker in (
            ("gate-long-context-08192", "NEEDLE_08192"),
            ("gate-long-context-16384", "NEEDLE_16384"),
            ("gate-long-context-24576", "NEEDLE_24576"),
        )
    )

    def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        return _FakeController(8110, stopped)

    # When the live runner performs a successful run through the threaded HTTP stub.
    with _stub_server(state) as (host, port):
        _ = run_live_items(
            LiveRunnerConfig(
                model_file=model,
                run_dir=tmp_path / "run",
                server_bin=binary,
                host=host,
                port=port,
                startup_timeout_seconds=2,
                poll_interval_seconds=0.01,
            ),
            (*non_needles, *needles),
            LiveRunOptions(server_factory=factory),
        )

    # Then each independently expected candidate is rendered and tokenized before generation.
    expected_markers = tuple(f"NON_NEEDLE_{index:02d}_" for index in range(11, 1, -1)) + (
        "NEEDLE_08192",
        "NEEDLE_16384",
        "NEEDLE_24576",
    )
    events = tuple(zip(state.request_paths, state.requests, strict=True))
    first_completion = next(index for index, (path, _) in enumerate(events) if path == "/v1/completions")
    preflight_events = events[:first_completion]
    assert sum(path == "/tokenize" for path, _ in preflight_events) == len(expected_markers)
    for marker in expected_markers:
        apply_indices = tuple(
            index
            for index, (path, body) in enumerate(preflight_events)
            if path == "/apply-template" and marker in json.dumps(body, sort_keys=True)
        )
        tokenize_indices = tuple(
            index
            for index, (path, body) in enumerate(preflight_events)
            if path == "/tokenize" and marker in json.dumps(body, sort_keys=True)
        )
        assert apply_indices
        assert len(tokenize_indices) == 1
        assert min(apply_indices) < tokenize_indices[0] < first_completion
    assert stopped == [8110]


def test_check_smoke_preflight_failure_writes_construction_defect_before_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = b"general.architecture"
    value = b"qwen3"
    model = tmp_path / "fixture-Q5_K_M.gguf"
    _ = model.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(value))
        + value
    )
    binary = tmp_path / "llama-server.exe"
    _ = binary.write_bytes(b"server")
    state = _StubState(model)
    state.oversized_prompt_marker = "MORETON-24576"
    state.oversized_prompt_tokens = 28001
    stopped: list[int] = []

    def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        return _FakeController(9099, stopped)

    run_dir = tmp_path / "run"
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "checkset" / "check-set-v1.manifest.json"

    with _stub_server(state) as (host, port):

        def run_real_live_items(
            config: LiveRunnerConfig,
            items: Sequence[LiveItem],
            options: LiveRunOptions,
        ) -> LiveExecutionResult:
            return live_runner.run_live_items(
                LiveRunnerConfig(
                    model_file=config.model_file,
                    run_dir=config.run_dir,
                    server_bin=binary,
                    host=host,
                    port=port,
                    startup_timeout_seconds=2,
                    poll_interval_seconds=0.01,
                    allow_untrusted_code=config.allow_untrusted_code,
                ),
                items,
                replace(options, server_factory=factory),
            )

        monkeypatch.setattr(check_run, "run_live_items", run_real_live_items)
        with pytest.raises(InfrastructureFailure) as caught:
            _ = run_check(
                CheckRequest(
                    artifact=model,
                    manifest=manifest,
                    parent=None,
                    dry_run=False,
                    out=run_dir,
                    resume=None,
                    smoke=True,
                )
            )

    expected_message = (
        "prompt fit preflight failed for gate-long-context-24576: "
        "28001 + 4096 + 512 + 256 = 32865 > 32768"
    )
    assert caught.value.failure_class == "construction-defect"
    assert caught.value.kind == "prompt-fit"
    assert caught.value.detail == expected_message
    assert read_json(run_dir / "infrastructure-failure.json") == {
        "failure_class": "construction-defect",
        "kind": "prompt-fit",
        "message": expected_message,
    }
    assert "/v1/completions" not in state.request_paths
    assert stopped == [9099]


def test_check_smoke_records_streaming_status_failure_from_live_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a live llama-server response that rejects a request exceeding its context size.
    key = b"general.architecture"
    value = b"qwen3"
    model = tmp_path / "fixture-Q5_K_M.gguf"
    _ = model.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(value))
        + value
    )
    binary = tmp_path / "llama-server.exe"
    _ = binary.write_bytes(b"server")
    state = _StubState(model)
    response_body = (
        '{"error":{"code":400,"message":"request (34629 tokens) exceeds the available context size '
        '(32768 tokens), try increasing it","type":"exceed_context_size_error",'
        '"n_prompt_tokens":34629,"n_ctx":32768}}'
    )
    state.completion_error = (400, response_body)
    stopped: list[int] = []

    def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        return _FakeController(9100, stopped)

    run_dir = tmp_path / "run"
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "checkset" / "check-set-v1.manifest.json"

    with _stub_server(state) as (host, port):

        def run_real_live_items(
            config: LiveRunnerConfig,
            items: Sequence[LiveItem],
            options: LiveRunOptions,
        ) -> LiveExecutionResult:
            return live_runner.run_live_items(
                LiveRunnerConfig(
                    model_file=config.model_file,
                    run_dir=config.run_dir,
                    server_bin=binary,
                    host=host,
                    port=port,
                    startup_timeout_seconds=2,
                    poll_interval_seconds=0.01,
                    allow_untrusted_code=config.allow_untrusted_code,
                ),
                items,
                replace(options, server_factory=factory),
            )

        monkeypatch.setattr(check_run, "run_live_items", run_real_live_items)

        # When the smoke check traverses the real live runner and streaming HTTP client.
        with pytest.raises(InfrastructureFailure) as caught:
            _ = run_check(
                CheckRequest(
                    artifact=model,
                    manifest=manifest,
                    parent=None,
                    dry_run=False,
                    out=run_dir,
                    resume=None,
                    smoke=True,
                )
            )

    # Then the existing failure policy classifies and records the exact server response.
    expected_message = f"live completion failed for ifbench-066: HTTP 400: {response_body}"
    assert caught.value.failure_class == "construction-defect"
    assert caught.value.kind == "execution"
    assert caught.value.detail == expected_message
    assert not isinstance(caught.value.__cause__, TypeError)
    assert read_json(run_dir / "infrastructure-failure.json") == {
        "failure_class": "construction-defect",
        "kind": "execution",
        "message": expected_message,
    }
    assert stopped == [9100]


def test_live_runner_classifies_health_timeout_as_infrastructure_and_stops_only_owned_pid(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.gguf"
    binary = tmp_path / "llama-server.exe"
    _ = model.write_bytes(b"model")
    _ = binary.write_bytes(b"server")
    state = _StubState(model)
    state.health_failures_remaining = 10_000
    stopped: list[int] = []

    def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        return _FakeController(9123, stopped)

    with _stub_server(state) as (host, port), pytest.raises(InfrastructureFailure) as caught:
        _ = run_live_items(
            LiveRunnerConfig(
                model_file=model,
                run_dir=tmp_path / "run",
                server_bin=binary,
                host=host,
                port=port,
                startup_timeout_seconds=0.05,
                poll_interval_seconds=0.01,
            ),
            (),
            LiveRunOptions(server_factory=factory),
        )

    assert caught.value.kind == "startup-timeout"
    assert caught.value.failure_class == "infrastructure"
    assert stopped == [9123]


def test_live_runner_classifies_child_crash_and_still_stops_that_child(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    binary = tmp_path / "llama-server.exe"
    _ = model.write_bytes(b"model")
    _ = binary.write_bytes(b"server")
    stopped: list[int] = []

    def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
        return _CrashedController(9456, stopped)

    with pytest.raises(InfrastructureFailure) as caught:
        _ = run_live_items(
            LiveRunnerConfig(
                model_file=model,
                run_dir=tmp_path / "run",
                server_bin=binary,
                port=65431,
                startup_timeout_seconds=0.05,
                poll_interval_seconds=0.01,
            ),
            (),
            LiveRunOptions(server_factory=factory),
        )

    assert caught.value.kind == "server-crash"
    assert stopped == [9456]


def test_full_live_runner_requires_explicit_coding_sandbox_consent(tmp_path: Path) -> None:
    item = LiveItem("bcbh-002", "coding", {"instruct_prompt": "write code"})

    with pytest.raises(CheckError, match="allow-untrusted-code"):
        _ = run_live_items(
            LiveRunnerConfig(model_file=tmp_path / "model.gguf", run_dir=tmp_path / "run"),
            (item,),
        )


def test_smoke_selection_is_pinned_few_items_plus_all_sanity_gates() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "checkset" / "check-set-v1.manifest.json"

    items = load_smoke_items(repo_root, manifest)

    assert [item.item_id for item in items[: len(PINNED_SMOKE_ITEMS)]] == list(PINNED_SMOKE_ITEMS)
    gates = [item for item in items if item.module == "sanity-gates"]
    assert len(items) == len(PINNED_SMOKE_ITEMS) + 18
    assert len(gates) == 18


def test_stateful_live_runner_uses_one_call_per_turn_and_reveals_inspect_output_after_call() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = read_json(repo_root / "checkset" / "check-set-v1.manifest.json")
    stateful = manifest["stateful"]
    assert isinstance(stateful, dict)
    instances = stateful["instances"]
    assert isinstance(instances, list)
    source = cast(
        JsonObject,
        next(
        instance
        for instance in instances
        if isinstance(instance, dict) and instance.get("template") == "config migration"
        ),
    )
    accepted = source["accepted_equivalent_trajectories"]
    inspect_output = source["inspect_output"]
    assert isinstance(accepted, list) and isinstance(accepted[0], list)
    assert isinstance(inspect_output, dict)
    trajectory = accepted[0]
    prompts: list[str] = []
    calls = iter(trajectory)

    def generate(turn_source: JsonObject) -> JsonObject:
        prompt = turn_source["prompt"]
        assert isinstance(prompt, str)
        prompts.append(prompt)
        if turn_source.get("stateful_final") is True:
            return {"finish_reason": "stop", "parsed_tool_calls": [], "text": "DONE", "token_ids": [9]}
        call = next(calls)
        assert isinstance(call, dict)
        return {
            "finish_reason": "stop",
            "parsed_tool_calls": [call],
            "protocol_flag": None,
            "text": json.dumps({"calls": [call]}),
            "token_ids": [1],
            "usage": {"completion_tokens": 1, "prompt_tokens": 1, "total_tokens": 2},
        }

    generation = run_stateful_item(source, generate)

    hidden_value = next(iter(inspect_output.values()))
    assert isinstance(hidden_value, str)
    assert hidden_value not in prompts[0]
    assert hidden_value in prompts[1]
    assert generation["parsed_tool_calls"] == trajectory
    assert generation["stateful_turns"] == len(trajectory) + 1


def test_live_reference_pairing_copies_independent_restart_canary_evidence() -> None:
    candidate: list[JsonObject] = [
        {"item_id": "gate-determinism-short", "module": "sanity-gates", "candidate": {"text": "101"}}
    ]
    reference: list[JsonObject] = [
        {
            "item_id": "gate-determinism-short",
            "module": "sanity-gates",
            "candidate": {"server_start_id": "ref-a", "text": "101"},
            "candidate_repeat": {"server_start_id": "ref-b", "text": "101"},
        }
    ]

    paired = attach_reference_rows(candidate, reference)

    assert paired[0]["reference"] == {"server_start_id": "ref-a", "text": "101"}
    assert paired[0]["reference_repeat"] == {"server_start_id": "ref-b", "text": "101"}
    assert paired[0]["reference"] is not reference[0]["candidate"]


def test_live_reference_rejects_execution_config_drift() -> None:
    candidate: JsonObject = {
        "backend": "CUDA",
        "batch_size": 1,
        "binaries": {"llama-server.exe": "a" * 64},
        "build": "b10076",
        "commit": "305ba51",
        "context_tokens": 32768,
        "cuda_version": "13.3",
        "driver": "stub-driver",
        "edition": "LCE-1",
        "flags": ["-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4"],
        "prompt_rendering": "cli-owned",
        "repo_defaults_disabled": True,
        "server_defaults_disabled": True,
    }
    reference = dict(candidate)
    reference["batch_size"] = 2

    with pytest.raises(CheckError, match="batch_size"):
        validate_execution_pair(candidate, reference)


def test_live_reference_records_candidate_template_drift_for_gate_scoring() -> None:
    fixed: JsonObject = {
        "backend": "CUDA",
        "batch_size": 1,
        "binaries": {"llama-server.exe": "a" * 64},
        "build": "b10076",
        "commit": "305ba51",
        "context_tokens": 32768,
        "cuda_version": "13.3",
        "driver": "stub-driver",
        "edition": "LCE-1",
        "flags": ["-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4"],
        "prompt_rendering": "cli-owned",
        "repo_defaults_disabled": True,
        "server_defaults_disabled": True,
    }
    candidate: JsonObject = {
        **fixed,
        "effective_server_config": {"chat_template": "wrong", "model_path": "candidate.gguf"},
        "prompt_template_sha256": "c" * 64,
    }
    reference: JsonObject = {
        **fixed,
        "effective_server_config": {"chat_template": "pinned", "model_path": "reference.gguf"},
        "prompt_template_sha256": "d" * 64,
    }

    validate_execution_pair(candidate, reference)


def test_full_reference_artifact_runs_independent_reference_and_candidate_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    execution: JsonObject = {
        "backend": "CUDA",
        "batch_size": 1,
        "binaries": {"llama-server.exe": "a" * 64},
        "build": "b10076",
        "commit": "305ba51",
        "context_tokens": 32768,
        "cuda_version": "13.3",
        "driver": "stub-driver",
        "edition": "LCE-1",
        "effective_server_config": {"chat_template": "stub", "model_path": "ignored"},
        "flags": ["-ctk", "f16", "-ctv", "f16", "--fit", "off", "-lv", "4"],
        "prompt_rendering": "cli-owned",
        "prompt_template_sha256": "b" * 64,
        "repo_defaults_disabled": True,
        "server_defaults_disabled": True,
    }

    def fake_run_live_items(
        _config: LiveRunnerConfig,
        _items: Sequence[LiveItem],
        _options: LiveRunOptions,
    ) -> LiveExecutionResult:
        calls.append(len(calls) + 1)
        return LiveExecutionResult(
            [
                {
                    "candidate": {"server_start_id": f"pass-{calls[-1]}", "text": str(calls[-1])},
                    "item_id": "ifbench-066",
                    "module": "instruction",
                }
            ],
            dict(execution),
        )

    monkeypatch.setattr(live_full, "run_live_items", fake_run_live_items)
    reference = ReferenceEdition(
        edition_id="reference-v1",
        family="qwen3",
        artifact_sha256="c" * 64,
        tokenizer_sha256="d" * 64,
        template_sha256="b" * 64,
        class_label="Q8 operational proxy",
        created_utc="2026-08-03T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )

    result = run_full_live_check(
        LiveRunnerConfig(
            model_file=tmp_path / "reference.gguf",
            run_dir=tmp_path / "run",
            allow_untrusted_code=True,
        ),
        (LiveItem("ifbench-066", "instruction", {"prompt": "stub"}),),
        FullLiveRequest(
            candidate_sha256="c" * 64,
            reference=reference,
            reference_run=None,
            manifest_edition="check-set-v1",
            manifest_sha256="f" * 64,
            progress=FullLiveProgress(
                journal=ItemJournal(tmp_path / "run" / "items.jsonl"),
                rows=(),
                execution_path=tmp_path / "run" / "execution.json",
                reference_execution=None,
                candidate_execution=None,
            ),
        ),
    )

    assert calls == [1, 2]
    assert result.items[0]["candidate"] == {"server_start_id": "pass-2", "text": "2"}
    assert result.items[0]["reference"] == {"server_start_id": "pass-1", "text": "1"}
    assert result.execution["reference_source"] == "independent-live-rerun"
