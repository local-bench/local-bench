from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from runtime_capacity_probe_support import run_probe, startup_log

from localbench.runtime_capacity_probe import CapacityProbeMismatchError
from localbench.serving.teardown import LiveProcessIdentity


@pytest.mark.anyio
async def test_capacity_probe_rejects_stale_valid_prefix_when_current_epoch_is_missing(
    tmp_path: Path,
) -> None:
    # Given: a valid startup record from an earlier launch and no current startup bytes.
    # When/Then: the stale prefix cannot satisfy the current capacity attestation.
    with pytest.raises(CapacityProbeMismatchError, match="startup log"):
        await run_probe(
            tmp_path,
            stale_startup_log=startup_log(),
            startup_log="",
        )


@pytest.mark.anyio
async def test_capacity_probe_accepts_current_valid_suffix_after_stale_invalid_prefix(
    tmp_path: Path,
) -> None:
    # Given: a stale invalid epoch followed by a complete valid current epoch.
    stale = startup_log().replace("n_ctx         = 65536", "n_ctx         = 32768")
    # When: validation is bound to the current process's append boundary.
    evidence = await run_probe(tmp_path, stale_startup_log=stale)

    # Then: only the current suffix attests capacity and its source range is auditable.
    assert evidence["passed"] is True
    assert evidence["startup_log_sha256"] == hashlib.sha256(
        startup_log().encode("utf-8"),
    ).hexdigest()
    assert evidence["startup_log_source"] == {
        "process_pid": 4242,
        "process_executable_path": "C:/tools/llama-server.exe",
        "process_commandline_sha256": "a" * 64,
        "process_birth_token": "134300000000000001",
        "identity_verified_before_probe": True,
        "identity_verified_after_probe": True,
        "listener_owner_pid_before_probe": 4242,
        "listener_owner_pid_after_probe": 4242,
        "listener_owner_verified_before_probe": True,
        "listener_owner_verified_after_probe": True,
        "start_byte": len(stale.encode("utf-8")),
        "end_byte": len((stale + startup_log()).encode("utf-8")),
    }


@pytest.mark.anyio
async def test_capacity_probe_rejects_partial_current_epoch_mixed_with_stale_prefix(
    tmp_path: Path,
) -> None:
    # Given: stale context lines and only a cache line from the current process epoch.
    lines = startup_log().splitlines()
    stale = "\n".join(lines[:-1]) + "\n"
    current = lines[-1]
    # When/Then: fields cannot be assembled across process epochs.
    with pytest.raises(CapacityProbeMismatchError, match="logged context"):
        await run_probe(
            tmp_path,
            stale_startup_log=stale,
            startup_log=current,
        )


@pytest.mark.anyio
async def test_capacity_probe_resume_append_uses_only_current_valid_epoch(
    tmp_path: Path,
) -> None:
    # Given: a reused resume directory whose log contains a complete prior launch.
    stale = startup_log() + "\ncommon_params_fit_impl: stale fit adjustment\n"
    # When: the resumed run appends a complete current startup record.
    evidence = await run_probe(tmp_path, stale_startup_log=stale)

    # Then: stale fit activity does not contaminate the current process epoch.
    assert evidence["passed"] is True
    effective = evidence["effective"]
    assert isinstance(effective, dict)
    assert effective["fit"] == "off"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("serve_log_start_byte", "server_pid", "failure"),
    [
        (10_000, 4242, "byte range"),
        (0, 0, "PID"),
    ],
)
async def test_capacity_probe_rejects_unprovable_process_epoch_boundary(
    tmp_path: Path,
    serve_log_start_byte: int,
    server_pid: int,
    failure: str,
) -> None:
    # Given: an invalid managed process identity or append boundary.
    # When/Then: capacity evidence fails closed before parsing startup fields.
    with pytest.raises(CapacityProbeMismatchError, match=failure):
        await run_probe(
            tmp_path,
            serve_log_start_byte=serve_log_start_byte,
            server_pid=server_pid,
        )


@pytest.mark.anyio
@pytest.mark.parametrize("live_identity", [None, "mismatch"])
async def test_capacity_probe_rejects_dead_or_reused_server_process(
    tmp_path: Path,
    live_identity: str | None,
) -> None:
    # Given: the launched child has exited or its PID now names a different process.
    probe = (
        (lambda _pid: None)
        if live_identity is None
        else lambda pid: LiveProcessIdentity(
            pid=pid,
            executable_path="C:/Windows/System32/notepad.exe",
            commandline_sha256="b" * 64,
            process_birth_token="134300000000000001",
        )
    )

    # When / Then: old log text and live endpoints cannot attest the dead/reused child.
    with pytest.raises(CapacityProbeMismatchError, match="process identity"):
        await run_probe(tmp_path, process_identity_probe=probe)


@pytest.mark.anyio
async def test_capacity_probe_rejects_same_pid_executable_and_commandline_from_new_birth(
    tmp_path: Path,
) -> None:
    # Given: a reused PID whose executable and command line exactly match the launched process.
    # When/Then: the different immutable process-birth token fails closed.
    with pytest.raises(CapacityProbeMismatchError, match="process identity"):
        await run_probe(
            tmp_path,
            recorded_birth_token="134300000000000001",
            live_birth_token="134300000000000002",
            listener_owner_probe=lambda _host, _port: 4242,
        )


@pytest.mark.anyio
async def test_capacity_probe_rejects_listener_owned_by_different_process(
    tmp_path: Path,
) -> None:
    # Given: the launched process identity is live but another PID owns the probed listener.
    # When/Then: valid HTTP payloads and startup bytes cannot attest that other listener.
    with pytest.raises(CapacityProbeMismatchError, match="listener owner"):
        await run_probe(
            tmp_path,
            recorded_birth_token="134300000000000001",
            live_birth_token="134300000000000001",
            listener_owner_probe=lambda _host, _port: 9001,
        )


@pytest.mark.anyio
async def test_capacity_probe_accepts_matching_process_epoch_and_listener_before_and_after(
    tmp_path: Path,
) -> None:
    # Given: both live probes identify the launched birth epoch and its loopback listener.
    listener_queries: list[tuple[str, int]] = []

    def listener_owner(host: str, port: int) -> int:
        listener_queries.append((host, port))
        return 4242

    # When: capacity evidence is collected from the managed server.
    evidence = await run_probe(
        tmp_path,
        recorded_birth_token="134300000000000001",
        live_birth_token="134300000000000001",
        listener_owner_probe=listener_owner,
    )

    # Then: both sides of collection are bound to the same birth and listener owner.
    assert evidence["passed"] is True
    assert listener_queries == [("127.0.0.1", 8080), ("127.0.0.1", 8080)]
    source = evidence["startup_log_source"]
    assert isinstance(source, dict)
    assert source["process_birth_token"] == "134300000000000001"
    assert source["listener_owner_verified_before_probe"] is True
    assert source["listener_owner_verified_after_probe"] is True
