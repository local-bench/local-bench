from __future__ import annotations

import json
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
            "sha256": "011187e234cb0d2856d48f4640cb5da665b039aee15c8892e13fe7f5350dca72",
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
