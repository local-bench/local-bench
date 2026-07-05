from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest

from localbench.coding_exec.ast_gate import check_ast_gate
from localbench.coding_exec.orchestrate import _assemble_tasks
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.runner import run_program

_TEST = (
    "import unittest\n"
    "class TestCases(unittest.TestCase):\n"
    "    def test_answer(self):\n"
    "        self.assertEqual(task_func(), 42)\n"
)

_BENIGN_SOURCE = {
    "id": "probe",
    "test": _TEST,
    "entry_point": "task_func",
}

ProbeLayer = Literal["ast_gate", "sentinel", "pass"]


@dataclass(frozen=True, slots=True)
class Probe:
    code: str
    passed: bool
    layer: ProbeLayer
    grading_integrity: str | None = None


_PROBES: dict[str, Probe] = {
    "control_correct": Probe(
        code="def task_func():\n    return 42\n",
        passed=True,
        layer="pass",
        grading_integrity="sentinel_ok",
    ),
    "control_wrong": Probe(
        code="def task_func():\n    return 0\n",
        passed=False,
        layer="sentinel",
        grading_integrity="counts_fail",
    ),
    "os_exit_before_tests": Probe(
        code="import os\nos._exit(0)\n\ndef task_func():\n    return 0\n",
        passed=False,
        layer="ast_gate",
    ),
    "sys_exit_before_tests": Probe(
        code="import sys\nsys.exit(0)\n\ndef task_func():\n    return 0\n",
        passed=False,
        layer="ast_gate",
    ),
    "atexit_os_exit": Probe(
        code=(
            "import atexit\n"
            "import os\n"
            "atexit.register(lambda: os._exit(0))\n\n"
            "def task_func():\n"
            "    return 0\n"
        ),
        passed=False,
        layer="ast_gate",
    ),
    "assertEqual_noop": Probe(
        code=(
            "import unittest\n"
            "unittest.TestCase.assertEqual = lambda self, first, second, msg=None: None\n\n"
            "def task_func():\n"
            "    return 0\n"
        ),
        passed=False,
        layer="ast_gate",
    ),
    "patch_wasSuccessful": Probe(
        code=(
            "import unittest\n"
            "unittest.result.TestResult.wasSuccessful = lambda self: True\n\n"
            "def task_func():\n"
            "    return 0\n"
        ),
        passed=False,
        layer="ast_gate",
    ),
    "redefine_testcases": Probe(
        code="class TestCases:\n    pass\n\n\ndef task_func():\n    return 0\n",
        passed=False,
        layer="sentinel",
        grading_integrity="counts_fail",
    ),
}


def _run_probe(probe: Probe) -> dict[str, object]:
    gate = check_ast_gate(probe.code)
    if not gate.accepted:
        return {
            "passed": False,
            "conformance_failure": "coding_ast_rejected",
            "ast_gate_failure": gate.failure,
        }
    return run_program(assemble_program(probe.code, _TEST, "task_func"), timeout=5.0)


@pytest.mark.parametrize("name", tuple(_PROBES))
def test_coding_exec_adversarial_probes_are_caught(name: str) -> None:
    probe = _PROBES[name]

    result = _run_probe(probe)

    assert result["passed"] is probe.passed
    if probe.layer == "ast_gate":
        assert result["conformance_failure"] == "coding_ast_rejected"
    if probe.grading_integrity is not None:
        assert result["grading_integrity"] == probe.grading_integrity


@pytest.mark.parametrize(
    ("program", "grading_integrity"),
    (
        ("import os\nos._exit(0)\n", "no_sentinel"),
        ("import sys\nsys.exit(0)\n", "no_sentinel"),
        ('print(\'<SENTINEL> {"run": 1, "fail": 0, "err": 0, "nonce": "wrong"}\')\n', "nonce_mismatch"),
        (assemble_program("def task_func():\n    return 0\n", _TEST, "task_func"), "counts_fail"),
    ),
)
def test_run_program_requires_a_valid_completion_sentinel(
    program: str,
    grading_integrity: str,
) -> None:
    result = run_program(program, timeout=5.0)

    assert result["passed"] is False
    assert result["grading_integrity"] == grading_integrity


def test_ast_rejected_generation_is_a_conformance_failure_not_a_sandbox_unscoreable() -> None:
    tasks, failures = _assemble_tasks(
        [_BENIGN_SOURCE],
        [{"id": "probe", "response_text": "import sys\nsys.exit(0)\n", "error": None}],
    )

    assert tasks == []
    assert failures == [
        {
            "id": "probe",
            "passed": False,
            "conformance_failure": "coding_ast_rejected",
            "ast_gate_failure": "forbidden_reference",
        }
    ]


@pytest.mark.parametrize(
    "code",
    (
        '"""Solve the task."""\n\n'
        "import math\n\n"
        "CONSTANT = 3\n\n"
        "def task_func(value):\n"
        "    return math.ceil(value) + CONSTANT\n",
        "from collections import Counter\n\n"
        "class Solver:\n"
        "    def solve(self, values):\n"
        "        return Counter(values).most_common(1)[0][0]\n\n"
        "def task_func(values):\n"
        "    return Solver().solve(values)\n",
        "from __future__ import annotations\n\n"
        "THRESHOLD: int = 10\n\n"
        "async def helper(value: int) -> int:\n"
        "    return value\n\n"
        "def task_func(value: int) -> bool:\n"
        "    return value > THRESHOLD\n",
        "import nltk\n\n"
        "nltk.download('stopwords')\n\n"
        "STOPWORDS = nltk.corpus.stopwords.words('english')\n\n"
        "def task_func(words):\n"
        "    return [word for word in words if word not in STOPWORDS]\n",
    ),
)
def test_ast_gate_accepts_representative_canonical_solution_shapes(code: str) -> None:
    assert check_ast_gate(code).accepted is True
