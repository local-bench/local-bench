from __future__ import annotations

from localbench.progress import (
    BenchProgressPlan,
    NonTtyProgressCadence,
    ProgressEstimator,
    ProgressLineFormatter,
    _segment_widths,
)


def test_progress_eta_waits_for_samples_then_weights_by_bench() -> None:
    estimator = ProgressEstimator(
        [
            BenchProgressPlan("mmlu_pro", 4),
            BenchProgressPlan("ifbench", 2),
        ],
        min_samples=3,
        rolling_window=3,
    )

    estimator.record_completion("mmlu_pro", 5.0)
    estimator.record_completion("mmlu_pro", 5.0)
    assert estimator.eta_seconds() is None

    estimator.record_completion("ifbench", 2.0)

    assert estimator.eta_seconds() == 12.0


def test_progress_rolling_average_uses_recent_items() -> None:
    estimator = ProgressEstimator(
        [BenchProgressPlan("tc_json_v1", 6)],
        min_samples=3,
        rolling_window=3,
    )

    estimator.record_completion("tc_json_v1", 20.0)
    estimator.record_completion("tc_json_v1", 4.0)
    estimator.record_completion("tc_json_v1", 2.0)
    estimator.record_completion("tc_json_v1", 8.0)

    assert estimator.per_bench_average_seconds("tc_json_v1") == 14.0 / 3.0
    assert estimator.eta_seconds() == 2 * (14.0 / 3.0)


def test_progress_eta_clamps_at_zero_when_done() -> None:
    estimator = ProgressEstimator([BenchProgressPlan("amo", 1)], min_samples=1)

    estimator.record_completion("amo", 3.0)

    assert estimator.eta_seconds() == 0.0


def test_progress_formatter_truncates_to_console_width() -> None:
    formatter = ProgressLineFormatter(width=72)
    estimator = ProgressEstimator(
        [BenchProgressPlan("bigcodebench_hard", 10)],
        min_samples=1,
    )
    estimator.record_completion("bigcodebench_hard", 5.0)

    line = formatter.status_line(
        estimator.snapshot(
            current_bench="bigcodebench_hard",
            current_bench_done=1,
            elapsed_seconds=15.0,
        ),
    )

    assert len(line) <= 72
    assert "bigcodebench_hard" in line
    assert "1/10 bench" in line
    assert "10.0%" in line
    assert "ETA" in line


def test_progress_status_line_renders_overall_bar() -> None:
    formatter = ProgressLineFormatter(width=200, bar_width=20)
    estimator = ProgressEstimator([BenchProgressPlan("mmlu_pro", 10)], min_samples=1)
    estimator.record_completion("mmlu_pro", 5.0)

    line = formatter.status_line(
        estimator.snapshot(current_bench="mmlu_pro", current_bench_done=1, elapsed_seconds=5.0),
    )

    assert "[██░░░░░░░░░░░░░░░░░░]" in line
    assert "10.0%" in line


def test_progress_bar_clamps_and_fills_at_bounds() -> None:
    formatter = ProgressLineFormatter(width=200, bar_width=10)

    assert formatter._bar(0.0) == "[░░░░░░░░░░] "
    assert formatter._bar(100.0) == "[██████████] "
    assert formatter._bar(250.0) == "[██████████] "
    assert formatter._bar(-5.0) == "[░░░░░░░░░░] "


def test_progress_bar_falls_back_to_ascii_for_legacy_encodings() -> None:
    formatter = ProgressLineFormatter(width=200, bar_width=10, bar_chars=("#", "-"))

    assert formatter._bar(50.0) == "[#####-----] "


def test_progress_segmented_bar_allocates_width_by_bench_share() -> None:
    formatter = ProgressLineFormatter(width=200, bar_width=20)
    estimator = ProgressEstimator(
        [BenchProgressPlan("mmlu_pro", 50), BenchProgressPlan("ifbench", 50)],
        min_samples=1,
    )
    for _ in range(50):
        estimator.record_completion("mmlu_pro", 1.0)

    line = formatter.status_line(
        estimator.snapshot(current_bench="ifbench", current_bench_done=0, elapsed_seconds=50.0),
    )

    # Given equal item counts: mmlu_pro's half is fully filled, ifbench's half fully empty.
    assert "[██████████░░░░░░░░░░]" in line


def test_progress_segmented_bar_colors_segments_per_bench() -> None:
    formatter = ProgressLineFormatter(width=400, bar_width=10, use_color=True)
    estimator = ProgressEstimator(
        [BenchProgressPlan("mmlu_pro", 5), BenchProgressPlan("bigcodebench_hard", 5)],
        min_samples=1,
    )
    estimator.record_completion("mmlu_pro", 1.0)

    line = formatter.status_line(
        estimator.snapshot(current_bench="mmlu_pro", current_bench_done=1, elapsed_seconds=1.0),
    )

    # Knowledge (mmlu_pro) and coding (bigcodebench_hard) axis colors from the site palette.
    assert "\x1b[38;2;124;159;255m" in line
    assert "\x1b[38;2;255;95;168m" in line
    assert line.count("\x1b[0m") == 2


def test_progress_segmented_bar_gives_tiny_benches_a_visible_cell() -> None:
    widths = _segment_widths([397, 2, 1], 20)

    assert sum(widths) == 20
    assert widths[1] >= 1
    assert widths[2] >= 1


def test_progress_color_lines_drop_bar_by_visible_width_not_raw_length() -> None:
    formatter = ProgressLineFormatter(width=72, bar_width=20, use_color=True)
    estimator = ProgressEstimator([BenchProgressPlan("bigcodebench_hard", 10)], min_samples=1)
    estimator.record_completion("bigcodebench_hard", 5.0)

    line = formatter.status_line(
        estimator.snapshot(current_bench="bigcodebench_hard", current_bench_done=1, elapsed_seconds=15.0),
    )

    assert "\x1b[" not in line
    assert len(line) <= 72
    assert "1/10 bench" in line


def test_progress_prerun_total_line_reports_estimating_before_samples() -> None:
    formatter = ProgressLineFormatter(width=120)

    line = formatter.prerun_total_line(
        [
            BenchProgressPlan("mmlu_pro", 2),
            BenchProgressPlan("ifbench", 1),
        ],
    )

    assert line == "estimate   3 items across 2 benches; ETA estimating..."


def test_non_tty_cadence_emits_on_item_or_time_threshold() -> None:
    cadence = NonTtyProgressCadence(item_interval=25, seconds_interval=300.0)

    assert cadence.should_emit(now_seconds=0.0, completed_items=0) is True
    cadence.mark_emitted(now_seconds=0.0, completed_items=0)

    assert cadence.should_emit(now_seconds=299.0, completed_items=24) is False
    assert cadence.should_emit(now_seconds=299.0, completed_items=25) is True
    cadence.mark_emitted(now_seconds=299.0, completed_items=25)

    assert cadence.should_emit(now_seconds=598.0, completed_items=49) is False
    assert cadence.should_emit(now_seconds=599.0, completed_items=49) is True
