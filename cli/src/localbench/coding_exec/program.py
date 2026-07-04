"""Assemble a self-executing test program from a generation + the task's unit tests.

The program = generated code + the task's `unittest` TestCase + a trusted epilogue that
runs the tests and exits 0 (all pass) or 1 (any fail/error). It is run as a FRESH
subprocess per task by the in-container runner, so:
- the scorer parent never imports/executes the untrusted generation (uncorruptible), and
- the blast radius of a malicious/buggy generation is one task.

Honest limit (documented in the threat model): generation + test share the subprocess, so
a deliberately adversarial generation could fake its own task's pass. That is caught by
replication (independent accounts must converge) — we never claim a single run is "verified".
"""

from __future__ import annotations

_EPILOGUE = '''

if __name__ == "__main__":
    import sys as _sys
    import unittest as _unittest
    _suite = _unittest.TestLoader().loadTestsFromModule(_sys.modules["__main__"])
    if _suite.countTestCases() == 0:
        _sys.exit(2)  # no tests discovered -> not a pass (guards empty/malformed tests)
    _result = _unittest.TextTestRunner(verbosity=0).run(_suite)
    _sys.exit(0 if _result.wasSuccessful() else 1)
'''


def assemble_program(generated_code: str, test: str, entry_point: str) -> str:
    """Build the runnable per-task program: generation + task tests + trusted epilogue."""
    return (
        f"# entry_point: {entry_point}\n"
        f"{generated_code.rstrip()}\n\n\n"
        f"{test.rstrip()}\n"
        f"{_EPILOGUE}"
    )
