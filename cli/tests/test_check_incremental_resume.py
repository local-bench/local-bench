from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

import localbench.check.live_runner as live_runner
import localbench.check.run as check_run
from live_stub_server import FakeController, StubState, stub_server
from localbench._types import JsonObject
from localbench.check.live_runner import LiveItem, LiveRunOptions, run_live_items
from localbench.check.live_server import InfrastructureFailure, LiveRunnerConfig, ServerController
from localbench.check.reference import create_reference_bundle, store_reference_bundle
from localbench.check.run import CheckRequest, run_check
from localbench.check.run_progress import ItemJournal
from localbench.check.run_support import read_items
from localbench.check.types import ReferenceEdition
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file, write_json_file
from localbench.submissions.keys import write_private_key


def _fixture_gguf(path: Path) -> Path:
    key = b"general.architecture"
    value = b"qwen3"
    _ = path.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(value))
        + value
    )
    return path


def test_live_reference_resume_preserves_completed_partial_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a signed two-item reference run whose server fails during item two.
    artifact = _fixture_gguf(tmp_path / "reference-Q5_K_M.gguf")
    binary = tmp_path / "llama-server.exe"
    _ = binary.write_bytes(b"server")
    state = StubState(artifact)
    state.completion_error = (503, "stub interruption")
    state.completion_error_after = 2
    stopped: list[int] = []
    manifest = Path(__file__).resolve().parents[2] / "checkset" / "check-set-v1.manifest.json"
    run_dir = tmp_path / "run"
    signing_key = tmp_path / "reference-key.pem"
    public_key = write_private_key(signing_key, seed=b"p" * 32)
    edition = ReferenceEdition(
        edition_id="qwen3-reference-v1",
        family="qwen3",
        artifact_sha256=sha256_file(artifact),
        tokenizer_sha256="a" * 64,
        template_sha256=hashlib.sha256(b"{{ messages }}").hexdigest(),
        class_label="Q5_K_M operational proxy",
        created_utc="2026-08-04T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )
    bundle = store_reference_bundle(
        tmp_path / "reference-store",
        create_reference_bundle(edition, signing_key),
    )
    sources = (
        LiveItem("item-a", "instruction", {"prompt": "ITEM_A"}),
        LiveItem("item-b", "instruction", {"prompt": "ITEM_B"}),
    )

    with stub_server(state) as (host, port):
        launches = 0

        def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
            nonlocal launches
            launches += 1
            return FakeController(8100 + launches, stopped)

        def config_factory(
            *,
            model_file: Path,
            run_dir: Path,
            allow_untrusted_code: bool,
        ) -> LiveRunnerConfig:
            return LiveRunnerConfig(
                model_file=model_file,
                run_dir=run_dir,
                server_bin=binary,
                host=host,
                port=port,
                startup_timeout_seconds=2,
                poll_interval_seconds=0.01,
                allow_untrusted_code=allow_untrusted_code,
            )

        monkeypatch.setattr(check_run, "load_live_items", lambda *_args: sources)
        monkeypatch.setattr(check_run, "LiveRunnerConfig", config_factory)
        monkeypatch.setattr(live_runner, "owned_server_factory", factory)
        def analyze(
            run_path: Path,
            _manifest: JsonObject,
            *,
            artifact_class: str,
        ) -> tuple[JsonObject, JsonObject]:
            _ = artifact_class
            statistics: JsonObject = {"status": "test"}
            verdict: JsonObject = {"verdict": "inconclusive"}
            write_json_file(run_path / "statistics.json", statistics)
            write_json_file(run_path / "verdict.json", verdict)
            return statistics, verdict

        monkeypatch.setattr(check_run, "analyze_run", analyze)
        request = CheckRequest(
            artifact=artifact,
            manifest=manifest,
            parent=None,
            dry_run=False,
            out=run_dir,
            resume=None,
            reference_bundle=bundle,
            reference_public_key=public_key,
            allow_untrusted_code=True,
        )

        # When the first attempt aborts, its completed first item is already durable.
        with pytest.raises(InfrastructureFailure):
            _ = run_check(request)
        partial = read_items(run_dir / "items.jsonl")
        assert [row["item_id"] for row in partial] == ["item-a"]
        partial_reference = partial[0]["reference"]
        assert isinstance(partial_reference, dict)
        assert read_json(run_dir / "infrastructure-failure.json")["failure_class"] == "infrastructure"

        # When explicitly resumed, only unfinished work in each lifecycle is generated.
        state.completion_error = None
        _, record = run_check(
            CheckRequest(
                artifact=artifact,
                manifest=manifest,
                parent=None,
                dry_run=False,
                out=None,
                resume=run_dir,
                reference_bundle=bundle,
                reference_public_key=public_key,
                allow_untrusted_code=True,
            )
        )

    # Then the original immutable row becomes the final reference and the run completes.
    final_rows = read_items(run_dir / "items.jsonl")
    assert len(final_rows) == 2
    assert final_rows[0]["reference"] == partial_reference
    assert record["items"] == final_rows


def test_determinism_repeat_resume_merges_without_regenerating_candidates(tmp_path: Path) -> None:
    # Given two completed candidates and an interruption during the second repeat.
    model = tmp_path / "model.gguf"
    binary = tmp_path / "llama-server.exe"
    _ = model.write_bytes(b"model")
    _ = binary.write_bytes(b"server")
    state = StubState(model)
    state.completion_error = (503, "repeat interruption")
    state.completion_error_after = 6
    stopped: list[int] = []
    journal = ItemJournal(tmp_path / "run" / "items.jsonl")
    execution_path = tmp_path / "run" / "execution.json"
    items = tuple(
        LiveItem(
            f"determinism-{suffix}",
            "sanity-gates",
            {
                "category": "determinism",
                "expected": {"answer": "101"},
                "prompt": f"ITEM_{suffix}",
            },
        )
        for suffix in ("a", "b")
    )

    with stub_server(state) as (host, port):
        launches = 0

        def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
            nonlocal launches
            launches += 1
            return FakeController(8200 + launches, stopped)

        config = LiveRunnerConfig(
            model_file=model,
            run_dir=tmp_path / "run",
            server_bin=binary,
            host=host,
            port=port,
            startup_timeout_seconds=2,
            poll_interval_seconds=0.01,
        )
        options = LiveRunOptions(
            row_sink=journal.append,
            execution_sink=lambda value: write_json_file(execution_path, value),
            server_factory=factory,
        )

        # When repeat generation aborts, the first repeat and both candidates are durable.
        with pytest.raises(InfrastructureFailure):
            _ = run_live_items(config, items, options)
        partial = journal.rows()
        assert len(partial) == 2
        assert "candidate_repeat" in partial[0]
        assert "candidate_repeat" not in partial[1]
        immutable_candidates = [row["candidate"] for row in partial]
        immutable_repeat = partial[0]["candidate_repeat"]

        # When resumed, only the missing repeat is requested.
        requests_before_resume = state.completion_requests
        state.completion_error = None
        result = run_live_items(
            config,
            items,
            LiveRunOptions(
                completed_rows=tuple(partial),
                previous_execution=read_json(execution_path),
                row_sink=journal.append,
                execution_sink=lambda value: write_json_file(execution_path, value),
                server_factory=factory,
            ),
        )

    # Then candidates and the completed repeat stay immutable while the missing repeat lands.
    assert state.completion_requests - requests_before_resume == 2
    assert [row["candidate"] for row in result.items] == immutable_candidates
    assert result.items[0]["candidate_repeat"] == immutable_repeat
    assert all(isinstance(row.get("candidate_repeat"), dict) for row in result.items)
