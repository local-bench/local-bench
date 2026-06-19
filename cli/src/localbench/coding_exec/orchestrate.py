"""`localbench code` orchestration: generate -> assemble -> sandbox-execute -> score.

Reuses the standard generation path (`run_benchmark`) to drive the user's endpoint over
the frozen BigCodeBench-Hard prompts, then extracts each generation, assembles a
self-executing test program, runs all of them in ONE hardened sandbox container (each task
in its own subprocess inside it), and scores the pass rate as the coding-exec axis.

Both the generation transport and the sandbox runner are injectable, so the whole flow is
unit-tested without a model endpoint or Docker. The real run is GPU + Docker gated.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, TypedDict

import httpx

from localbench._requests import utc_now
from localbench._suite import item_hashes, read_json_object, render_benches, suite_version
from localbench._types import JsonObject
from localbench.coding_exec import runner as runner_module
from localbench.coding_exec.extract import extract_code
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.sandbox import (
    MANDATORY_SECURITY_FLAGS,
    OPT_IN_WARNING,
    DockerEnv,
    SandboxLimits,
    docker_run_argv,
    preflight_checks,
    probe_docker_env,
    run_sandboxed,
)
from localbench.coding_exec.sandbox import Runner as SandboxRunner
from localbench.coding_exec.score import BENCH, CodingExecScore, score_coding_exec
from localbench.providers import ReasoningEffort, provider_for_name
from localbench.runner import run_benchmark, write_json

SCHEMA: Final = "localbench-coding-exec-v1"
# bigcode's evaluation image; SHOULD be digest-pinned (repo@sha256:...) before a real run.
DEFAULT_IMAGE: Final = "bigcodebench/bigcodebench-evaluate:latest"
_CONTAINER_OVERHEAD_SECONDS: Final = 300


class CodingExecError(RuntimeError):
    """Raised when the coding-exec run cannot be set up or the sandbox infra fails."""


@dataclass(frozen=True, slots=True)
class CodingExecConfig:
    endpoint: str
    model: str
    suite_dir: Path
    image: str = DEFAULT_IMAGE
    tier: str = "standard"
    concurrency: int = 4
    out: Path | None = None
    api_key: str | None = None
    max_items: int | None = None
    provider: str = "local"
    reasoning_effort: ReasoningEffort | None = None
    lane: str = "capped-thinking"
    per_task_timeout: int = 30
    limits: SandboxLimits = SandboxLimits()
    runtime: str | None = None
    allow_unsafe_sandbox: bool = False  # explicit override for the rootful-bare-Linux fail-closed gate


class CodingExecRun(TypedDict):
    schema: str
    manifest: JsonObject
    score: CodingExecScore
    results: list[JsonObject]
    warnings: list[str]
    output_path: str


async def run_coding_exec(
    config: CodingExecConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    sandbox_runner: SandboxRunner | None = None,
    docker_env: DockerEnv | None = None,
) -> CodingExecRun:
    suite = read_json_object(config.suite_dir / "suite.json")
    warnings: list[str] = []

    # SECURITY GATE (fail fast, before the generation pass): refuse to execute untrusted
    # model code unless the host has a sufficient sandbox boundary. `docker_env` is injected
    # in tests; a real run probes the host. preflight may auto-select gVisor as the runtime.
    env = docker_env if docker_env is not None else probe_docker_env()
    preflight = preflight_checks(env, allow_unsafe=config.allow_unsafe_sandbox)
    warnings.extend(f"sandbox: {note}" for note in preflight.warnings)
    if not preflight.ok:
        raise CodingExecError(
            "sandbox preflight failed — refusing to run model-generated code: "
            + "; ".join(preflight.blockers)
            + " (override with allow_unsafe_sandbox if you accept the risk)"
        )
    config = replace(config, runtime=config.runtime or preflight.runtime)

    rendered = render_benches(BENCH, config.tier, config.max_items, config.suite_dir, suite, warnings)
    if not rendered:
        raise CodingExecError(f"{BENCH} not renderable from {config.suite_dir} (warnings: {warnings})")
    bench = rendered[0]

    started_at = utc_now()
    started_perf = time.perf_counter()
    record = await run_benchmark(
        base_url=config.endpoint,
        model=config.model,
        items=bench.benchmark_items,
        api_key=config.api_key,
        concurrency=config.concurrency,
        transport=transport,
        provider=provider_for_name(config.provider),
        lane=config.lane,  # type: ignore[arg-type]
        effort=config.reasoning_effort,
    )

    tasks, results = _assemble_tasks(bench.source_items, record["results"])
    if tasks:
        results.extend(_execute(tasks, config, sandbox_runner))
    results.sort(key=lambda result: str(result["id"]))
    score = score_coding_exec(results)
    wall = time.perf_counter() - started_perf

    output_path = config.out or Path("runs") / f"{_safe(config.model)}_coding-exec.json"
    run: CodingExecRun = {
        "schema": SCHEMA,
        "manifest": _manifest(config, suite, started_at, wall, score),
        "score": score,
        "results": results,
        "warnings": warnings,
        "output_path": str(output_path),
    }
    write_json(run, output_path)
    return run


def _assemble_tasks(
    source_items: list,
    generation_results: list,
) -> tuple[list[JsonObject], list[JsonObject]]:
    """Split generations into runnable tasks and immediate no-code/error failures."""
    tasks: list[JsonObject] = []
    failures: list[JsonObject] = []
    for source_item, result in zip(source_items, generation_results, strict=True):
        item_id = str(result["id"])
        if result.get("error") is not None:
            failures.append({"id": item_id, "passed": False, "error": str(result["error"])})
            continue
        code = extract_code(result.get("response_text"))
        if code is None:
            failures.append({"id": item_id, "passed": False, "no_code": True})
            continue
        program = assemble_program(code, str(source_item["test"]), str(source_item["entry_point"]))
        tasks.append({"id": item_id, "program": program})
    return tasks, failures


def _execute(
    tasks: list[JsonObject],
    config: CodingExecConfig,
    sandbox_runner: SandboxRunner | None,
) -> list[JsonObject]:
    runner_path = Path(runner_module.__file__).resolve()
    container_seconds = config.per_task_timeout * len(tasks) + _CONTAINER_OVERHEAD_SECONDS
    limits = replace(config.limits, wall_clock_seconds=container_seconds)
    with tempfile.TemporaryDirectory() as work:
        tasks_path = Path(work) / "tasks.json"
        tasks_path.write_text(json.dumps(tasks), encoding="utf-8")
        argv = docker_run_argv(
            config.image,
            ["python", "/work/runner.py", "/work/tasks.json", str(config.per_task_timeout)],
            limits=limits,
            read_only_mounts=[
                (str(runner_path), "/work/runner.py"),
                (str(tasks_path), "/work/tasks.json"),
            ],
            runtime=config.runtime,
        )
        result = run_sandboxed(argv, limits=limits, runner=sandbox_runner)
    if result["timed_out"] or result["exit_code"] != 0:
        raise CodingExecError(
            f"sandbox container failed (exit={result['exit_code']}, timed_out={result['timed_out']}): "
            f"{result['stderr'][:500] or result['stdout'][:500]}"
        )
    payload = json.loads(result["stdout"])
    parsed = payload.get("results")
    if not isinstance(parsed, list):
        raise CodingExecError("sandbox runner returned no results array")
    return [dict(entry) for entry in parsed]


def _manifest(
    config: CodingExecConfig,
    suite: JsonObject,
    started_at: str,
    wall: float,
    score: CodingExecScore,
) -> JsonObject:
    return {
        "lane": "exec",
        "schema_note": "coding-exec axis: model-generated code run in a hardened opt-in Docker sandbox",
        "image": config.image,
        "image_digest_pinned": "@sha256:" in config.image,
        "runtime": config.runtime,
        "allow_unsafe_sandbox": config.allow_unsafe_sandbox,
        "model": config.model,
        "suite_version": suite_version(suite),
        "item_set_hashes": item_hashes(config.suite_dir, [f"{BENCH}.jsonl"]),
        "sandbox_hardening": [" ".join(flag) for flag in MANDATORY_SECURITY_FLAGS],
        "per_task_timeout_seconds": config.per_task_timeout,
        "limits": {
            "memory": config.limits.memory,
            "cpus": config.limits.cpus,
            "pids": config.limits.pids,
            "tmpfs_size_mb": config.limits.tmpfs_size_mb,
        },
        "started_at": started_at,
        "wall_clock_seconds": wall,
        "n_tasks": score["n"],
        "n_no_code": score["n_no_code"],
        "warning": OPT_IN_WARNING,
    }


def _safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("_") or "model"
