from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from localbench.serving.job_object import WindowsJobObject


@dataclass(slots=True)
class LaunchedServer:
    process: subprocess.Popen[str]
    job: WindowsJobObject
    job_handle: int
    log_handle: TextIO

    def close_log(self) -> None:
        self.log_handle.close()


@dataclass(frozen=True, slots=True)
class JobController:
    job: WindowsJobObject
    job_handle: int

    def terminate_job(self) -> None:
        self.job.terminate(self.job_handle, exit_code=70)

    def close(self) -> None:
        self.job.close(self.job_handle)


def launch_llama_cpp(argv: list[str], *, cwd: Path, log_path: Path) -> LaunchedServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8")
    job = WindowsJobObject()
    job_handle = job.create()
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=serve_env(),
    )
    process_handle = getattr(process, "_handle", None)
    if not isinstance(process_handle, int):
        process.terminate()
        log_handle.close()
        job.close(job_handle)
        raise RuntimeError("could not obtain Windows process handle for Job Object assignment")
    job.assign_process(job_handle, process_handle=process_handle)
    return LaunchedServer(process=process, job=job, job_handle=job_handle, log_handle=log_handle)


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if not isinstance(port, int):
        raise RuntimeError("failed to allocate loopback port")
    return port


def serve_env() -> dict[str, str]:
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = "0"
    return env
