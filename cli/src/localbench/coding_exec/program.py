"""Assemble generated code, unit tests, and the trusted completion epilogue."""

from __future__ import annotations

from typing import Final

SENTINEL_SCHEME_REV: Final = "bigcodebench-unittest-sentinel-v1"
NONCE_PLACEHOLDER: Final = "__LOCALBENCH_SENTINEL_NONCE__"

_EPILOGUE = '''

if __name__ == "__main__":
    import json as _json
    import sys as _sys
    import unittest as _unittest
    _nonce = "__LOCALBENCH_SENTINEL_NONCE__"
    _suite = _unittest.TestLoader().loadTestsFromModule(_sys.modules["__main__"])
    if _suite.countTestCases() == 0:
        _sys.exit(2)  # no tests discovered -> not a pass (guards empty/malformed tests)
    _result = _unittest.TextTestRunner(verbosity=0).run(_suite)
    _failures = len(_result.failures)
    _errors = len(_result.errors)
    print(
        "<SENTINEL> "
        + _json.dumps(
            {
                "run": _result.testsRun,
                "fail": _failures,
                "err": _errors,
                "nonce": _nonce,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    _sys.exit(0 if _result.testsRun > 0 and _failures == 0 and _errors == 0 else 1)
'''


def assemble_program(generated_code: str, test: str, entry_point: str) -> str:
    """Build the runnable per-task program: generation + task tests + trusted epilogue."""
    return (
        f"# entry_point: {entry_point}\n"
        f"{generated_code.rstrip()}\n\n\n"
        f"{test.rstrip()}\n"
        f"{_EPILOGUE}"
    )
