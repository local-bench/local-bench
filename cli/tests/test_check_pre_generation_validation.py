from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

import localbench.check.live_runner as live_runner
import localbench.check.run as check_run
from live_stub_server import FakeController, StubState, stub_server
from localbench.check.live_runner import LiveItem
from localbench.check.live_server import LiveRunnerConfig, ServerController
from localbench.check.reference import create_reference_bundle, store_reference_bundle
from localbench.check.run import CheckRequest, run_check
from localbench.check.types import CheckError, ReferenceEdition
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file
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


def test_signed_template_mismatch_fails_before_any_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a signed edition whose template digest differs from the server-effective template.
    artifact = _fixture_gguf(tmp_path / "reference-Q5_K_M.gguf")
    binary = tmp_path / "llama-server.exe"
    _ = binary.write_bytes(b"server")
    state = StubState(artifact)
    state.chat_template = "{{ mismatched_messages }}"
    stopped: list[int] = []
    manifest = Path(__file__).resolve().parents[2] / "checkset" / "check-set-v1.manifest.json"
    run_dir = tmp_path / "run"
    signing_key = tmp_path / "reference-key.pem"
    public_key = write_private_key(signing_key, seed=b"v" * 32)
    edition = ReferenceEdition(
        edition_id="qwen3-reference-v1",
        family="qwen3",
        artifact_sha256=sha256_file(artifact),
        tokenizer_sha256="a" * 64,
        template_sha256=hashlib.sha256(b"{{ signed_messages }}").hexdigest(),
        class_label="Q5_K_M operational proxy",
        created_utc="2026-08-04T00:00:00Z",
        checkset_edition="check-set-v1",
        execution_edition="LCE-1",
    )
    bundle = store_reference_bundle(
        tmp_path / "reference-store",
        create_reference_bundle(edition, signing_key),
    )

    with stub_server(state) as (host, port):
        def factory(_argv: list[str], _cwd: Path, _log_path: Path) -> ServerController:
            return FakeController(8300, stopped)

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

        monkeypatch.setattr(
            check_run,
            "load_live_items",
            lambda *_args: (LiveItem("item-a", "instruction", {"prompt": "ITEM_A"}),),
        )
        monkeypatch.setattr(check_run, "LiveRunnerConfig", config_factory)
        monkeypatch.setattr(live_runner, "owned_server_factory", factory)

        # When the live reference run reaches pre-generation validation.
        with pytest.raises(CheckError, match="prompt template"):
            _ = run_check(
                CheckRequest(
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
            )

    # Then template application occurred, no completion was requested, and failure is typed.
    assert "/apply-template" in state.request_paths
    assert "/v1/completions" not in state.request_paths
    assert read_json(run_dir / "infrastructure-failure.json") == {
        "failure_class": "validation",
        "kind": "check-error",
        "message": "reference execution prompt template does not match the signed reference edition",
    }
    assert stopped == [8300]
