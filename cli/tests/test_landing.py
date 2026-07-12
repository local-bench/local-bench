from __future__ import annotations

import json
from pathlib import Path

import pytest

from board_fixtures import (
    FROZEN_AT,
    inline_agentic_provenance,
    run_record as board_run_record,
    source as board_source,
    write_run,
)
from localbench.landing import (
    LandingError,
    _agentic_campaign_aggregate,
    _append_json_array_item,
    _assert_generations_untouched,
    _assert_protected_public_runs_unchanged,
    _assert_rescore_coverage,
    _candidate_system,
    _rescore,
    changed_existing_ranked_rows,
    land_run,
)
from localbench._suite import read_json_object, render_benches
from localbench.coding_exec.receipt import attach_signed_verifier_receipt, verify_signed_verifier_receipt
from localbench.scoring.scorecard import scorecard_identity
from localbench.submissions.keys import write_private_key
from localbench.suite_release import COVERAGE_PROFILES, CoverageProfile


def test_changed_existing_ranked_rows_is_exact_and_ignores_new_rows() -> None:
    existing = {"slug": "existing", "ranked": True, "composite": {"point": 42.0}}
    current = {"models": [existing, {"slug": "diagnostic", "ranked": False}]}
    candidate = {"models": [dict(existing), {"slug": "new", "ranked": True}]}

    assert changed_existing_ranked_rows(current, candidate) == ()

    candidate["models"][0]["composite"] = {"point": 42.1}
    assert changed_existing_ranked_rows(current, candidate) == ("existing",)


def test_candidate_system_surfaces_staged_run_skip_reason() -> None:
    stem = "fixture-model-new-quant-bounded-final-v2"
    reason = "incomplete: inline appworld_c mean_asr does not match bench raw_accuracy"
    board = {
        "models": [{"slug": "fixture-model", "systems": [{"run_id": "fixture-model__existing"}]}],
        "manifest": {"skipped_runs": [{"file": f"{stem}.json", "reason": reason}]},
    }

    with pytest.raises(LandingError, match="mean_asr does not match bench raw_accuracy") as error:
        _candidate_system(board, stem, {"model_label": "Fixture Model"})

    assert reason in str(error.value)

    board["manifest"] = {"skipped_runs": []}
    with pytest.raises(LandingError, match="existing run_ids.*fixture-model__existing"):
        _candidate_system(board, stem, {"model_label": "Fixture Model"})


def test_existing_model_new_staged_system_is_present_with_canonical_run_id(tmp_path: Path) -> None:
    from localbench.scoring.board import build_board

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    write_run(runs_dir / "existing.json", board_run_record())
    stem = "fixture-model-new-quant-bounded-final-v2"
    staged_run = tmp_path / "stage" / f"{stem}.json"
    staged_run.parent.mkdir()
    staged_record = board_run_record(appworld_inline=(False, True))
    first_run = inline_agentic_provenance((False, False))["diagnostics"]
    agentic = inline_agentic_provenance((False, True))
    agentic["runs"][0] = {"run_index": 1, "results_path": "agentic/run1.json", **first_run}
    agentic["asr_series"] = [0.0, 0.5]
    agentic["mean_asr"] = 0.25
    agentic["max_abs_delta_pp"] = 50.0
    staged_record["agentic_run"] = agentic
    staged_record["benches"]["appworld_c"] = _agentic_campaign_aggregate(staged_record)
    write_run(staged_run, staged_record)
    sources = [
        board_source("Fixture Model", "existing.json", model_id="org/fixture-model"),
        board_source("Fixture Model", str(staged_run), model_id="org/fixture-model"),
    ]
    curation = tmp_path / "staged-data_sources.json"
    _write(curation, sources)

    board = build_board(
        runs_dir=runs_dir,
        curation_path=curation,
        generated_at=FROZEN_AT,
        bootstrap_iters=50,
    )

    system = _candidate_system(board, stem, sources[-1])
    assert system["run_id"] == f"fixture-model__{stem}"


def test_agentic_campaign_aggregate_uses_campaign_mean_not_final_run_items() -> None:
    aggregate = _agentic_campaign_aggregate(
        {
            "agentic_run": {
                "subset_size": 96,
                "asr_series": [0.09375, 0.10416666666666667],
                "mean_asr": 0.09895833333333334,
            }
        }
    )

    assert aggregate["n"] == 96
    assert aggregate["raw_accuracy"] == 0.09895833333333334


def test_generation_guard_allows_only_coding_verdict_fields() -> None:
    original = _run_record()
    verified = _run_record(verified=True)

    _assert_generations_untouched(original, verified)

    verified["items"][0]["response_text"] = "changed generation"
    with pytest.raises(LandingError, match="changed generation data"):
        _assert_generations_untouched(original, verified)

    forged = _run_record(verified=True)
    forged["benches"] = {"bigcodebench_hard": {"n": 1, "raw_accuracy": 0.0}}
    with pytest.raises(LandingError, match="non-coding top-level"):
        _assert_generations_untouched(original, forged)


def test_append_json_array_item_preserves_existing_text() -> None:
    original = b'[\n  {\n    "value": 1.00\n  }\n]\n'

    updated = _append_json_array_item(original, {"value": 2})

    assert b'"value": 1.00' in updated
    assert json.loads(updated) == [{"value": 1.0}, {"value": 2}]


def test_protected_public_run_guard_covers_model_and_standalone_detail(tmp_path: Path) -> None:
    run_id = "gemma-4-12b-it__gemma-4-12b-it-qat-ud-q2kxl-bounded-final-v2"
    before = tmp_path / "before"
    after = tmp_path / "after"
    for root in (before, after):
        (root / "models").mkdir(parents=True)
        (root / "runs").mkdir()
        _write(root / "models" / "gemma-4-12b-it.json", {"runs": [{"run_id": run_id, "score": 1}]})
        _write(root / "runs" / f"{run_id}.json", {"run_id": run_id, "items": [1]})

    _assert_protected_public_runs_unchanged(before, after)

    _write(after / "runs" / f"{run_id}.json", {"run_id": run_id, "items": [2]})
    with pytest.raises(LandingError, match="protected public run detail"):
        _assert_protected_public_runs_unchanged(before, after)

    _write(after / "runs" / f"{run_id}.json", {"run_id": run_id, "items": [1]})
    _write(after / "models" / "gemma-4-12b-it.json", {"runs": [{"run_id": run_id, "score": 2}]})
    with pytest.raises(LandingError, match="protected public run"):
        _assert_protected_public_runs_unchanged(before, after)


def test_verifier_receipt_signature_covers_the_coding_patch(tmp_path: Path) -> None:
    run = _run_record(verified=True)
    key_path = tmp_path / "verifier.pem"
    public_key = write_private_key(key_path, seed=bytes(range(32)))
    attach_signed_verifier_receipt(
        run,
        source_bytes=b"original-run-bytes",
        suite_dir=Path(__file__).resolve().parents[2] / "suite" / "v1",
        image_digest="verifier@example.invalid@sha256:" + "a" * 64,
        signing_key=key_path,
    )

    receipt = run["coding_verifier_receipt"]
    assert isinstance(receipt, dict)
    payload = verify_signed_verifier_receipt(receipt, public_key)
    assert payload["complete"] is True
    receipt_payload = receipt["payload"]
    assert isinstance(receipt_payload, dict)
    receipt_payload["coding_patch_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="signature"):
        verify_signed_verifier_receipt(receipt, public_key)


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
    monkeypatch.setattr(landing, "_assert_campaign_complete", lambda *_: None)
    monkeypatch.setattr(landing, "_assert_verifier_receipt", lambda *_args, **_kwargs: "b" * 64)
    monkeypatch.setattr(landing, "_hash_actual_gguf", lambda *_args, **_kwargs: "a" * 64)
    monkeypatch.setattr(landing, "_assert_rescore_coverage", lambda *_: landing.SUITE_DIR)
    monkeypatch.setattr(landing, "_recompute_derived_record", lambda *_: None)
    monkeypatch.setattr(landing, "_assert_protected_public_runs_unchanged", lambda *_: None)
    monkeypatch.setattr(landing, "build_board", fake_build_board)
    monkeypatch.setattr(
        landing,
        "_preflight_web_build",
        lambda sources, board, out: preflight_calls.append((sources, board, out)),
    )

    before = sources_path.read_bytes()
    result = land_run(
        run_dir,
        gguf_path=tmp_path / "model.gguf",
        verifier_public_key="c" * 64,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.source_added is True
    assert result.model_sha256 == "a" * 64
    assert sources_path.read_bytes() == before
    assert not landed_dir.exists()
    assert len(preflight_calls) == 1


def test_rescore_coverage_rejects_missing_future_profile_bench(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench import landing

    suite_dir = _future_split_suite(tmp_path)
    profile_id = "future-tool-use-v2"
    monkeypatch.setattr(landing, "REPO_ROOT", tmp_path)
    monkeypatch.setitem(
        COVERAGE_PROFILES,
        profile_id,
        CoverageProfile(
            profile_id=profile_id,
            benches=("bfcl_multi_turn_base", "bfcl_multi_turn_long_context"),
            headline_weight=1.0,
            rank_scope=profile_id,
        ),
    )
    items = _rendered_item_refs(suite_dir, "bfcl_multi_turn_long_context")
    record = _coverage_record(profile_id, items)
    record["manifest"]["scorecard"] = scorecard_identity(  # type: ignore[index]
        "answer_only_v1",
        lane_spec_id="bounded-final-v2",
    )
    monkeypatch.setattr(
        landing,
        "scorecard_identity",
        lambda *_args, **_kwargs: {
            "scorecard_id": "future-scorecard",
            "registry": [
                {
                    "key": "tool_calling",
                    "benches": ["bfcl_multi_turn_base", "bfcl_multi_turn_long_context"],
                }
            ],
        },
    )

    with pytest.raises(
        LandingError,
        match=(
            r"record cannot satisfy stamped suite coverage future-tool-use-v2: "
            r"coverage mismatch: bfcl_multi_turn_base \(0/2 items\)"
        ),
    ):
        _rescore(
            record,
            original_path=tmp_path / "localbench-run.json",
            verified_path=tmp_path / "coding-verified.json",
            verifier_receipt_sha256="a" * 64,
        )


def test_rescore_coverage_rejects_unsplit_bench_from_future_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench import landing

    suite_dir = _future_split_suite(tmp_path)
    profile_id = "future-tool-use-v2"
    monkeypatch.setattr(landing, "REPO_ROOT", tmp_path)
    monkeypatch.setitem(
        COVERAGE_PROFILES,
        profile_id,
        CoverageProfile(
            profile_id=profile_id,
            benches=("bfcl_multi_turn_base", "bfcl_multi_turn_long_context"),
            headline_weight=1.0,
            rank_scope=profile_id,
        ),
    )
    items = [
        *_rendered_item_refs(suite_dir, "bfcl_multi_turn_base,bfcl_multi_turn_long_context"),
        {"bench": "bfcl_multi_turn", "id": "legacy-unsplit"},
    ]

    with pytest.raises(
        LandingError,
        match=r"undefined bench items: bfcl_multi_turn \(1 items\)",
    ):
        _assert_rescore_coverage(_coverage_record(profile_id, items), items)


def test_rescore_coverage_accepts_complete_current_suite_record() -> None:
    suite_dir = Path(__file__).resolve().parents[2] / "suite" / "v1"
    profile_id = "full-exec-6axis-v1"
    static_benches = [bench for bench in COVERAGE_PROFILES[profile_id].benches if bench != "appworld_c"]
    items = _rendered_item_refs(suite_dir, ",".join(static_benches))
    items.extend({"bench": "appworld_c", "id": f"appworld-{index}"} for index in range(2))
    record = _coverage_record(profile_id, items)
    record["agentic_run"] = {"subset_size": 2}

    assert _assert_rescore_coverage(record, items) == suite_dir


def test_rescore_coverage_resolves_v2_tool_use_profile_from_release_identity() -> None:
    suite_dir = Path(__file__).resolve().parents[2] / "suite" / "v2"
    profile_id = "full-exec-tooluse-5axis-v2"
    static_benches = [
        bench for bench in COVERAGE_PROFILES[profile_id].benches if bench != "appworld_c"
    ]
    items = _rendered_item_refs(suite_dir, ",".join(static_benches))
    items.extend({"bench": "appworld_c", "id": f"appworld-{index}"} for index in range(2))
    record = _coverage_record(profile_id, items)
    record["agentic_run"] = {"subset_size": 2}

    assert _assert_rescore_coverage(record, items) == suite_dir


def test_staged_output_failure_restores_directories_and_removes_created_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench import landing

    temp_dir = tmp_path / "stage"
    temp_dir.mkdir()
    staged_file = temp_dir / "board.json"
    staged_file.write_text("new-board", encoding="utf-8")
    staged_dir = temp_dir / "site-data"
    staged_dir.mkdir()
    (staged_dir / "index.json").write_text("new-index", encoding="utf-8")
    staged_manifest = temp_dir / "manifest.json"
    staged_manifest.write_text("new-manifest", encoding="utf-8")
    staged_freeze = temp_dir / "freeze.ts"
    staged_freeze.write_text("new-freeze", encoding="utf-8")

    board = tmp_path / "live" / "board.json"
    board.parent.mkdir()
    board.write_text("old-board", encoding="utf-8")
    public_data = tmp_path / "live" / "data"
    public_data.mkdir()
    (public_data / "index.json").write_text("old-index", encoding="utf-8")
    created_manifest = tmp_path / "live" / "manifest.json"
    freeze = tmp_path / "live" / "freeze.ts"
    freeze.write_text("old-freeze", encoding="utf-8")

    monkeypatch.setattr(landing, "LANDING_LOCK_PATH", tmp_path / ".lock")
    monkeypatch.setattr(landing, "LANDING_JOURNAL_PATH", tmp_path / ".journal.json")
    monkeypatch.setattr(landing, "LANDING_BACKUPS_PATH", tmp_path / ".backups")
    real_replace = landing.os.replace

    def failing_replace(source: Path | str, target: Path | str) -> None:
        if Path(source) == staged_freeze:
            raise OSError("simulated final swap failure")
        real_replace(source, target)

    monkeypatch.setattr(landing.os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated"):
        landing._apply_staged_outputs(
            temp_dir,
            (
                (staged_file, board),
                (staged_dir, public_data),
                (staged_manifest, created_manifest),
                (staged_freeze, freeze),
            ),
        )

    assert board.read_text(encoding="utf-8") == "old-board"
    assert (public_data / "index.json").read_text(encoding="utf-8") == "old-index"
    assert not created_manifest.exists()
    assert freeze.read_text(encoding="utf-8") == "old-freeze"
    assert not landing.LANDING_LOCK_PATH.exists()
    assert not landing.LANDING_JOURNAL_PATH.exists()
    assert not landing.LANDING_BACKUPS_PATH.exists()


def test_rollback_failure_preserves_journal_lock_and_backups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench import landing

    temp_dir = tmp_path / "stage"
    temp_dir.mkdir()
    staged_board = temp_dir / "board.json"
    staged_board.write_text("new-board", encoding="utf-8")
    staged_freeze = temp_dir / "freeze.ts"
    staged_freeze.write_text("new-freeze", encoding="utf-8")
    board = tmp_path / "live" / "board.json"
    board.parent.mkdir()
    board.write_text("old-board", encoding="utf-8")
    freeze = tmp_path / "live" / "freeze.ts"
    freeze.write_text("old-freeze", encoding="utf-8")

    monkeypatch.setattr(landing, "LANDING_LOCK_PATH", tmp_path / ".lock")
    monkeypatch.setattr(landing, "LANDING_JOURNAL_PATH", tmp_path / ".journal.json")
    monkeypatch.setattr(landing, "LANDING_BACKUPS_PATH", tmp_path / ".backups")
    real_replace = landing.os.replace

    def failing_replace(source: Path | str, target: Path | str) -> None:
        source_path = Path(source)
        target_path = Path(target)
        if source_path == staged_freeze:
            raise OSError("simulated final swap failure")
        if source_path == landing.LANDING_BACKUPS_PATH / "1-freeze.ts" and target_path == freeze:
            raise OSError("simulated rollback restoration failure")
        real_replace(source, target)

    monkeypatch.setattr(landing.os, "replace", failing_replace)

    with pytest.raises(LandingError, match="rollback was incomplete") as error:
        landing._apply_staged_outputs(
            temp_dir,
            ((staged_board, board), (staged_freeze, freeze)),
        )

    assert str(landing.LANDING_JOURNAL_PATH) in str(error.value)
    assert str(landing.LANDING_BACKUPS_PATH) in str(error.value)
    assert landing.LANDING_LOCK_PATH.exists()
    assert landing.LANDING_JOURNAL_PATH.exists()
    assert landing.LANDING_BACKUPS_PATH.is_dir()
    assert (landing.LANDING_BACKUPS_PATH / "1-freeze.ts").read_text(encoding="utf-8") == "old-freeze"
    assert board.read_text(encoding="utf-8") == "old-board"


def _run_record(*, verified: bool = False) -> dict[str, object]:
    scorecard = scorecard_identity("answer_only_v1", lane_spec_id="bounded-final-v2")
    artifact = {
        "sanitized_code": "def answer(): return 1",
        "verdict_source": "verifier" if verified else "pending",
        **({"verdict": {"passed": True}} if verified else {}),
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


def _future_split_suite(tmp_path: Path) -> Path:
    suite_dir = tmp_path / "suite" / "v2"
    suite_dir.mkdir(parents=True)
    template = "templates/bfcl_multi_turn.txt"
    (suite_dir / "templates").mkdir()
    (suite_dir / template).write_text("unused", encoding="utf-8")
    benches: dict[str, object] = {}
    for bench in ("bfcl_multi_turn_base", "bfcl_multi_turn_long_context"):
        item_file = f"{bench}.jsonl"
        rows = [
            {
                "id": f"{bench}-{index}",
                "function": [],
                "question": [],
            }
            for index in range(2)
        ]
        (suite_dir / item_file).write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        benches[bench] = {
            "chance_correction_baseline": 0.0,
            "decoding": {"max_tokens": 16, "temperature": 0},
            "itemsets": {"standard": {"file": item_file, "item_count": 2}},
            "lane_caps": {},
            "template": template,
        }
    _write(suite_dir / "suite.json", {"version": "suite-v2", "benches": benches, "axes": {}})
    return suite_dir


def _rendered_item_refs(suite_dir: Path, bench_choice: str) -> list[dict[str, object]]:
    suite = read_json_object(suite_dir / "suite.json")
    rendered = render_benches(bench_choice, "standard", None, suite_dir, suite, [])
    return [
        {"bench": bench.name, "id": item["id"]}
        for bench in rendered
        for item in bench.benchmark_items
    ]


def _coverage_record(profile_id: str, items: list[dict[str, object]]) -> dict[str, object]:
    suite_version = (
        "suite-v2"
        if profile_id in {"future-tool-use-v2", "full-exec-tooluse-5axis-v2"}
        else "suite-v1"
    )
    return {
        "manifest": {
            "suite": {
                "coverage_profile_id": profile_id,
                "suite_version": suite_version,
                "suite_release_id": f"{suite_version}-{profile_id}",
                "tier": "standard",
            }
        },
        "items": items,
    }


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
