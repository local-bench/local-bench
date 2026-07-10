from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.landing import (
    LandingError,
    _append_json_array_item,
    _assert_generations_untouched,
    changed_existing_ranked_rows,
    land_run,
)
from localbench.scoring.scorecard import scorecard_identity


def test_changed_existing_ranked_rows_is_exact_and_ignores_new_rows() -> None:
    existing = {"slug": "existing", "ranked": True, "composite": {"point": 42.0}}
    current = {"models": [existing, {"slug": "diagnostic", "ranked": False}]}
    candidate = {"models": [dict(existing), {"slug": "new", "ranked": True}]}

    assert changed_existing_ranked_rows(current, candidate) == ()

    candidate["models"][0]["composite"] = {"point": 42.1}
    assert changed_existing_ranked_rows(current, candidate) == ("existing",)


def test_generation_guard_allows_only_coding_verdict_fields() -> None:
    original = _run_record()
    verified = _run_record(verified=True)

    _assert_generations_untouched(original, verified)

    verified["items"][0]["response_text"] = "changed generation"
    with pytest.raises(LandingError, match="changed generation data"):
        _assert_generations_untouched(original, verified)


def test_append_json_array_item_preserves_existing_text() -> None:
    original = b'[\n  {\n    "value": 1.00\n  }\n]\n'

    updated = _append_json_array_item(original, {"value": 2})

    assert b'"value": 1.00' in updated
    assert json.loads(updated) == [{"value": 1.0}, {"value": 2}]


def test_land_run_dry_run_preflights_without_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from localbench import landing

    run_dir = tmp_path / "incoming"
    run_dir.mkdir()
    _write(run_dir / "localbench-run.json", _run_record())
    _write(run_dir / "coding-verified.json", _run_record(verified=True))
    sources_path = tmp_path / "data_sources.json"
    sources_path.write_text("[]\n", encoding="utf-8")
    catalog_path = tmp_path / "model_catalog.json"
    _write(
        catalog_path,
        {
            "models": [
                {
                    "id": "org/new-model",
                    "slug": "new-model",
                    "display_name": "New Model",
                    "family": "New",
                    "org": "org",
                    "gguf_repo": "org/new-model-GGUF",
                },
            ],
        },
    )
    board_path = tmp_path / "board_v2.json"
    existing = {"slug": "existing", "ranked": True, "composite": {"point": 1.0}}
    _write(board_path, {"models": [existing], "manifest": {"generated_at": "2026-07-10T00:00:00Z"}})
    landed_dir = tmp_path / "landed"
    preflight_calls: list[tuple[Path, Path, Path]] = []

    def fake_build_board(**_: object) -> dict[str, object]:
        stem = "new-model-q4-k-m-" + "a" * 12 + "-bounded-final-v2"
        return {
            "models": [
                dict(existing),
                {
                    "slug": "new-model",
                    "ranked": True,
                    "systems": [
                        {
                            "run_id": f"new-model__{stem}",
                            "ranked": True,
                        },
                    ],
                },
            ],
            "manifest": {"generated_at": "2026-07-10T00:00:00Z"},
        }

    monkeypatch.setattr(landing, "DATA_SOURCES_PATH", sources_path)
    monkeypatch.setattr(landing, "MODEL_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(landing, "DEFAULT_OUT_V2", board_path)
    monkeypatch.setattr(landing, "LANDED_RUNS_DIR", landed_dir)
    monkeypatch.setattr(landing, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(landing, "_validate_launch_freeze", lambda: None)
    monkeypatch.setattr(landing, "build_board", fake_build_board)
    monkeypatch.setattr(
        landing,
        "_preflight_web_build",
        lambda sources, board, out: preflight_calls.append((sources, board, out)),
    )

    before = sources_path.read_bytes()
    result = land_run(run_dir, dry_run=True)

    assert result.dry_run is True
    assert result.source_added is True
    assert result.model_sha256 == "a" * 64
    assert sources_path.read_bytes() == before
    assert not landed_dir.exists()
    assert len(preflight_calls) == 1


def _run_record(*, verified: bool = False) -> dict[str, object]:
    scorecard = scorecard_identity("answer_only_v1", lane_spec_id="bounded-final-v2")
    artifact = {
        "sanitized_code": "def answer(): return 1",
        "verdict_source": "verifier" if verified else "pending",
    }
    item = {
        "id": "bcbh-001",
        "bench": "bigcodebench_hard",
        "response_text": "```python\ndef answer(): return 1\n```",
        "correct": True if verified else None,
        "code_artifact": artifact,
        "max_tokens": 16,
        "generated_tokens": {"total": 8},
    }
    model_manifest = {
        "family": "new",
        "quant_label": "Q4_K_M",
        "file_name": "new-model-Q4_K_M.gguf",
        "file_size_bytes": 4_000_000_000,
        "file_sha256": "a" * 64,
        "format": "GGUF",
    }
    return {
        "model": {"name": "new-model-q4-k-m", "file_sha256": "a" * 64},
        "manifest": {
            "model": model_manifest,
            "scorecard": scorecard,
            "suite": {"lane": "bounded-final-v2", "tier": "standard"},
        },
        "items": [item],
        "benches": {"bigcodebench_hard": {"n": 1, "raw_accuracy": 1.0}},
        "totals": {"n_items": 1, "n_errors": 0},
        "agentic_run": {
            "runs": [
                {
                    "subset_hash": "agentic-subset",
                    "infra_timeout_rate": 0.0,
                    "infra_sandbox_rate": 0.0,
                    "harness_error_rate": 0.0,
                },
                {
                    "subset_hash": "agentic-subset",
                    "infra_timeout_rate": 0.0,
                    "infra_sandbox_rate": 0.0,
                    "harness_error_rate": 0.0,
                },
            ],
        },
    }


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
