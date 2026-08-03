from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Final, cast

from localbench._types import JsonObject
from localbench.coding_exec import runner as runner_module
from localbench.coding_exec.sandbox import (
    OPT_IN_WARNING,
    SandboxLimits,
    docker_run_argv,
    preflight_sandbox_controls,
    probe_docker_env,
    run_sandboxed,
)

_IMAGE: Final = (
    "bigcodebench/bigcodebench-evaluate@sha256:"
    "a3cd34ec3840a49d6b7afb240f4bdd47c350bc5991043fd0a91773830f7cd405"
)
_PER_TASK_TIMEOUT: Final = 30
_CONTAINER_OVERHEAD_SECONDS: Final = 300


class CodingVerifierError(RuntimeError):
    pass


def execute_verifier_tasks(
    tasks: list[JsonObject],
    *,
    allow_untrusted_code: bool,
) -> tuple[list[JsonObject], str]:
    if not allow_untrusted_code:
        raise CodingVerifierError(f"{OPT_IN_WARNING} Refusing to continue without explicit consent.")
    limits = SandboxLimits()
    preflight = preflight_sandbox_controls(
        _IMAGE,
        probe_docker_env(),
        limits=limits,
    )
    if not preflight.ok:
        raise CodingVerifierError(
            "sandbox preflight failed: " + "; ".join(preflight.blockers)
        )
    bounded = replace(
        limits,
        wall_clock_seconds=_PER_TASK_TIMEOUT * len(tasks) + _CONTAINER_OVERHEAD_SECONDS,
    )
    runner_source = Path(runner_module.__file__).resolve().read_text(encoding="utf-8")
    argv = docker_run_argv(
        _IMAGE,
        ["python", "-c", runner_source, "-", str(_PER_TASK_TIMEOUT)],
        limits=bounded,
        runtime=preflight.runtime,
    )
    result = run_sandboxed(
        argv,
        limits=bounded,
        stdin_bytes=json.dumps(tasks).encode("utf-8"),
    )
    if result["timed_out"] or result["exit_code"] != 0:
        raise CodingVerifierError(
            f"sandbox container failed (exit={result['exit_code']}, timed_out={result['timed_out']}): "
            + str(result["stderr"] or result["stdout"])[:500]
        )
    try:
        raw_payload = cast(object, json.loads(result["stdout"]))
    except json.JSONDecodeError as error:
        raise CodingVerifierError("sandbox runner returned invalid JSON") from error
    if not isinstance(raw_payload, dict):
        raise CodingVerifierError("sandbox runner returned a non-object payload")
    payload = cast(JsonObject, raw_payload)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise CodingVerifierError("sandbox runner returned no results array")
    rows = [cast(JsonObject, row) for row in raw_results if isinstance(row, dict)]
    if len(rows) != len(tasks):
        raise CodingVerifierError("sandbox runner returned an incomplete results array")
    return rows, _IMAGE
