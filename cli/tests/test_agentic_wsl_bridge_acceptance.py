from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))
sys.path.insert(0, str(_REPO / "cli" / "tools"))


def _appworld_available() -> bool:
    return importlib.util.find_spec("appworld") is not None


def _bwrap_available() -> bool:
    from localbench.scoring.agentic_exec.sandbox import resolve_bwrap

    return resolve_bwrap() is not None


_SKIP_REASON = (
    "requires the WSL appworld venv + bubblewrap; run from Windows through wsl bash"
)

pytestmark = [
    pytest.mark.wsl,
    pytest.mark.skipif(
        sys.platform != "linux"
        or not (_appworld_available() and os.environ.get("APPWORLD_ROOT") and _bwrap_available()),
        reason=_SKIP_REASON,
    ),
]


def _wsl_proxy_config():
    from localbench.scoring.agentic_exec.wsl_bridge import WslWorkerConfig

    return WslWorkerConfig(
        repo_root_wsl_path=str(_REPO),
        venv_python=sys.executable,
        appworld_root="/home/michael/appworld-data",
        log_dir=_REPO / "cli" / ".pytest-wsl-logs",
        worker_env={"PYTHONPATH": str(_REPO / "cli" / "src")},
        op_timeout_s=30.0,
        open_task_timeout_s=180.0,
    )


def test_worker_hello_identity_sanity() -> None:
    # Given / When: the worker identity is collected in the WSL appworld venv.
    from localbench.scoring.agentic_exec.wsl_worker import collect_identity

    identity = collect_identity()

    # Then: the root is native WSL storage and the sandbox dependencies are visible.
    assert identity["appworld_root"] == "/home/michael/appworld-data"
    assert identity["appworld_root_under_mnt"] is False
    assert identity["bwrap_path"]
    assert identity["appworld_version"]
    assert identity["localbench_distribution_version"] == "0.3.1"
    assert len(identity["worker_content_sha256"]) == 64
    assert identity["worker_module_sha256"]


def test_proxy_round_trip_on_one_real_task_from_wsl_side() -> None:
    # Given: the proxy configured to launch the worker through WSL's local Python command path.
    from localbench.scoring.agentic_exec.wsl_bridge import WslSandboxProxy

    # When: opening a real task through the proxy and running one harmless block.
    with WslSandboxProxy("fac291d_1", _wsl_proxy_config()) as sandbox:
        obs = sandbox.run_block("print('proxy-ok')")

    # Then: the AppWorld sandbox executed through the B1' proxy surface.
    assert "proxy-ok" in obs.stdout
    assert obs.error is None


def test_acceptance_gates_run_through_proxy_path() -> None:
    # Given: the B1' proxy path and the existing canary/scripted-solve helpers.
    import appworld_canary_suite as base
    import appworld_canary_suite_sandboxed as sandboxed
    import appworld_scripted_solve_sandboxed as solver
    from localbench.scoring.agentic_exec.wsl_bridge import WslSandboxProxy

    config = _wsl_proxy_config()

    # When: the 55 canaries are driven through run_block from the proxy side.
    sec = base.load_secrets()
    canaries = base.build_canaries(sec)
    results: list[base.Result] = []
    with WslSandboxProxy(base.PRIMARY_TASK, config) as sandbox:
        for canary in canaries:
            obs = sandbox.run_block(canary.code)
            out = obs.stdout
            if obs.error:
                out = (out + "\nTraceback (most recent call last)\n" + obs.error).strip()
            results.append(sandboxed._classify_sandboxed(out, canary, sec))

    # Then: the security gate remains 55/55 blocked through the proxy.
    assert len(results) == 55
    assert not [r for r in results if r.verdict == "SUCCEEDED"]
    assert not [r for r in results if r.verdict == "ERROR"]

    # When: two scripted utility solves run through the same proxy surface.
    verdicts = {}
    for task_id, solve in (("fac291d_1", solver.solve_fac291d), ("50e1ac9_1", solver.solve_50e1ac9)):
        with WslSandboxProxy(task_id, config) as sandbox:
            _answer, verdict = solve(sandbox)
        verdicts[task_id] = verdict

    # Then: both known dev tasks still solve through the proxy.
    assert sum(1 for verdict in verdicts.values() if verdict.success) == 2
    assert all(not verdict.collateral_damage for verdict in verdicts.values())


def test_parent_death_cleanup_leaves_no_env_host_or_bwrap() -> None:
    # Given: a proxy worker killed mid-task.
    from localbench.scoring.agentic_exec.wsl_bridge import WslSandboxProxy

    proxy = WslSandboxProxy("fac291d_1", _wsl_proxy_config())
    proxy.__enter__()

    # When: the parent worker is killed.
    proxy.force_kill()

    # Then: no env_host or bwrap runner process remains in WSL.
    result = subprocess.run(
        ["pgrep", "-af", "localbench.scoring.agentic_exec.env_host|bwrap"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert "localbench.scoring.agentic_exec.env_host" not in result.stdout
    assert "bwrap" not in result.stdout
