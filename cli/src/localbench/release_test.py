"""Empty-machine release-test command planning."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseTestCommand:
    name: str
    argv: tuple[str, ...]
    env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ReleaseTestPlan:
    work_dir: Path
    home: Path
    venv: Path
    commands: tuple[ReleaseTestCommand, ...]


def release_test_plan(
    *,
    wheel: Path,
    suite_source: Path,
    work_dir: Path,
    endpoint: str,
    model: str,
) -> ReleaseTestPlan:
    """Build the empty-machine command plan against a local suite source."""
    home = work_dir / "home"
    venv = work_dir / "venv"
    python = _venv_python(venv)
    base_env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "LOCALBENCH_CACHE_DIR": str(home / ".cache" / "localbench"),
    }
    localbench = str(_venv_script(venv, "localbench"))
    commands = (
        ReleaseTestCommand(
            "create-venv",
            (sys.executable, "-m", "venv", str(venv)),
            base_env,
        ),
        ReleaseTestCommand(
            "install-wheel",
            (str(python), "-m", "pip", "install", str(wheel)),
            base_env,
        ),
        ReleaseTestCommand(
            "fetch-suite",
            (
                localbench,
                "fetch-suite",
                "--accept-suite-terms",
                "--source",
                str(suite_source),
            ),
            base_env,
        ),
        ReleaseTestCommand("suite-inspect", (localbench, "suite", "inspect"), base_env),
        ReleaseTestCommand(
            "run-dry-run",
            (
                localbench,
                "run",
                "--suite",
                "core-text-v1",
                "--endpoint",
                endpoint,
                "--model",
                model,
                "--dry-run",
            ),
            base_env,
        ),
        ReleaseTestCommand(
            "run-smoke-2",
            (
                localbench,
                "run",
                "--suite",
                "core-text-v1",
                "--accept-suite-terms",
                "--endpoint",
                endpoint,
                "--model",
                model,
                "--out",
                str(work_dir / "my-run.json"),
                "--bench",
                "mmlu_pro",
                "--max-items",
                "2",
            ),
            base_env,
        ),
    )
    return ReleaseTestPlan(work_dir=work_dir, home=home, venv=venv, commands=commands)


def run_release_test(plan: ReleaseTestPlan) -> None:
    """Execute a prepared release-test plan in order."""
    plan.home.mkdir(parents=True, exist_ok=True)
    for command in plan.commands:
        subprocess.run(
            command.argv,
            env=dict(command.env),
            cwd=plan.work_dir,
            check=True,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the local empty-machine release harness."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m localbench.release_test")
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--suite-source", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)
    plan = release_test_plan(
        wheel=args.wheel,
        suite_source=args.suite_source,
        work_dir=args.work_dir,
        endpoint=args.endpoint,
        model=args.model,
    )
    run_release_test(plan)
    return 0


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def _venv_script(venv: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{name}{suffix}"


if __name__ == "__main__":
    raise SystemExit(main())
