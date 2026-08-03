from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, override

import httpx

from localbench._types import JsonObject
from localbench.check.execution import DEFAULT_LCE_SERVER_BIN, LceLaunchConfig, lce_server_argv
from localbench.check.live_http import LiveHttpConfig
from localbench.check.types import CheckError, ConstructionDefect, SignedEditionValidationError
from localbench.serving.process import JobController, LaunchedServer, allocate_port, launch_llama_cpp
from localbench.serving.teardown import teardown_owned_server


@dataclass(frozen=True, slots=True)
class InfrastructureFailure(CheckError):
    kind: str
    detail: str
    failure_class: str = "infrastructure"

    @override
    def __str__(self) -> str:
        return f"{self.failure_class} failure ({self.kind}): {self.detail}"


@dataclass(frozen=True, slots=True)
class LiveRunnerConfig:
    model_file: Path
    run_dir: Path
    server_bin: Path = DEFAULT_LCE_SERVER_BIN
    host: str = "127.0.0.1"
    port: int | None = None
    model_id: str = "localbench-check"
    startup_timeout_seconds: float = 180.0
    poll_interval_seconds: float = 0.25
    allow_untrusted_code: bool = False


class ServerController(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def stop(self) -> None: ...


ServerFactory = Callable[[list[str], Path, Path], ServerController]
CycleExecutor = Callable[[LiveHttpConfig, JsonObject], list[JsonObject]]
CycleReady = Callable[[LiveHttpConfig, JsonObject, JsonObject], None]


@dataclass(frozen=True, slots=True)
class ServerCycleResult:
    rows: list[JsonObject]
    props: JsonObject
    start: JsonObject


@dataclass(frozen=True, slots=True)
class ServerCycleOptions:
    port: int
    api_key: str
    launch: ServerFactory
    execute: CycleExecutor
    ready: CycleReady


@dataclass(frozen=True, slots=True)
class _JobServerController:
    launched: LaunchedServer

    @property
    def pid(self) -> int:
        return self.launched.process.pid

    def poll(self) -> int | None:
        return self.launched.process.poll()

    def stop(self) -> None:
        evidence = teardown_owned_server(
            process=self.launched.process,
            controller=JobController(self.launched.job, self.launched.job_handle),
            owned_pids=[self.launched.process.pid],
        )
        self.launched.close_log()
        if not evidence.terminated:
            raise InfrastructureFailure("teardown", "owned llama-server process did not terminate cleanly")


def run_server_cycle(
    config: LiveRunnerConfig,
    options: ServerCycleOptions,
) -> ServerCycleResult:
    launch_config = LceLaunchConfig(
        model_file=config.model_file,
        run_dir=config.run_dir,
        host=config.host,
        port=options.port,
        api_key=options.api_key,
        server_bin=config.server_bin,
        model_id=config.model_id,
    )
    controller = options.launch(
        lce_server_argv(launch_config),
        config.server_bin.parent,
        config.run_dir / "serve.log",
    )
    base_url = f"http://{config.host}:{options.port}"
    start_id = uuid.uuid4().hex
    try:
        props = _wait_for_health_and_props(
            controller,
            config,
            base_url=base_url,
            api_key=options.api_key,
        )
        http_config = LiveHttpConfig(base_url, options.api_key, config.model_id, start_id)
        start: JsonObject = {
            "effective_server_config": props,
            "pid": controller.pid,
            "server_start_id": start_id,
        }
        options.ready(http_config, props, start)
        return ServerCycleResult(options.execute(http_config, props), props, start)
    except InfrastructureFailure:
        raise
    except SignedEditionValidationError:
        raise
    except ConstructionDefect as error:
        raise InfrastructureFailure(error.kind, error.detail, failure_class="construction-defect") from error
    except (CheckError, httpx.HTTPError, OSError, RuntimeError, ValueError) as error:
        raise InfrastructureFailure("execution", str(error)) from error
    finally:
        try:
            controller.stop()
        except InfrastructureFailure:
            raise
        except (OSError, RuntimeError) as error:
            raise InfrastructureFailure("teardown", str(error)) from error


def server_port(config: LiveRunnerConfig) -> int:
    return config.port if config.port is not None else allocate_port()


def owned_server_factory(argv: list[str], cwd: Path, log_path: Path) -> ServerController:
    return _JobServerController(launch_llama_cpp(argv, cwd=cwd, log_path=log_path))


def _wait_for_health_and_props(
    controller: ServerController,
    config: LiveRunnerConfig,
    *,
    base_url: str,
    api_key: str,
) -> JsonObject:
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=2.0, headers=headers) as client:
        deadline = time.monotonic() + config.startup_timeout_seconds
        while time.monotonic() < deadline:
            exit_code = controller.poll()
            if exit_code is not None:
                raise InfrastructureFailure("server-crash", f"llama-server exited with code {exit_code}")
            try:
                response = client.get(f"{base_url}/health")
                if response.status_code == 200:
                    props_response = client.get(f"{base_url}/props")
                    _ = props_response.raise_for_status()
                    raw_props = cast(object, props_response.json())
                    if not isinstance(raw_props, dict):
                        raise InfrastructureFailure("invalid-props", "/props did not return an object")
                    props = cast(JsonObject, raw_props)
                    _validate_props(props, config.model_file)
                    return props
            except httpx.TransportError as error:
                _ = error
            time.sleep(config.poll_interval_seconds)
    raise InfrastructureFailure("startup-timeout", "llama-server did not become healthy before the deadline")


def _validate_props(props: JsonObject, model_file: Path) -> None:
    if props.get("total_slots") != 1:
        raise InfrastructureFailure("invalid-props", "llama-server must expose exactly one slot")
    model_path = props.get("model_path")
    if not isinstance(model_path, str) or Path(model_path).resolve() != model_file.resolve():
        raise InfrastructureFailure("invalid-props", "llama-server model_path does not match the requested artifact")
