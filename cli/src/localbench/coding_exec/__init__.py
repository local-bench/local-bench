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
    OPT_IN_WARNING,
    RawRunResult,
    SandboxLimits,
    SandboxResult,
    default_runner,
    docker_run_argv,
    run_sandboxed,
)
from localbench.coding_exec.score import CodingExecScore, score_coding_exec

__all__ = [
    "MANDATORY_SECURITY_FLAGS",
    "OPT_IN_WARNING",
    "CodingExecScore",
    "RawRunResult",
    "SandboxLimits",
    "SandboxResult",
    "assemble_program",
    "default_runner",
    "docker_run_argv",
    "extract_code",
    "run_program",
    "run_sandboxed",
    "score_coding_exec",
]
