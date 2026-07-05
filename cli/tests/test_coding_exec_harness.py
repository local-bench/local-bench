from __future__ import annotations

import json
from pathlib import Path

import pytest

import localbench.coding_exec.score as score_module
from localbench.coding_exec import (
    assemble_program,
    extract_code,
    run_program,
    score_coding_exec,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GEN_OK = "def task_func(a, b):\n    return a + b"
_TEST = (
    "import unittest\n"
    "class TestCases(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(task_func(1, 2), 3)\n"
)


def test_extract_code_takes_last_python_fence() -> None:
    response = (
        "Let me reason about this.\n"
        "```python\ndef wrong():\n    pass\n```\n"
        "Actually, the final answer is:\n"
        "```python\ndef task_func():\n    return 42\n```\n"
    )
    assert extract_code(response) == "def task_func():\n    return 42"


def test_extract_code_falls_back_to_unlabeled_fence_and_handles_none() -> None:
    assert extract_code("```\nx = 1\n```") == "x = 1"
    assert extract_code("no code here at all") is None
    assert extract_code(None) is None
    assert extract_code("```python\n\n```") is None


def test_assemble_program_includes_generation_tests_and_trusted_epilogue() -> None:
    program = assemble_program(_GEN_OK, _TEST, "task_func")
    assert "def task_func(a, b):" in program
    assert "class TestCases(unittest.TestCase):" in program
    assert "wasSuccessful()" in program  # the trusted epilogue computes the verdict


def test_run_program_passes_a_correct_solution() -> None:
    result = run_program(assemble_program(_GEN_OK, _TEST, "task_func"), timeout=30.0)
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["timed_out"] is False


def test_run_program_fails_an_incorrect_solution() -> None:
    bad_test = _TEST.replace("task_func(1, 2), 3", "task_func(1, 2), 999")
    result = run_program(assemble_program(_GEN_OK, bad_test, "task_func"), timeout=30.0)
    assert result["passed"] is False
    assert result["exit_code"] == 1


def test_run_program_kills_a_runaway_on_timeout() -> None:
    result = run_program("while True:\n    pass\n", timeout=1.0)
    assert result["timed_out"] is True
    assert result["passed"] is False


def test_run_program_rejects_a_program_with_no_discovered_tests() -> None:
    # An empty/malformed test suite must NOT count as a pass.
    result = run_program(assemble_program("x = 1", "", "task_func"), timeout=30.0)
    assert result["passed"] is False
    assert result["exit_code"] == 2


def test_run_program_reports_the_subprocess_verdict_not_a_self_report() -> None:
    # Contract: the runner reports the subprocess exit code; it never executes the
    # generation in its own process. (Adversarial self-pass is handled by replication.)
    raised = run_program("raise SystemExit(1)\n", timeout=30.0)
    assert raised["passed"] is False
    clean = run_program("import sys\nsys.exit(0)\n", timeout=30.0)
    assert clean["passed"] is True


def test_score_coding_exec_aggregates_pass_rate() -> None:
    results = [
        {"id": "bcbh-001", "passed": True},
        {"id": "bcbh-002", "passed": False, "timed_out": True},
        {"id": "bcbh-003", "passed": False, "no_code": True},
        {"id": "bcbh-004", "passed": True},
    ]
    score = score_coding_exec(results)
    assert score["bench"] == "bigcodebench_hard"
    assert score["n"] == 4
    assert score["n_passed"] == 2
    assert score["n_timed_out"] == 1
    assert score["n_no_code"] == 1
    assert score["raw_accuracy"] == pytest.approx(0.5)
    assert score["chance_corrected"] == pytest.approx(0.5)  # chance 0 -> corrected == raw


def test_score_coding_exec_scores_only_sandbox_scoreable_items() -> None:
    results = [
        {"id": "bcbh-001", "passed": True},
        {"id": "bcbh-002", "passed": True},
        {"id": "bcbh-006", "passed": False, "timed_out": True, "no_code": True},
        {"id": "bcbh-007", "passed": False, "timed_out": True},
        {"id": "bcbh-014", "passed": False, "timed_out": True},
        {"id": "bcbh-035", "passed": False, "no_code": True},
        {"id": "bcbh-074", "passed": False, "timed_out": True},
        {"id": "bcbh-096", "passed": False},
        {"id": "bcbh-104", "passed": False, "no_code": True},
    ]

    score = score_coding_exec(results)

    assert score["n"] == 2
    assert score["n_passed"] == 2
    assert score["n_timed_out"] == 0
    assert score["n_no_code"] == 0
    assert score["n_unscoreable"] == 7
    assert score["raw_accuracy"] == pytest.approx(1.0)
    assert score["chance_corrected"] == pytest.approx(1.0)


def test_sandbox_unscoreable_bigcodebench_ids_exist_and_leave_141_scoreable_items() -> None:
    unscoreable = getattr(score_module, "SANDBOX_UNSCOREABLE_BCBH", frozenset())
    suite_path = _REPO_ROOT / "suite" / "v1" / "bigcodebench_hard.jsonl"
    item_ids = {
        str(json.loads(line)["id"])
        for line in suite_path.read_text(encoding="utf-8").splitlines()
        if line
    }

    assert unscoreable == frozenset(
        {
            "bcbh-006",
            "bcbh-007",
            "bcbh-014",
            "bcbh-035",
            "bcbh-074",
            "bcbh-096",
            "bcbh-104",
        },
    )
    assert unscoreable <= item_ids
    assert len(item_ids - unscoreable) == 141
