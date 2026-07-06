"""Assemble generated code + tests into a program graded by a TRUSTED driver.

Security model (2026-07-06 invert-control redesign — closes the P1 sentinel-forgery vector
demonstrated in docs/reports/coding-exec-groundtruth-and-probes-2026-07-05.md):

The untrusted model-generated code and the (trusted) BigCodeBench unit test are carried into
the program as base64 DATA, not as executable top-level source. A trusted DRIVER is
``__main__`` and runs FIRST. Before any untrusted code can run it:

  * captures the grading tools it needs (os.write, unittest loader/runner and the
    result-recording methods) into private references;
  * reads the per-task nonce out of band (an env var, see runner.py) and DELETES it, so
    untrusted code cannot read it and forge a passing sentinel;
  * executes the untrusted solution + test inside an isolated module namespace wrapped in
    ``try/except BaseException`` — a ``SystemExit`` (or any exception) raised during untrusted
    top-level execution is scored as a FAILURE, never a pass, so the verdict can no longer be
    skipped by exiting the process early;
  * runs the tests with a PRIVATE ``TestResult`` subclass the untrusted code has no reference
    to (robust against monkeypatching ``unittest.TestResult`` on the base class), and
    identity-checks the grading tools before and after the run;
  * emits the completion sentinel through the pre-captured ``os.write`` and terminates with
    ``os._exit`` so no untrusted ``atexit``/``__del__``/thread can run after the verdict.

Residual (documented, not closed here): sophisticated in-process attacks — patch-then-restore
of a specific assert method from *inside* ``task_func``, or frame/gc walking to recover the
nonce — remain theoretically possible because gen and tests share an interpreter. These are
far harder than the trivial one-liner this redesign removes, and are further contained by the
hardened container, by community coding scores never auto-ranking, and by maintainer review
before any community coding row is promoted. See runner.py for nonce delivery + verdict
parsing and the AST gate (ast_gate.py) for the defense-in-depth policy on the untrusted code.
"""

from __future__ import annotations

import base64
from typing import Final

SENTINEL_SCHEME_REV: Final = "bigcodebench-invert-control-sentinel-v2"
NONCE_ENV_VAR: Final = "LOCALBENCH_SENTINEL_NONCE"

# The trusted driver. Tokens __NONCE_ENV__/__SOLUTION_B64__/__TEST_B64__ are substituted by
# assemble_program (plain str.replace so literal ``{``/``}`` in the body need no escaping).
_DRIVER = '''\
import base64 as _b64
import json as _json
import os as _os
import types as _types
import unittest as _unittest

# --- capture grading tools + nonce BEFORE any untrusted code can run ---
_nonce = _os.environ.pop("__NONCE_ENV__", None)
_write = _os.write
_TestLoader = _unittest.TestLoader
_TextTestRunner = _unittest.TextTestRunner
_loadTestsFromModule = _unittest.TestLoader.loadTestsFromModule
_orig_addError = _unittest.TestResult.addError
_orig_addFailure = _unittest.TestResult.addFailure
_orig_addSuccess = _unittest.TestResult.addSuccess
_orig_wasSuccessful = _unittest.TestResult.wasSuccessful
_orig_TestCase_run = _unittest.TestCase.run
# Common assert methods: a no-op patch from inside task_func would fake passes; identity-check
# them after the run (patch-then-restore within task_func is the documented residual).
_ASSERTS = (
    "assertEqual", "assertNotEqual", "assertTrue", "assertFalse", "assertIs", "assertIsNot",
    "assertIsNone", "assertIsNotNone", "assertIn", "assertNotIn", "assertRaises", "assertRaisesRegex",
    "assertAlmostEqual", "assertNotAlmostEqual", "assertGreater", "assertGreaterEqual", "assertLess",
    "assertLessEqual", "assertListEqual", "assertDictEqual", "assertSetEqual", "assertTupleEqual",
    "assertCountEqual", "assertSequenceEqual", "assertMultiLineEqual", "assertRegex", "fail",
)
_orig_asserts = {_name: getattr(_unittest.TestCase, _name, None) for _name in _ASSERTS}

_solution = _b64.b64decode("__SOLUTION_B64__").decode("utf-8")
_test = _b64.b64decode("__TEST_B64__").decode("utf-8")


def _emit(run, fail, err):
    line = "<SENTINEL> " + _json.dumps(
        {"err": err, "fail": fail, "nonce": _nonce, "run": run}, sort_keys=True
    ) + "\\n"
    _write(1, line.encode("utf-8"))


def _fail_exit(run, fail, err, code):
    _emit(run, fail, err)
    _os._exit(code)


def _grading_tools_intact():
    if (
        _unittest.TestResult.addError is not _orig_addError
        or _unittest.TestResult.addFailure is not _orig_addFailure
        or _unittest.TestResult.addSuccess is not _orig_addSuccess
        or _unittest.TestResult.wasSuccessful is not _orig_wasSuccessful
        or _unittest.TestCase.run is not _orig_TestCase_run
        or _unittest.TestLoader.loadTestsFromModule is not _loadTestsFromModule
    ):
        return False
    for _name, _ref in _orig_asserts.items():
        if getattr(_unittest.TestCase, _name, None) is not _ref:
            return False
    return True


# Private result: overrides the record hooks so a monkeypatch of unittest.TestResult on the
# BASE class does not affect our counting (untrusted code has no reference to this subclass).
# Semantics mirror the previous sentinel epilogue EXACTLY: pass iff run>0 and no failures or
# errors; skips / expected-failures / unexpected-successes do not count as failures.
class _Result(_unittest.TestResult):
    def __init__(self):
        _unittest.TestResult.__init__(self)
        self.run_count = 0
        self.bad = 0

    def startTest(self, test):
        self.run_count += 1

    def stopTest(self, test):
        pass

    def addSuccess(self, test):
        pass

    def addError(self, test, err):
        self.bad += 1

    def addFailure(self, test, err):
        self.bad += 1

    def addSubTest(self, test, subtest, outcome):
        if outcome is not None:
            self.bad += 1

    def addSkip(self, test, reason):
        pass

    def addExpectedFailure(self, test, err):
        pass

    def addUnexpectedSuccess(self, test):
        pass


# --- execute untrusted solution + trusted test in an isolated namespace ---
_mod = _types.ModuleType("submission")
_mod.__dict__["__name__"] = "submission"
try:
    exec(compile(_solution, "<solution>", "exec"), _mod.__dict__)
    exec(compile(_test, "<test>", "exec"), _mod.__dict__)
except BaseException:
    _fail_exit(0, 0, 1, 1)  # untrusted top-level execution failed -> not a pass

if not _grading_tools_intact():
    _fail_exit(0, 0, 1, 1)  # import-time monkeypatch of a grading tool -> not a pass

# --- load + run the tests with the pre-captured loader/runner + private result ---
try:
    _suite = _loadTestsFromModule(_TestLoader(), _mod)
except BaseException:
    _fail_exit(0, 0, 1, 1)

if _suite.countTestCases() == 0:
    _fail_exit(0, 0, 0, 2)  # no tests discovered -> not a pass

_result = _Result()
try:
    _suite(_result)  # TestSuite.__call__ -> run; drives each test against our private result
except BaseException:
    _fail_exit(0, 0, 1, 1)

# --- re-check grading tools AFTER the run (a test called untrusted task_func) ---
if not _grading_tools_intact():
    _fail_exit(_result.run_count or 1, _result.bad or 1, 1, 1)

_run = _result.run_count
_fail = _result.bad
_emit(_run, _fail, 0)
_os._exit(0 if _run > 0 and _fail == 0 else 1)
'''


def assemble_program(generated_code: str, test: str, entry_point: str) -> str:
    """Build the runnable per-task program: a trusted driver that grades untrusted code.

    ``generated_code`` (untrusted) and ``test`` (trusted) are embedded as base64 data; the
    driver decodes and executes them under supervision. The signature and the leading
    ``# entry_point`` marker are unchanged from the previous (sentinel-epilogue) recipe so all
    callers and the ``assembled_program_sha256`` provenance field keep working.
    """
    solution_b64 = base64.b64encode(generated_code.rstrip().encode("utf-8")).decode("ascii")
    test_b64 = base64.b64encode(test.rstrip().encode("utf-8")).decode("ascii")
    driver = (
        _DRIVER.replace("__NONCE_ENV__", NONCE_ENV_VAR)
        .replace("__SOLUTION_B64__", solution_b64)
        .replace("__TEST_B64__", test_b64)
    )
    return f"# entry_point: {entry_point}\n{driver}"
