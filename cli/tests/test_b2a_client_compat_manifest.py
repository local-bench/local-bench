from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_b2a_compatibility_manifest_pins_rc_and_live_wheels() -> None:
    manifest = json.loads((ROOT / "release" / "b2a-client-compat.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "localbench.b2a_client_compat.v1"
    assert manifest["clients"] == [
        {
            "role": "rc_n",
            "version": "0.3.3rc1",
            "filename": "local_bench_ai-0.3.3rc1-py3-none-any.whl",
            "sha256": "2cfc18250e096a81246f31b61762e1c0052ab00b24d29708a2fff84ba4ee794f",
            "source": "build:cli",
        },
        {
            "role": "live_n_minus_1",
            "version": "0.3.2",
            "filename": "local_bench_ai-0.3.2-py3-none-any.whl",
            "sha256": "cb1113fb3e1fb06f47f57fa8a6de286e1a0d9f89cf26e7df6cf00c70f366f1b3",
            "source": "pypi:local-bench-ai==0.3.2",
        },
    ]


def test_b2a_mutated_admission_is_rejected_by_both_pinned_clients() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "b2a_client_compat_gate.py"), "--mutate-admission"],
        cwd=ROOT, capture_output=True, text=True, timeout=240,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 1, combined
    rc_line = next(line for line in combined.splitlines() if line.startswith("rc_n "))
    previous_line = next(line for line in combined.splitlines() if line.startswith("live_n_minus_1 "))
    assert "result=0" not in rc_line
    assert "result=0" not in previous_line
