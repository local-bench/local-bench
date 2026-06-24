"""Tests for the empty-machine local release-test harness."""

from __future__ import annotations

from pathlib import Path

from localbench.release_test import ReleaseTestCommand, release_test_plan


def test_release_test_plan_uses_fresh_home_and_local_suite_source(tmp_path: Path) -> None:
    # Given: a wheel path, local suite bundle source, and work directory.
    wheel = tmp_path / "localbench-0.1.0-py3-none-any.whl"
    suite_source = tmp_path / "suite-source"
    work_dir = tmp_path / "empty"

    # When: building the empty-machine command plan.
    plan = release_test_plan(
        wheel=wheel,
        suite_source=suite_source,
        work_dir=work_dir,
        endpoint="http://127.0.0.1:8000/v1",
        model="smoke-model",
    )

    # Then: it exercises install, fetch, inspect, dry-run, and two-item smoke locally.
    assert [command.name for command in plan.commands] == [
        "create-venv",
        "install-wheel",
        "fetch-suite",
        "suite-inspect",
        "run-dry-run",
        "run-smoke-2",
    ]
    assert all(isinstance(command, ReleaseTestCommand) for command in plan.commands)
    assert plan.home == work_dir / "home"
    assert str(suite_source) in _joined(plan.commands[2].argv)
    assert "--accept-suite-terms" in plan.commands[2].argv
    assert "--dry-run" in plan.commands[4].argv
    assert plan.commands[5].argv[-4:] == ("--bench", "mmlu_pro", "--max-items", "2")
    assert plan.commands[5].argv[-2:] == ("--max-items", "2")


def _joined(argv: tuple[str, ...]) -> str:
    return " ".join(argv)
