from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.kld import (
    KldParseError,
    build_drift,
    compute_churn,
    parse_kld_log,
    run_kld_ladder,
)
from localbench.kld.run import _QuantDrift

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kld"


def _fixture(label: str) -> str:
    return (_FIXTURES / f"kld-{label}-vs-bf16.log").read_text(encoding="utf-8")


def test_parse_kld_log_q4_matches_captured_llama_perplexity_values() -> None:
    # Given a real llama-perplexity --kl-divergence pass (Gemma-12B Q4_K_M vs BF16).
    stats = parse_kld_log(_fixture("Q4_K_M"))

    # Then every headline + curve metric is parsed from the two panels.
    assert stats.mean_kld == pytest.approx(0.914923)
    assert stats.mean_kld_stderr == pytest.approx(0.015859)
    assert stats.median_kld == pytest.approx(0.311585)
    assert stats.q90_kld == pytest.approx(2.391408)
    assert stats.q95_kld == pytest.approx(3.906530)
    assert stats.q99_kld == pytest.approx(8.561064)
    assert stats.q999_kld == pytest.approx(16.962540)
    assert stats.max_kld == pytest.approx(28.704802)
    assert stats.min_kld == pytest.approx(-0.000002)
    assert stats.same_top_p == pytest.approx(67.059)
    assert stats.same_top_p_stderr == pytest.approx(0.429)
    assert stats.rms_dp == pytest.approx(17.212)
    assert stats.mean_ppl_quant == pytest.approx(507.283704)
    assert stats.mean_ppl_base == pytest.approx(437.785463)


def test_parse_kld_log_curve_rises_monotonically_q8_to_q3() -> None:
    # Given the captured ladder (the validated Gemma-12B shape).
    q8 = parse_kld_log(_fixture("Q8_0"))
    q4 = parse_kld_log(_fixture("Q4_K_M"))
    q3 = parse_kld_log(_fixture("Q3_K_M"))

    # Then mean KLD rises and same-top-p falls as the quant gets coarser.
    assert q8.mean_kld < q4.mean_kld < q3.mean_kld
    assert q8.same_top_p > q4.same_top_p > q3.same_top_p
    # Q8 is near-lossless vs BF16; Q3 is the cliff.
    assert q8.mean_kld < 0.3
    assert q3.mean_kld > 1.0


def test_parse_kld_log_raises_when_kld_panel_is_absent() -> None:
    # Given output with no KL divergence statistics panel (e.g. a baseline pass).
    with pytest.raises(KldParseError):
        parse_kld_log("Mean PPL(base): 437.0\nperplexity: done\n")


def test_compute_churn_counts_correctness_flips_per_bench() -> None:
    # Given a reference run and a quant run over the same items.
    reference = _run_record(
        [("mmlu_pro", "k1", True), ("mmlu_pro", "k2", True), ("ifbench", "i1", False)]
    )
    quant = _run_record(
        [("mmlu_pro", "k1", True), ("mmlu_pro", "k2", False), ("ifbench", "i1", True)]
    )

    # When computing churn.
    result = compute_churn(reference, quant)

    # Then 2 of 3 items flipped, broken out per bench.
    assert result.n == 3
    assert result.flips == 2
    assert result.churn == pytest.approx(2 / 3)
    assert result.by_bench == {"ifbench": pytest.approx(1.0), "mmlu_pro": pytest.approx(0.5)}


def test_compute_churn_requires_identical_item_ids() -> None:
    reference = _run_record([("mmlu_pro", "k1", True)])
    quant = _run_record([("mmlu_pro", "k2", True)])
    with pytest.raises(ValueError, match="same item ids"):
        compute_churn(reference, quant)


def test_build_drift_shapes_the_model_page_record() -> None:
    drift = build_drift(
        "gemma-4-12b-it",
        "BF16",
        {"path": "calib.txt", "bytes": 100, "sha256": "abc"},
        {"Q4_K_M": _QuantDrift(parse_kld_log(_fixture("Q4_K_M")), None)},
    )
    assert drift["schema"] == "localbench-kld-v1"
    assert drift["model"] == "gemma-4-12b-it"
    assert drift["reference"] == "BF16"
    assert drift["calib"]["sha256"] == "abc"
    assert drift["quants"]["Q4_K_M"]["kld"]["mean_kld"] == pytest.approx(0.914923)
    assert drift["quants"]["Q4_K_M"]["churn"] is None


def test_run_kld_ladder_assembles_drift_with_injected_runner(tmp_path: Path) -> None:
    # Given fixture llama-perplexity output keyed by the quant model path, plus a
    # calib file and paired task runs for churn -- no llama-perplexity binary needed.
    reference = tmp_path / "gemma-BF16.gguf"
    quant_paths = {"Q8_0": tmp_path / "gemma-Q8_0.gguf", "Q4_K_M": tmp_path / "gemma-Q4_K_M.gguf"}
    fixture_by_path = {str(path): _fixture(label) for label, path in quant_paths.items()}
    calib = tmp_path / "calib.txt"
    calib.write_text("hashed calibration corpus", encoding="utf-8")

    churn_ref = tmp_path / "run-bf16.json"
    churn_q4 = tmp_path / "run-q4.json"
    churn_ref.write_text(json.dumps(_run_record([("mmlu_pro", "k1", True), ("mmlu_pro", "k2", True)])), encoding="utf-8")
    churn_q4.write_text(json.dumps(_run_record([("mmlu_pro", "k1", True), ("mmlu_pro", "k2", False)])), encoding="utf-8")

    def fake_runner(cmd: list[str]) -> str:
        model = cmd[cmd.index("-m") + 1]
        if "--kl-divergence" not in cmd:  # the reference baseline pass
            return "baseline written\n"
        return fixture_by_path[model]

    # When running the ladder.
    drift = run_kld_ladder(
        llama_perplexity=tmp_path / "llama-perplexity",
        reference=reference,
        quants=quant_paths,
        calib=calib,
        model_label="gemma-4-12b-it",
        reference_label="BF16",
        work_dir=tmp_path / "kld",
        churn_reference=churn_ref,
        churn_quants={"Q4_K_M": churn_q4},
        runner=fake_runner,
    )

    # Then both quants are parsed, churn is attached only where a paired run exists,
    # and the calib is hashed for provenance.
    assert set(drift["quants"]) == {"Q8_0", "Q4_K_M"}
    assert drift["quants"]["Q8_0"]["kld"]["mean_kld"] < drift["quants"]["Q4_K_M"]["kld"]["mean_kld"]
    assert drift["quants"]["Q8_0"]["churn"] is None
    assert drift["quants"]["Q4_K_M"]["churn"]["flips"] == 1
    assert drift["quants"]["Q4_K_M"]["churn"]["churn"] == pytest.approx(0.5)
    assert len(drift["calib"]["sha256"]) == 64
    assert (tmp_path / "kld" / "kld-Q4_K_M.log").exists()


def _run_record(items: list[tuple[str, str, bool]]) -> dict[str, object]:
    return {
        "items": [
            {"id": item_id, "bench": bench, "correct": correct}
            for bench, item_id, correct in items
        ]
    }
