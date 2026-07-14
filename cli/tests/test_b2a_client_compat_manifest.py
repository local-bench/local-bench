from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_wheel_build_backend_is_exactly_pinned() -> None:
    pyproject = tomllib.loads((ROOT / "cli" / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"]["requires"] == [
        "setuptools==80.9.0",
        "wheel==0.45.1",
    ]


def test_b2a_compatibility_manifest_pins_rc_and_live_wheels() -> None:
    manifest = json.loads((ROOT / "release" / "b2a-client-compat.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "localbench.b2a_client_compat.v1"
    assert manifest["clients"] == [
        {
            "role": "rc_n",
            "version": "0.3.3rc1",
            "filename": "local_bench_ai-0.3.3rc1-py3-none-any.whl",
            "sha256": "51467bee8cbb3cc47e0794b7e94eb3ba8b066f6297a9e4dc660e7dd8db55624a",
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


def test_rc_wheel_pin_matches_clean_committed_tree_rebuild() -> None:
    manifest = json.loads((ROOT / "release" / "b2a-client-compat.json").read_text(encoding="utf-8"))
    provenance = manifest["rc_build"]
    assert provenance == {
        "source_commit": "6cc70d59df240940119b0ebc77b1a744bedba3dd",
        "source_tree": "189348fa509c060f629ee6b8c9d8fc6342358f1b",
        "source_date_epoch": 1783814400,
        "tool_versions": {
            "python": "CPython 3.14.2",
            "uv": "0.9.22",
            "setuptools": "80.9.0",
            "wheel": "0.45.1",
        },
        "command": [
            "git archive --format=zip 6cc70d59df240940119b0ebc77b1a744bedba3dd cli",
            "replace project version 0.3.1 with 0.3.3rc1 in extracted cli/pyproject.toml",
            "SOURCE_DATE_EPOCH=1783814400 uv build --offline --wheel --no-build-logs --python CPython-3.14.2 <archive>/cli --out-dir <dist>",
        ],
        "wheel_sha256": "51467bee8cbb3cc47e0794b7e94eb3ba8b066f6297a9e4dc660e7dd8db55624a",
    }
    assert provenance["wheel_sha256"] == manifest["clients"][0]["sha256"]
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "b2a_client_compat_gate.py"), "--verify-rc-rebuild"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "UV_OFFLINE": "1", "UV_PYTHON_DOWNLOADS": "never"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "rc_rebuild local_bench_ai-0.3.3rc1-py3-none-any.whl sha256=51467bee" in combined


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
