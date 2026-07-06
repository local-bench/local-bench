"""Opt-in, sandboxed code-EXECUTION coding axis (CODING-EXEC-MODULE-SPEC.md).

The judge-free headline cannot credibly measure code GENERATION (dual red-team:
MCQ/IO-prediction proxies are code *reasoning*, not *writing*). This module adds an
OPT-IN axis that runs the model's generated code against unit tests inside a hardened,
default-deny Docker sandbox on the USER's machine — never on our infra (v1).

`sandbox.py` encodes the host-OS hardening locked after the dual SECURITY red-team
(GPT-5.5 + Gemini 3.1 Pro, 2026-06-19); the flags are asserted by tests so the
sandbox can't silently weaken.
"""

from __future__ import annotations

from localbench.coding_exec.extract import extract_code
from localbench.coding_exec.program import assemble_program
from localbench.coding_exec.runner import run_program
from localbench.coding_exec.sandbox import (
    MANDATORY_SECURITY_FLAGS,
    MIN_SAFE_RUNC,
    OPT_IN_WARNING,
    DockerEnv,
    PreflightResult,
    RawRunResult,
    SandboxLimits,
    SandboxResult,
    default_runner,
    docker_run_argv,
    preflight_checks,
    probe_docker_env,
    run_sandboxed,
)
from localbench.coding_exec.score import (
    CODING_SCOREABLE_REV,
    SANDBOX_UNSCOREABLE_BCBH,
    CodingExecScore,
    score_coding_exec,
)

__all__ = [
    "MANDATORY_SECURITY_FLAGS",
    "MIN_SAFE_RUNC",
    "OPT_IN_WARNING",
    "CodingExecScore",
    "DockerEnv",
    "PreflightResult",
    "RawRunResult",
    "SandboxLimits",
    "SandboxResult",
    "CODING_SCOREABLE_REV",
    "SANDBOX_UNSCOREABLE_BCBH",
    "assemble_program",
    "default_runner",
    "docker_run_argv",
    "extract_code",
    "preflight_checks",
    "probe_docker_env",
    "run_program",
    "run_sandboxed",
    "score_coding_exec",
]
