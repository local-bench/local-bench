"""In-container task runner (STANDALONE, stdlib-only).

This file is passed as the container's `python -c` program with task JSON on stdin, so no
host files are mounted and it must not import anything outside the stdlib. For each task it
runs the assembled self-executing program (generation + tests + trusted epilogue) in a
FRESH subprocess and records the exit code: 0 = all tests passed. The runner process
itself never imports or executes the untrusted generation, so it cannot be corrupted by
it; each task's blast radius is its own subprocess + the container's bounded /tmp tmpfs.

It is also importable (`run_program`) so the harness logic is unit-tested locally on safe
fixtures without Docker.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from typing import Final, Literal, TypeAlias

SCHEMA = "localbench-coding-exec-runner-v2"
SENTINEL_TAG: Final = "<SENTINEL>"
# The trusted driver reads the per-task nonce from this env var and DELETES it before any
# untrusted code runs, so untrusted code cannot read the nonce and forge a passing sentinel.
# Must match localbench.coding_exec.program.NONCE_ENV_VAR (this module is standalone/stdlib-only
# and is mounted read-only into the container, so it cannot import it — a cli test asserts equality).
NONCE_ENV_VAR: Final = "LOCALBENCH_SENTINEL_NONCE"
GradingIntegrity: TypeAlias = Literal[
    "sentinel_ok",
    "no_sentinel",
    "nonce_mismatch",
    "counts_fail",
]
SentinelValue: TypeAlias = str | int | float | bool | None
SentinelPayload: TypeAlias = Mapping[str, SentinelValue]


def _sandbox_env(work: str) -> dict:
    """Env for the task subprocess. The container rootfs is read-only; the ONLY writable
    location is the /tmp tmpfs. Libraries that insist on writing a cache (numba, matplotlib,
    fontconfig, HF, etc.) fail against a read-only HOME/site-packages, so point every standard
    cache var at a per-task scratch dir inside the sandbox. Security-neutral: these are already
    confined to the bounded tmpfs, and network stays off."""
    env = dict(os.environ)
    cache = os.path.join(work, "cache")
    os.makedirs(cache, exist_ok=True)
    env.update(
        {
            "HOME": work,
            "TMPDIR": work,
            "NUMBA_CACHE_DIR": cache,
            "MPLCONFIGDIR": cache,
            "XDG_CACHE_HOME": cache,
            "FONTCONFIG_PATH": cache,
            "HF_HOME": cache,
            "NLTK_DATA": cache,
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
        }
    )
    return env


def run_program(program: str, *, timeout: float = 30.0, stderr_tail_bytes: int = 2000) -> dict:
    """Run one assembled program in a subprocess and require trusted completion proof."""
    nonce = secrets.token_urlsafe(18)
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "prog.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(program)  # nonce is delivered out of band (env), never written to the file
        env = _sandbox_env(work)
        env[NONCE_ENV_VAR] = nonce
        try:
            proc = subprocess.run(
                [sys.executable, path],
                capture_output=True,
                timeout=timeout,
                cwd=work,
                env=env,
            )
            exit_code = proc.returncode
            timed_out = False
            stderr = proc.stderr
            stdout = proc.stdout
        except subprocess.TimeoutExpired as exc:
            exit_code = -9
            timed_out = True
            stderr = _bytes(exc.stderr)
            stdout = _bytes(exc.stdout)
    stdout_text = stdout.decode("utf-8", "replace")
    grading_integrity = _grading_integrity(_last_sentinel(stdout_text), nonce)
    return {
        "passed": exit_code == 0 and not timed_out and grading_integrity == "sentinel_ok",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "grading_integrity": grading_integrity,
        "stdout_tail": stdout[-stderr_tail_bytes:].decode("utf-8", "replace"),
        "stderr_tail": stderr[-stderr_tail_bytes:].decode("utf-8", "replace"),
    }


def _last_sentinel(stdout: str) -> SentinelPayload | None:
    prefix = f"{SENTINEL_TAG} "
    for line in reversed(stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line[len(prefix):])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _grading_integrity(payload: SentinelPayload | None, nonce: str) -> GradingIntegrity:
    if payload is None:
        return "no_sentinel"
    if payload.get("nonce") != nonce:
        return "nonce_mismatch"
    run = payload.get("run")
    fail = payload.get("fail")
    err = payload.get("err")
    if (
        not isinstance(run, int)
        or isinstance(run, bool)
        or run <= 0
        or fail != 0
        or err != 0
    ):
        return "counts_fail"
    return "sentinel_ok"


def _bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    tasks_path = args[0]
    timeout = float(args[1]) if len(args) > 1 else 30.0
    if tasks_path == "-":
        tasks = json.load(sys.stdin)
    else:
        with open(tasks_path, encoding="utf-8") as handle:
            tasks = json.load(handle)
    results = [{"id": task["id"], **run_program(task["program"], timeout=timeout)} for task in tasks]
    print(json.dumps({"schema": SCHEMA, "results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
