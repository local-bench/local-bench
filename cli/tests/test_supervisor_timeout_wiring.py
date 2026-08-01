from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from localbench._suite import read_json_object
from localbench.cli import _parser, _run_supervised
from localbench.run_plan import resolve_run_benches
from localbench.supervisor import SupervisorConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUITE_DIR = _REPO_ROOT / "suite" / "v1"


def _args(*, bench: str, lane: str = "bounded-final-v2") -> argparse.Namespace:
    return _parser().parse_args(
        [
            "run",
            "--endpoint",
            "http://local/v1",
            "--model",
            "fixture",
            "--suite",
            "suite-v1",
            "--suite-dir",
            str(_SUITE_DIR),
            "--bench",
            bench,
            "--lane",
            lane,
        ],
    )


def _bench_choice(args: argparse.Namespace) -> str:
    suite = read_json_object(_SUITE_DIR / "suite.json")
    return ",".join(resolve_run_benches(args.bench, suite))


@pytest.mark.parametrize(
    ("bench", "expected_static"),
    (("appworld_c", 0), ("mmlu_pro,appworld_c", 400), ("all", 1311)),
)
def test_run_supervised_derives_agentic_work_from_real_suite_selection(
    bench: str,
    expected_static: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[SupervisorConfig] = []

    def capture(config: SupervisorConfig) -> int:
        captured.append(config)
        return 73

    args = _args(bench=bench)
    monkeypatch.setattr("localbench.cli.run_supervised", capture)

    # Given: an agentic-only, mixed, or complete selection from the real suite-v1 manifest.
    # When: the actual CLI supervision entry point builds its worker configuration.
    result = _run_supervised(args, "standard", tmp_path / "run.json", _bench_choice(args))

    # Then: static items and the signed 96-task agentic set both reach the lease plan.
    assert result == 73
    assert len(captured) == 1
    timeout_budget = captured[0].timeout_budget
    assert timeout_budget is not None
    assert timeout_budget.remaining_static_items == expected_static
    assert timeout_budget.remaining_agentic_tasks == 96
    assert timeout_budget.campaign_seconds == (
        300.0
        + expected_static * 14988.0
        + 96 * 3000 * 3
        + 300.0
    )


def test_run_supervised_keeps_agentic_lease_disabled_for_legacy_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[SupervisorConfig] = []

    def capture(config: SupervisorConfig) -> int:
        captured.append(config)
        return 0

    args = _args(bench="appworld_c", lane="answer-only")
    monkeypatch.setattr("localbench.cli.run_supervised", capture)

    # Given: genuine legacy lane construction with the real agentic suite selection.
    # When: the CLI enters supervision without a resolved execution profile.
    _run_supervised(args, "standard", tmp_path / "run.json", _bench_choice(args))

    # Then: T6 does not reinterpret the frozen legacy fallback as profile-derived.
    assert len(captured) == 1
    assert captured[0].timeout_budget is None
