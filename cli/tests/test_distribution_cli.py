"""Tests for public distribution CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.cli import main
from localbench.suite_resolver import DEFAULT_SUITE_ID, SuiteRef


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


def test_fetch_suite_command_accepts_remote_manifest_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    # Given: a remote manifest URL and a fake verified remote cache result.
    import localbench.cli as cli_mod

    cached = tmp_path / "cache" / "suites" / DEFAULT_SUITE_ID / ("a" * 64)

    def fake_fetch(config: cli_mod.RemoteSuiteFetch) -> SuiteRef:
        assert config.accept_suite_terms is True
        assert config.manifest_url == "https://local-bench.ai/api/suites/core-text-v1/manifest"
        assert config.cache_root == tmp_path / "cache"
        return SuiteRef(
            suite_id=DEFAULT_SUITE_ID,
            path=cached,
            suite_hash="a" * 64,
            source="remote-manifest",
            version=DEFAULT_SUITE_ID,
            license_manifest={},
        )

    monkeypatch.setattr(cli_mod, "fetch_suite_from_manifest_url", fake_fetch)

    # When: fetching through the command-line URL mode.
    code = main(
        [
            "fetch-suite",
            "--source-url",
            "https://local-bench.ai/api/suites/core-text-v1/manifest",
            "--accept-suite-terms",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )

    # Then: the CLI reports the remote-manifest suite identity.
    output = capsys.readouterr().out
    assert code == 0
    assert "suite_id  core-text-v1" in output
    assert "cached    " in output


def test_scorer_gates_preserves_agentic_token_when_an_http_bench_is_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an explicit bench list with a (forced) scorer-gated HTTP bench AND the agentic token
    # appworld_c, against the full v1 suite.
    import argparse

    import localbench.cli as cli_mod

    suite_v1 = Path(__file__).resolve().parents[2] / "suite" / "v1"
    # Force ifbench to read as scorer-unavailable (host-independent), leaving mmlu_pro/tc_json_v1 ok.
    monkeypatch.setattr(
        cli_mod,
        "scorer_unavailable_warning",
        lambda bench: "forced scorer gate" if bench.name == "ifbench" else None,
    )
    args = argparse.Namespace(
        suite="suite-v1",
        suite_dir=suite_v1,
        accept_suite_terms=True,
        suite_source=None,
        cache_dir=None,
        bench="mmlu_pro,ifbench,tc_json_v1,appworld_c",
        max_items=1,
    )

    # When: computing the scorer gates with a gated HTTP bench present.
    bench_choice, gates, _ = cli_mod._scorer_gates(args, "standard")

    # Then: the gated HTTP bench is recorded + dropped from the HTTP run, but the agentic token
    # SURVIVES so run_localbench's agentic branch still fires (the silent-drop fix).
    names = bench_choice.split(",")
    assert "ifbench" in gates
    assert "appworld_c" in names
    assert "mmlu_pro" in names
    assert "tc_json_v1" in names
    assert "ifbench" not in names


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
    assert "benches   ifbench, mmlu_pro, tc_json_v1" in inspect_out


def test_packaged_suite_fetch_and_suite_inspect_include_public_scored_axes(
    tmp_path: Path,
    capsys,
) -> None:
    # Given: an empty isolated cache and the packaged public suite.
    cache_dir = tmp_path / "cache"

    # When: fetching from package data and inspecting the cached suite.
    fetch_code = main(
        [
            "fetch-suite",
            "--accept-suite-terms",
            "--cache-dir",
            str(cache_dir),
        ],
    )
    fetch_out = capsys.readouterr().out
    inspect_code = main(["suite", "inspect", "--cache-dir", str(cache_dir)])
    inspect_out = capsys.readouterr().out

    # Then: the packaged distribution verifies and exposes the three packaged benches.
    assert fetch_code == 0
    assert "suite_id  core-text-v1" in fetch_out
    assert "cached    " in fetch_out
    assert inspect_code == 0
    assert "benches   ifbench, mmlu_pro, tc_json_v1" in inspect_out


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
    assert "tc_json_v1" in output
    assert "items     3" in output
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
    (path / "tc_json_v1.jsonl").write_text(
        json.dumps(
            {
                "gold": {
                    "calls": [{"arguments": {"a": 1, "b": 2}, "name": "add"}],
                    "order_matters": True,
                },
                "id": "tc-1",
                "match_policy": {
                    "allow_default_omission": True,
                    "default": "typed_canonical_json_equality",
                    "normalizers": {},
                    "unordered_arrays": [],
                },
                "prompt": "user: Add 1 and 2.",
                "source": "local-test",
                "stratum": "smoke",
                "tools": [
                    {
                        "description": "Add two integers.",
                        "name": "add",
                        "parameters": {
                            "additionalProperties": False,
                            "properties": {
                                "a": {"type": "integer"},
                                "b": {"type": "integer"},
                            },
                            "required": ["a", "b"],
                            "type": "object",
                        },
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    mmlu_hash = _sha256(path / "mmlu_pro.jsonl")
    ifbench_hash = _sha256(path / "ifbench.jsonl")
    tc_json_hash = _sha256(path / "tc_json_v1.jsonl")
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
                    "tc_json_v1": {
                        "chance_correction_baseline": 0.0,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {
                            "standard": {"file": "tc_json_v1.jsonl", "item_count": 1, "sha256": tc_json_hash},
                        },
                        "template_text": (
                            "Tool catalog:\n{tool_catalog}\n\n"
                            "User request:\n{user_request}\n"
                        ),
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
                    "tc_json_v1.jsonl": {"item_count": 1, "sha256": tc_json_hash},
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
