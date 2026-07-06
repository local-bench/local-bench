"""KNOWN-OPEN residual forgery vectors for the coding-exec grader (found 2026-07-07).

The 2026-07-06 invert-control redesign (test_coding_exec_forgery_fix.py) closed the trivial
``raise SystemExit(0)`` + cleartext-nonce exploit, but it did NOT close the sentinel-forgery
CLASS. Untrusted code sharing the grader's interpreter can still recover the driver's private
globals (the nonce + os.write + os) and forge a passing sentinel with the correct nonce, via at
least three independent, AST-gate-passing paths. Full analysis + blast radius:
docs/reports/coding-exec-framewalk-forgery-2026-07-07.md.

Each test below asserts the DESIRED end state (``passed is False`` — forgery rejected) and is
marked ``xfail(strict=True)`` because that state is NOT yet achieved: today these forge a pass.
This is a deliberate tripwire. When the sound out-of-process fix lands
(docs/reports/coding-exec-worker-marshalling-spec-2026-07-07.md) and a vector is genuinely
closed, its assertion will pass, the strict xfail will report XPASS-as-FAILURE, and whoever
landed the fix must remove that marker — so no change can silently claim "closed" without the
proof showing here. Do not delete these tests or soften them to non-strict to get green.

NOTE: these spawn real subprocesses that DO forge a pass against the current harness. That is
intentional (they are the regression target). They are contained exactly as production is:
coding never auto-ranks, and the ranked board ingests only maintainer-curated files.
"""

from __future__ import annotations

import pytest

from localbench.coding_exec.ast_gate import check_ast_gate
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.runner import run_program

# Any "pass" against this test can ONLY be forgery (the real assertion can never hold).
_FAILING_TEST = (
    "import unittest\n"
    "class TestCases(unittest.TestCase):\n"
    "    def test_it(self):\n"
    "        self.assertEqual(task_func(2), 999999)\n"
)

# The forged-sentinel + hard-exit tail (4-space indent = function body, AFTER the walk loop
# where `_g` was bound via break). `_g` is the recovered driver globals (holds _write/_nonce/_os).
_FORGE_TAIL = (
    '    _line = "<SENTINEL> " + _j.dumps('
    '{"err": 0, "fail": 0, "nonce": _g["_nonce"], "run": 1}, sort_keys=True) + "\\n"\n'
    '    _r = _g["_write"](1, _line.encode("utf-8"))\n'
    '    _z = _g["_os"]._exit(0)\n'
)

# E1 — sys._getframe(): walk f_back to the frame whose globals hold the nonce.
_E1_GETFRAME = (
    "import sys as _s\n"
    "import json as _j\n"
    "def _pwn():\n"
    "    _f = _s._getframe()\n"
    "    while _f is not None:\n"
    "        if '_nonce' in _f.f_globals:\n"
    "            _g = _f.f_globals\n"
    "            break\n"
    "        _f = _f.f_back\n"
    + _FORGE_TAIL +
    "_z = _pwn()\n"
    "def task_func(x):\n"
    "    return -1\n"
)

# E2 — traceback frame (no sys._getframe; bypasses a sys.addaudithook lockdown).
_E2_TRACEBACK = (
    "import sys as _s\n"
    "import json as _j\n"
    "def _pwn():\n"
    "    try:\n"
    "        raise RuntimeError('x')\n"
    "    except RuntimeError:\n"
    "        _f = _s.exc_info()[2].tb_frame\n"
    "    while _f is not None:\n"
    "        if '_nonce' in _f.f_globals:\n"
    "            _g = _f.f_globals\n"
    "            break\n"
    "        _f = _f.f_back\n"
    + _FORGE_TAIL +
    "_z = _pwn()\n"
    "def task_func(x):\n"
    "    return -1\n"
)

# E3 — gc walk: find the displaced real __main__ module by its private attrs; recover os from it.
_E3_GCWALK = (
    "import gc as _gc\n"
    "import json as _j\n"
    "def _pwn():\n"
    "    for _m in _gc.get_objects():\n"
    "        if type(_m).__name__ == 'module' and hasattr(_m, '_nonce') and hasattr(_m, '_write') and hasattr(_m, '_os'):\n"
    "            _line = '<SENTINEL> ' + _j.dumps("
    "{'err': 0, 'fail': 0, 'nonce': _m._nonce, 'run': 1}, sort_keys=True) + '\\n'\n"
    "            _r = _m._write(1, _line.encode('utf-8'))\n"
    "            _z = _m._os._exit(0)\n"
    "_z = _pwn()\n"
    "def task_func(x):\n"
    "    return -1\n"
)

_RESIDUAL_VECTORS: dict[str, str] = {
    "E1_getframe_walk": _E1_GETFRAME,
    "E2_traceback_frame_walk": _E2_TRACEBACK,
    "E3_gc_object_walk": _E3_GCWALK,
}


def _verdict(code: str) -> dict:
    gate = check_ast_gate(code)
    if not gate.accepted:
        return {"passed": False, "gated": True, "gate_failure": gate.failure, "gate_detail": gate.detail}
    return run_program(assemble_program(code, _FAILING_TEST, "task_func"), timeout=20.0)


@pytest.mark.parametrize("name", tuple(_RESIDUAL_VECTORS))
@pytest.mark.xfail(
    strict=True,
    reason="KNOWN-OPEN: in-process nonce recovery forges a pass; sound fix is out-of-process "
    "value-marshalling (coding-exec-worker-marshalling-spec-2026-07-07.md). Remove this marker "
    "for a vector only when it genuinely resolves to passed=False.",
)
def test_residual_forgery_vectors_should_be_rejected(name: str) -> None:
    result = _verdict(_RESIDUAL_VECTORS[name])
    assert result["passed"] is False, f"{name} still forges a passing verdict: {result}"


def test_all_three_vectors_pass_the_ast_gate() -> None:
    # Not xfail: documents that the static gate does NOT stop these (they are admitted, then
    # forge at runtime). If the gate is later tightened to reject one, update this accordingly.
    for name, code in _RESIDUAL_VECTORS.items():
        assert check_ast_gate(code).accepted is True, f"{name} unexpectedly gate-blocked"
