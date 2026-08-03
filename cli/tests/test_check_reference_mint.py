from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from localbench._types import JsonObject
from localbench.check.reference import load_reference_bundle
from localbench.check.smoke import write_smoke_record
from localbench.check_cli import main
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import sha256_file, write_json_file
from localbench.submissions.keys import write_private_key


def _completed_smoke(run_dir: Path, artifact: Path, template_sha256: str) -> None:
    run_dir.mkdir()
    write_json_file(run_dir / "plan.lock.json", {"plan": "reference-mint-test"})
    item: JsonObject = {
        "candidate": {"finish_reason": "stop", "text": "101", "token_ids": [101]},
        "generation_parameters": {},
        "item_id": "gate-determinism-short",
        "module": "sanity-gates",
        "source_item": {
            "category": "determinism",
            "expected": {"answer": "101"},
            "gate_kind": "validity",
        },
    }
    _ = write_smoke_record(
        run_dir,
        artifact={
            "model_family": "qwen3",
            "sha256": sha256_file(artifact),
            "tokenizer_sha256": "b" * 64,
        },
        execution={
            "edition": "LCE-1",
            "prompt_template_sha256": template_sha256,
            "runner": "llama-server-live",
        },
        items=[item],
        manifest_edition="check-set-v1",
        manifest_sha256="c" * 64,
        resumed=False,
    )


def _mint_args(artifact: Path, run_dir: Path, signing_key: Path, store: Path) -> tuple[str, ...]:
    return (
        "reference",
        "mint",
        "--edition-id",
        "qwen36-27b-reference-v1",
        "--family",
        "qwen3",
        "--class-label",
        "Q5_K_M operational proxy",
        "--created-utc",
        "2026-08-04T00:00:00Z",
        "--artifact",
        str(artifact),
        "--from-execution",
        str(run_dir),
        "--signing-key",
        str(signing_key),
        "--store",
        str(store),
    )


def test_reference_mint_uses_server_effective_template_digest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given a receipt-validated smoke record with a server-effective template digest.
    artifact = tmp_path / "reference.gguf"
    _ = artifact.write_bytes(b"reference-artifact")
    run_dir = tmp_path / "smoke"
    template_sha256 = "a" * 64
    _completed_smoke(run_dir, artifact, template_sha256)
    signing_key = tmp_path / "reference-key.pem"
    public_key = write_private_key(signing_key, seed=b"m" * 32)
    store = tmp_path / "store"

    # When the supported command mints the signed edition from that execution.
    exit_code = main(_mint_args(artifact, run_dir, signing_key, store))

    # Then the bundle uses runtime template identity and record tokenizer identity.
    bundle = store / "qwen36-27b-reference-v1.json"
    edition = load_reference_bundle(bundle, expected_public_key=public_key)
    assert exit_code == 0
    assert edition.template_sha256 == template_sha256
    assert edition.tokenizer_sha256 == "b" * 64
    assert "reference edition written" in capsys.readouterr().out


def test_reference_mint_rejects_doctored_execution_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given a completed record changed after its receipt was issued.
    artifact = tmp_path / "reference.gguf"
    _ = artifact.write_bytes(b"reference-artifact")
    run_dir = tmp_path / "smoke"
    _completed_smoke(run_dir, artifact, "a" * 64)
    record = read_json(run_dir / "check-record.json")
    execution = cast(JsonObject, record["execution"])
    execution["prompt_template_sha256"] = "d" * 64
    write_json_file(run_dir / "check-record.json", record)
    signing_key = tmp_path / "reference-key.pem"
    _ = write_private_key(signing_key, seed=b"m" * 32)
    store = tmp_path / "store"

    # When minting verifies the execution source.
    exit_code = main(_mint_args(artifact, run_dir, signing_key, store))

    # Then receipt validation fails closed and no bundle is stored.
    assert exit_code == 2
    assert "receipt digest mismatch: check-record.json" in capsys.readouterr().out
    assert not store.exists()
