"""Regression tests for the P1 coding-exec sentinel-forgery fix (2026-07-06, task #42).

Each case is a distinct way untrusted model-generated code tried (or could try) to force a
passing verdict without the unit tests passing. Every one must resolve to ``passed is False``.
The invert-control driver (program.py) plus the tightened AST gate (ast_gate.py) close the
whole simple-forgery class; the honest control confirms the harness still passes real code.

See docs/reports/coding-exec-groundtruth-and-probes-2026-07-05.md and
scratchpad exploit_sentinel_forgery.py for the originally demonstrated exploit.
"""

from __future__ import annotations

import pytest

from localbench.coding_exec.ast_gate import check_ast_gate
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.runner import run_program

# A test that genuinely FAILS if it runs, so any "pass" can ONLY be forgery.
_FAILING_TEST = (
    "import unittest\n"
    "class TestCases(unittest.TestCase):\n"
    "    def test_it(self):\n"
    "        self.assertEqual(task_func(), 999999)\n"
)


def _verdict(code: str) -> dict:
    """Mirror the pipeline: AST-gate the generation, then (if admitted) execute it."""
    gate = check_ast_gate(code)
    if not gate.accepted:
        return {"passed": False, "gated": True, "gate_failure": gate.failure}
    return run_program(assemble_program(code, _FAILING_TEST, "task_func"), timeout=15.0)


# The exact demonstrated exploit: read the nonce from __file__, print a forged passing
# sentinel, then raise SystemExit(0) from a helper invoked by a legal top-level assignment.
_DEMONSTRATED_EXPLOIT = (
    "import re as _re\n"
    "def _pwn():\n"
    "    _src = open(__file__, encoding='utf-8').read()\n"
    "    _n = _src.rsplit('_nonce = \"', 1)[1].split('\"', 1)[0]\n"
    "    print('<SENTINEL> {\"err\": 0, \"fail\": 0, \"nonce\": \"' + _n + '\", \"run\": 1}', flush=True)\n"
    "    raise SystemExit(0)\n"
    "_z = _pwn()\n"
    "def task_func():\n"
    "    return 0\n"
)

_FORGERY_VECTORS: dict[str, str] = {
    "demonstrated_systemexit_from_helper": _DEMONSTRATED_EXPLOIT,
    "raise_systemexit_top_level": (
        "raise SystemExit(0)\n\ndef task_func():\n    return 0\n"
    ),
    "builtin_exit_from_helper": (
        "def _p():\n    exit(0)\n_z = _p()\n\ndef task_func():\n    return 0\n"
    ),
    "builtin_quit_from_helper": (
        "def _p():\n    quit()\n_z = _p()\n\ndef task_func():\n    return 0\n"
    ),
    "os_exit_obfuscated_no_valid_sentinel": (
        # getattr-obfuscated os._exit(0) slips the gate's literal os._exit check, forces exit 0,
        # but the driver never emitted a nonce-valid sentinel -> no forged pass.
        "import os as _o\n"
        "def _p():\n"
        "    getattr(_o, '_' + 'exit')(0)\n"
        "_z = _p()\n\n"
        "def task_func():\n"
        "    return 0\n"
    ),
    "patch_wasSuccessful_in_helper": (
        "import unittest as _u\n"
        "def _p():\n"
        "    _u.TestResult.wasSuccessful = lambda self: True\n"
        "_z = _p()\n\n"
        "def task_func():\n"
        "    return 0\n"
    ),
    "patch_assertEqual_in_helper": (
        "import unittest as _u\n"
        "def _p():\n"
        "    _u.TestCase.assertEqual = lambda self, a, b, msg=None: None\n"
        "_z = _p()\n\n"
        "def task_func():\n"
        "    return 0\n"
    ),
    "forged_sentinel_no_nonce": (
        "def _p():\n"
        "    print('<SENTINEL> {\"err\": 0, \"fail\": 0, \"nonce\": \"guess\", \"run\": 1}')\n"
        "_z = _p()\n\n"
        "def task_func():\n"
        "    return 0\n"
    ),
    "read_env_nonce_is_deleted_before_untrusted_runs": (
        # The driver pops the nonce env var before executing untrusted code, so it is gone.
        "import os as _o\n"
        "def _p():\n"
        "    _n = _o.environ.get('LOCALBENCH_SENTINEL_NONCE', 'MISSING')\n"
        "    print('<SENTINEL> {\"err\": 0, \"fail\": 0, \"nonce\": \"' + _n + '\", \"run\": 1}')\n"
        "_z = _p()\n\n"
        "def task_func():\n"
        "    return 0\n"
    ),
}


@pytest.mark.parametrize("name", tuple(_FORGERY_VECTORS))
def test_forgery_vectors_never_pass(name: str) -> None:
    result = _verdict(_FORGERY_VECTORS[name])
    assert result["passed"] is False, f"{name} forged a passing verdict: {result}"


def test_demonstrated_exploit_is_gate_rejected() -> None:
    # Belt: the tightened gate rejects the demonstrated exploit outright (SystemExit reference).
    gate = check_ast_gate(_DEMONSTRATED_EXPLOIT)
    assert gate.accepted is False
    assert gate.failure == "forbidden_reference"


def test_honest_correct_solution_still_passes() -> None:
    passing_test = _FAILING_TEST.replace("999999", "0")
    result = run_program(assemble_program("def task_func():\n    return 0\n", passing_test, "task_func"), timeout=15.0)
    assert result["passed"] is True
    assert result["grading_integrity"] == "sentinel_ok"


def test_honest_failing_solution_reports_counts_fail() -> None:
    result = run_program(assemble_program("def task_func():\n    return 0\n", _FAILING_TEST, "task_func"), timeout=15.0)
    assert result["passed"] is False
    assert result["grading_integrity"] == "counts_fail"


def test_program_and_runner_agree_on_the_nonce_env_var() -> None:
    from localbench.coding_exec import program, runner

    assert program.NONCE_ENV_VAR == runner.NONCE_ENV_VAR
