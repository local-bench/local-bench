"""In-container task runner (STANDALONE, stdlib-only).

This file is mounted READ-ONLY into the hardened sandbox container and executed by the
container's Python — so it must not import anything outside the stdlib. For each task it
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
import subprocess
import sys
import tempfile

SCHEMA = "localbench-coding-exec-runner-v1"


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
    """Run one assembled program in a subprocess; pass = clean exit 0 within the timeout."""
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "prog.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(program)
        try:
            proc = subprocess.run(
                [sys.executable, path],
                capture_output=True,
                timeout=timeout,
                cwd=work,
                env=_sandbox_env(work),
            )
            exit_code = proc.returncode
            timed_out = False
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = -9
            timed_out = True
            stderr = exc.stderr or b""
    return {
        "passed": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stderr_tail": stderr[-stderr_tail_bytes:].decode("utf-8", "replace"),
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    tasks_path = args[0]
    timeout = float(args[1]) if len(args) > 1 else 30.0
    with open(tasks_path, encoding="utf-8") as handle:
        tasks = json.load(handle)
    results = [{"id": task["id"], **run_program(task["program"], timeout=timeout)} for task in tasks]
    print(json.dumps({"schema": SCHEMA, "results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
