from __future__ import annotations

import signal
from dataclasses import dataclass, field
from types import TracebackType

import pytest

from localbench._types import ChatMessage, JsonValue
from localbench.scoring.agentic_exec import benchmark
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.model_client import GenerationParams, ModelResponse
from localbench.scoring.agentic_exec.wsl_proxy import WslTransportError
from localbench.scoring.agentic_exec.wsl_teardown import (
    ProcessPin,
    TeardownError,
    terminate_linux_worker,
    verify_linux_worker_terminated,
)

_SIGKILL = int(getattr(signal, "SIGKILL", 9))


@dataclass(frozen=True, slots=True)
class _Process:
    pin: ProcessPin
    token: str | None
    commandline: tuple[str, ...]
    survives_sigterm: bool = False
    survives_sigkill: bool = False


@dataclass(slots=True)  # noqa: MUTABLE_OK - this fake models process-table state transitions.
class _ProcessModel:
    records: dict[int, _Process]
    signals: list[tuple[int, int]] = field(default_factory=list)
    reuse_after_sigterm: _Process | None = None
    signal_error: OSError | None = None

    def _read_process(self, pid: int) -> ProcessPin | None:
        process = self.records.get(pid)
        return None if process is None else process.pin

    def capture(self, pid: int, *, token: str | None = None) -> ProcessPin:
        process = self.records.get(pid)
        if process is None:
            raise TeardownError(f"worker pid {pid} is not present")
        if token is not None and process.token != token:
            raise TeardownError(f"worker pid {pid} does not carry its spawn token")
        return process.pin

    def owned_processes(self, pin: ProcessPin, *, token: str) -> list[ProcessPin]:
        owned = [
            process.pin
            for process in self.records.values()
            if (
                process.token == token
                and process.commandline[:1] != ("/usr/bin/setsid",)
            )
            or (
                process.pin.process_group_id == pin.process_group_id
                and process.pin.session_id == pin.session_id
            )
        ]
        return sorted(owned, key=lambda process: process.pid)

    def signal_group(self, process_group_id: int, signum: int) -> None:
        self.signals.append((process_group_id, signum))
        if self.signal_error is not None:
            raise self.signal_error
        members = [
            process
            for process in self.records.values()
            if process.pin.process_group_id == process_group_id
        ]
        for process in members:
            survives = (
                process.survives_sigterm
                if signum == signal.SIGTERM
                else process.survives_sigkill
            )
            if not survives:
                self.records.pop(process.pin.pid, None)
        reused = self.reuse_after_sigterm
        if (
            signum == signal.SIGTERM
            and reused is not None
            and reused.pin.process_group_id == process_group_id
        ):
            self.records[reused.pin.pid] = reused
            self.reuse_after_sigterm = None


@dataclass(frozen=True, slots=True)
class _Observation:
    stdout: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _Verdict:
    success: bool = False
    collateral_damage: bool = False
    failures: tuple[str, ...] = ()


class _NoFinalModel:
    def complete(
        self,
        _messages: list[ChatMessage],
        _params: GenerationParams,
    ) -> ModelResponse:
        return ModelResponse("no executable block", "stop")


class _UnprovenTeardownSandbox:
    def __init__(self, model: _ProcessModel, pin: ProcessPin, token: str) -> None:
        self.model = model
        self.pin = pin
        self.token = token

    def __enter__(self) -> _UnprovenTeardownSandbox:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        try:
            terminate_linux_worker(
                self.pin,
                token=self.token,
                procfs=self.model,
                signal_group=self.model.signal_group,
                timeout_s=0.0,
                poll_interval_s=0.0,
            )
        except TeardownError as error:
            raise WslTransportError(operation="teardown", detail=str(error)) from error

    def run_block(self, _code: str) -> _Observation:
        return _Observation()

    def finalize(self, _answer: JsonValue) -> _Verdict:
        return _Verdict()


def test_linux_teardown_signals_owned_groups_and_proves_the_session_empty() -> None:
    token = "worker-token"
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    model = _ProcessModel(
        records={
            91: _process(
                pid=91,
                group=91,
                session=1,
                start=900,
                token=token,
                executable="/usr/bin/setsid",
                commandline=("/usr/bin/setsid", "--wait"),
            ),
            101: worker,
            102: _process(pid=102, group=101, session=101, start=1001, token=None),
            201: _process(
                pid=201,
                group=201,
                session=201,
                start=2000,
                token=token,
                executable="/opt/localbench/venv/bin/env_host",
            ),
        },
    )

    terminate_linux_worker(
        worker.pin,
        token=token,
        procfs=model,
        signal_group=model.signal_group,
        timeout_s=0.0,
        poll_interval_s=0.0,
    )

    assert model.signals == [(101, signal.SIGTERM), (201, signal.SIGTERM)]
    assert sorted(model.records) == [91]


def test_linux_teardown_reports_a_descendant_that_survives_term_and_kill() -> None:
    token = "worker-token"
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    model = _ProcessModel(
        records={
            101: worker,
            102: _process(
                pid=102,
                group=101,
                session=101,
                start=1001,
                token=None,
                survives_sigterm=True,
                survives_sigkill=True,
            ),
        },
    )

    with pytest.raises(TeardownError, match=r"did not terminate: \[102\]"):
        terminate_linux_worker(
            worker.pin,
            token=token,
            procfs=model,
            signal_group=model.signal_group,
            timeout_s=0.0,
            poll_interval_s=0.0,
        )

    assert model.signals == [(101, signal.SIGTERM), (101, _SIGKILL)]
    assert sorted(model.records) == [102]


def test_linux_teardown_refuses_pid_reuse_before_kill_escalation() -> None:
    token = "worker-token"
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    reused = _process(
        pid=101,
        group=101,
        session=101,
        start=9000,
        token=None,
        executable="/usr/bin/unrelated",
    )
    model = _ProcessModel(
        records={101: worker},
        reuse_after_sigterm=reused,
    )

    with pytest.raises(TeardownError, match="was reused; refusing to signal"):
        terminate_linux_worker(
            worker.pin,
            token=token,
            procfs=model,
            signal_group=model.signal_group,
            timeout_s=0.0,
            poll_interval_s=0.0,
        )

    assert model.signals == [(101, signal.SIGTERM)]
    assert model.records[101] == reused


def test_linux_teardown_verifier_rejects_a_surviving_descendant() -> None:
    token = "worker-token"
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    model = _ProcessModel(
        records={
            102: _process(pid=102, group=101, session=101, start=1001, token=None),
        },
    )

    with pytest.raises(TeardownError, match=r"remain after teardown: \[102\]"):
        verify_linux_worker_terminated(worker.pin, token=token, procfs=model)


def test_linux_teardown_reports_failed_group_signal() -> None:
    token = "worker-token"
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    model = _ProcessModel(
        records={101: worker},
        signal_error=OSError("signal refused"),
    )

    with pytest.raises(TeardownError, match="signal refused"):
        terminate_linux_worker(
            worker.pin,
            token=token,
            procfs=model,
            signal_group=model.signal_group,
            timeout_s=0.0,
        )


def test_unproven_teardown_aborts_benchmark_before_the_next_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from localbench.scoring.agentic_exec import execution_contract

    monkeypatch.setattr(execution_contract, "assert_execution_contract", lambda: "fixture")
    token = "worker-token"
    opened: list[str] = []
    process_models: list[_ProcessModel] = []

    def sandbox_factory(task_id: str) -> _UnprovenTeardownSandbox:
        opened.append(task_id)
        model, pin = _surviving_descendant_model(token)
        process_models.append(model)
        return _UnprovenTeardownSandbox(model, pin, token)

    with pytest.raises(WslTransportError) as error:
        benchmark.run_appworld_c_benchmark(
            task_ids=["first", "second"],
            model_factory=lambda _task_id: _NoFinalModel(),
            sandbox_factory=sandbox_factory,
            config=LoopConfig(max_turns=1),
        )

    assert error.value.operation == "teardown"
    assert opened == ["first"]
    assert process_models[0].signals == [
        (101, signal.SIGTERM),
        (101, _SIGKILL),
    ]


def _surviving_descendant_model(token: str) -> tuple[_ProcessModel, ProcessPin]:
    worker = _process(pid=101, group=101, session=101, start=1000, token=token)
    return (
        _ProcessModel(
            records={
                101: worker,
                102: _process(
                    pid=102,
                    group=101,
                    session=101,
                    start=1001,
                    token=None,
                    survives_sigterm=True,
                    survives_sigkill=True,
                ),
            },
        ),
        worker.pin,
    )


def _process(
    *,
    pid: int,
    group: int,
    session: int,
    start: int,
    token: str | None,
    executable: str = "/opt/localbench/venv/bin/python",
    commandline: tuple[str, ...] = (
        "/opt/localbench/venv/bin/python",
        "-m",
        "localbench.scoring.agentic_exec.wsl_worker",
    ),
    survives_sigterm: bool = False,
    survives_sigkill: bool = False,
) -> _Process:
    return _Process(
        pin=ProcessPin(
            pid=pid,
            process_group_id=group,
            session_id=session,
            start_time_ticks=start,
            executable=executable,
        ),
        token=token,
        commandline=commandline,
        survives_sigterm=survives_sigterm,
        survives_sigkill=survives_sigkill,
    )
