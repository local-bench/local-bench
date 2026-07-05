"""`localbench code` orchestration: generate -> assemble -> sandbox-execute -> score.

Reuses the standard generation path (`run_benchmark`) to drive the user's endpoint over
the frozen BigCodeBench-Hard prompts, then extracts each generation, assembles a
self-executing test program, runs all of them in ONE hardened sandbox container (each task
in its own subprocess inside it), and scores the pass rate as the coding-exec axis.

Both the generation transport and the sandbox runner are injectable, so the whole flow is
unit-tested without a model endpoint or Docker. The real run is GPU + Docker gated.
"""

from __future__ import annotations

import hashlib
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
from localbench.coding_exec.ast_gate import ASTGateResult, check_ast_gate
from localbench.coding_exec import runner as runner_module
from localbench.coding_exec.artifacts import (
    ast_rejected_artifact,
    verified_artifact,
    verdict_from_runner_result,
)
from localbench.coding_exec.extract import extract_code_result
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
from localbench.scoring.scorecard import scorecard_identity

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


def execute_pending_artifacts(
    run_path: Path,
    config: CodingExecConfig,
    *,
    sandbox_runner: SandboxRunner | None = None,
    docker_env: DockerEnv | None = None,
) -> JsonObject:
    env = docker_env if docker_env is not None else probe_docker_env()
    preflight = preflight_checks(env, allow_unsafe=config.allow_unsafe_sandbox)
    if not preflight.ok:
        raise CodingExecError(
            "sandbox preflight failed — refusing to run model-generated code: "
            + "; ".join(preflight.blockers)
            + " (override with allow_unsafe_sandbox if you accept the risk)"
        )
    config = replace(config, runtime=config.runtime or preflight.runtime)
    run = read_json_object(run_path)
    suite = read_json_object(config.suite_dir / "suite.json")
    warnings: list[str] = []
    rendered = render_benches(BENCH, config.tier, config.max_items, config.suite_dir, suite, warnings)
    source_by_id = {
        str(source["id"]): source
        for bench in rendered
        for source in bench.source_items
        if isinstance(source.get("id"), str)
    }
    tasks: list[JsonObject] = []
    pending_items: list[JsonObject] = []
    rejected_any = False
    for item in _run_items(run):
        if item.get("bench") != BENCH:
            continue
        artifact = item.get("code_artifact")
        if not isinstance(artifact, dict) or artifact.get("verdict_source") == "verifier":
            continue
        sanitized = artifact.get("sanitized_code")
        source = source_by_id.get(str(item.get("id")))
        if not isinstance(sanitized, str) or source is None:
            continue
        gate = check_ast_gate(sanitized)
        if not gate.accepted:
            item["code_artifact"] = ast_rejected_artifact(artifact, gate)
            item["correct"] = False
            item["failure_kind"] = "coding_ast_rejected"
            item["extracted"] = sanitized
            rejected_any = True
            continue
        tasks.append(
            {
                "id": str(item["id"]),
                "program": assemble_program(sanitized, str(source["test"]), str(source["entry_point"])),
            },
        )
        pending_items.append(item)
    if not tasks:
        if rejected_any:
            _refresh_bigcodebench_aggregate(run)
        write_json(run, config.out or run_path)
        return run
    verdicts = {str(result["id"]): result for result in _execute(tasks, config, sandbox_runner)}
    image_digest = config.image if "@sha256:" in config.image else None
    for item in pending_items:
        result = verdicts.get(str(item["id"]))
        if result is None:
            continue
        artifact = item["code_artifact"]
        if isinstance(artifact, dict):
            item["code_artifact"] = verified_artifact(
                artifact,
                verdict=verdict_from_runner_result(result),
                image_digest=image_digest,
            )
            item["correct"] = bool(result.get("passed"))
    _refresh_bigcodebench_aggregate(run)
    output_path = config.out or run_path
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
        extraction = extract_code_result(result.get("response_text"))
        if extraction.extracted_code is None:
            failures.append({"id": item_id, "passed": False, "no_code": True})
            continue
        code = extraction.extracted_code.rstrip()
        gate = check_ast_gate(code)
        if not gate.accepted:
            failures.append(_ast_rejection_row(item_id, gate))
            continue
        program = assemble_program(code, str(source_item["test"]), str(source_item["entry_point"]))
        tasks.append({"id": item_id, "program": program})
    return tasks, failures


def _run_items(run: JsonObject) -> list[JsonObject]:
    items = run.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _refresh_bigcodebench_aggregate(run: JsonObject) -> None:
    items = [item for item in _run_items(run) if item.get("bench") == BENCH]
    verdict_rows: list[JsonObject] = []
    for item in items:
        artifact = item.get("code_artifact")
        verdict = artifact.get("verdict") if isinstance(artifact, dict) else None
        if not isinstance(verdict, dict):
            verdict_rows.append(
                {
                    "id": item.get("id"),
                    "passed": False,
                    "no_code": item.get("extracted") is None,
                    "conformance_failure": item.get("failure_kind"),
                },
            )
            continue
        verdict_rows.append(
            {
                "id": item.get("id"),
                "passed": verdict.get("passed") is True,
                "timed_out": verdict.get("timeout") is True,
                "conformance_failure": item.get("failure_kind"),
            },
        )
    score = score_coding_exec(verdict_rows)
    benches = run.get("benches")
    if not isinstance(benches, dict):
        benches = {}
        run["benches"] = benches
    termination_rate = 1.0 - (score["n_timed_out"] / score["n"] if score["n"] else 0.0)
    benches[BENCH] = {
        "n": score["n"],
        "n_errors": 0,
        "n_extraction_failures": score["n_no_code"],
        "n_conformance_failures": score["n_conformance_failures"],
        "n_unscoreable": score["n_unscoreable"],
        "raw_accuracy": score["raw_accuracy"],
        "chance_corrected": score["chance_corrected"],
        "termination_rate": termination_rate,
        "conditional_accuracy": score["raw_accuracy"] / termination_rate if termination_rate else 0.0,
    }


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


def _runner_sha256() -> str:
    """Hash of the in-container harness (runner.py) — provenance so a verifier can confirm
    the trusted runner wasn't tampered with on a ranked submission."""
    return hashlib.sha256(Path(runner_module.__file__).resolve().read_bytes()).hexdigest()


def ranked_eligibility(config: CodingExecConfig) -> tuple[bool, list[str]]:
    """A coding-exec run is RANKABLE only if its execution environment is fully pinned and
    the sandbox boundary was not overridden (oracle #13). The digest-pinned image IS the
    dependency lock for the container; the runner hash (recorded in the manifest) pins our
    harness. Returns (eligible, reasons-if-not)."""
    reasons: list[str] = []
    if "@sha256:" not in config.image:
        reasons.append("image not digest-pinned (repo@sha256:...) — container runtime + deps not locked")
    if config.allow_unsafe_sandbox:
        reasons.append("allow_unsafe_sandbox override used — sandbox isolation not guaranteed")
    return (not reasons, reasons)


def _manifest(
    config: CodingExecConfig,
    suite: JsonObject,
    started_at: str,
    wall: float,
    score: CodingExecScore,
) -> JsonObject:
    ranked_eligible, ranked_reasons = ranked_eligibility(config)
    return {
        "lane": "exec",
        "schema_note": "coding-exec axis: model-generated code run in a hardened opt-in Docker sandbox",
        "scorecard": scorecard_identity(),
        "image": config.image,
        "image_digest_pinned": "@sha256:" in config.image,
        "runner_sha256": _runner_sha256(),
        "ranked_eligible": ranked_eligible,
        "ranked_ineligible_reasons": ranked_reasons,
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
        "n_conformance_failures": score["n_conformance_failures"],
        "warning": OPT_IN_WARNING,
    }


def _safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("_") or "model"


def _ast_rejection_row(item_id: str, gate: ASTGateResult) -> JsonObject:
    return {
        "id": item_id,
        "passed": False,
        "conformance_failure": "coding_ast_rejected",
        "ast_gate_failure": _ast_gate_failure(gate),
    }


def _ast_gate_failure(gate: ASTGateResult) -> str:
    return gate.failure or "forbidden_reference"
