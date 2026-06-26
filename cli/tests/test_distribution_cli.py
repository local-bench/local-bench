"""Tests for public distribution CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.cli import main


def test_fetch_suite_command_requires_accept_suite_terms(
    tmp_path: Path,
    capsys,
) -> None:
    # Given: a local suite source.
    source = _write_suite(tmp_path / "source")

    # When: fetching without the acceptance flag.
    code = main(["fetch-suite", "--source", str(source), "--cache-dir", str(tmp_path / "cache")])

    # Then: the CLI fails closed.
    captured = capsys.readouterr()
    assert code == 2
    assert "--accept-suite-terms" in captured.out


def test_fetch_suite_and_suite_inspect_commands_use_local_source(
    tmp_path: Path,
    capsys,
) -> None:
    # Given: a local public-suite source and empty cache.
    source = _write_suite(tmp_path / "source")
    cache_dir = tmp_path / "cache"

    # When: fetching and then inspecting from the cache.
    fetch_code = main(
        [
            "fetch-suite",
            "--accept-suite-terms",
            "--source",
            str(source),
            "--cache-dir",
            str(cache_dir),
        ],
    )
    fetch_out = capsys.readouterr().out
    inspect_code = main(["suite", "inspect", "--cache-dir", str(cache_dir)])
    inspect_out = capsys.readouterr().out

    # Then: both commands expose the verified suite identity.
    assert fetch_code == 0
    assert "suite_id  core-text-v1" in fetch_out
    assert "cached    " in fetch_out
    assert inspect_code == 0
    assert "suite_id  core-text-v1" in inspect_out
    assert "benches   ifbench, mmlu_pro" in inspect_out


def test_doctor_command_reports_cache_and_suite_status(tmp_path: Path, capsys) -> None:
    # Given / When: doctor runs against an empty isolated cache.
    code = main(["doctor", "--cache-dir", str(tmp_path / "cache")])

    # Then: it reports local diagnostics without failing the process.
    output = capsys.readouterr().out
    assert code == 0
    assert "cache     " in output
    assert "python    " in output
    assert "core-text-v1" in output


def test_tc_json_help_uses_tool_calling_label(capsys) -> None:
    # Given / When: the top-level CLI help is rendered.
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    # Then: the tc-json command is described as a Tool-calling axis.
    output = capsys.readouterr().out
    tc_json_line = next(line for line in output.splitlines() if line.strip().startswith("tc-json"))
    assert exit_info.value.code == 0
    assert "Tool-calling" in tc_json_line
    assert "gate" not in tc_json_line.lower()


def test_run_dry_defaults_core_text_suite_to_standard_tier(tmp_path: Path, capsys) -> None:
    # Given: a public-suite source with standard itemsets only.
    source = _write_suite(tmp_path / "source")

    # When: dry-running without an explicit tier.
    code = main(
        [
            "run",
            "--suite-dir",
            str(source),
            "--endpoint",
            "http://127.0.0.1:9/v1",
            "--model",
            "smoke-model",
            "--dry-run",
        ],
    )

    # Then: the public on-ramp exercises the headline tier instead of an empty quick run.
    output = capsys.readouterr().out
    assert code == 0
    assert "mmlu_pro" in output
    assert "ifbench" in output
    assert "items     2" in output
    assert "tier is not listed" not in output


def _write_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "mmlu_pro.jsonl").write_text(
        '{"id":"1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    (path / "ifbench.jsonl").write_text(
        '{"key":"if-1","prompt":"Say ok","instruction_id_list":[],"kwargs":[]}\n',
        encoding="utf-8",
    )
    mmlu_hash = _sha256(path / "mmlu_pro.jsonl")
    ifbench_hash = _sha256(path / "ifbench.jsonl")
    (path / "suite.json").write_text(
        json.dumps(
            {
                "id": "core-text-v1",
                "version": "core-text-v1",
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {"standard": {"file": "mmlu_pro.jsonl", "item_count": 1, "sha256": mmlu_hash}},
                        "template_text": "{question}\n{options}",
                    },
                    "ifbench": {
                        "chance_correction_baseline": 0.0,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {"standard": {"file": "ifbench.jsonl", "item_count": 1, "sha256": ifbench_hash}},
                        "template_text": "{prompt}",
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps(
            {
                "files": {
                    "mmlu_pro.jsonl": {"item_count": 1, "sha256": mmlu_hash},
                    "ifbench.jsonl": {"item_count": 1, "sha256": ifbench_hash},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
