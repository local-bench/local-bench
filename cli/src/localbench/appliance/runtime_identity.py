"""Canonical C4 agentic runtime/worker drift identity.

The canonical identity string is the UTF-8 decoding of the repository's
``canonical_json_bytes`` encoding: keys sorted lexicographically, compact ``(',', ':')``
separators, no ASCII escaping, and no NaN values. The digest is SHA-256 over those exact
UTF-8 bytes. Git state, dirty-tree state, filesystem paths, hostnames, PIDs, ports,
timestamps, and environment values are intentionally excluded, so identical component
inputs produce identical identity strings on every machine.

This identity detects drift among the pinned and observed runtime components. It is not an
anti-spoof mechanism and does not replace signature verification or appliance ownership
checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import canonical_json_bytes, canonical_json_hash

AGENTIC_WORKER_PROTOCOL_VERSION: Final = "localbench.agentic-worker.v1"


@dataclass(frozen=True, slots=True)
class AgenticRuntimeIdentityError(ValueError):
    component: str
    expected: str
    observed: str

    def __str__(self) -> str:
        return (
            f"agentic runtime identity mismatch for {self.component}: "
            f"expected {self.expected!r}, observed {self.observed!r}"
        )


@dataclass(frozen=True, slots=True)
class AgenticRuntimeIdentityComponents:
    runtime_id: str
    rootfs_sha256: str
    worker_wheel_sha256: str
    worker_protocol_version: str
    python_version: str
    bubblewrap_version: str
    appworld_package_sha256: str
    appworld_data_sha256: str
    ordered_task_ids_sha256: str
    selection_recipe_sha256: str
    execution_contract_sha256: str
    localbench_distribution_version: str
    worker_content_sha256: str
    host_agent_loop_scorer_source_sha256: str


def agentic_runtime_identity_object(
    components: AgenticRuntimeIdentityComponents,
) -> JsonObject:
    return {
        "runtime_id": components.runtime_id,
        "rootfs_sha256": components.rootfs_sha256,
        "worker_wheel_sha256": components.worker_wheel_sha256,
        "worker_protocol_version": components.worker_protocol_version,
        "python_version": components.python_version,
        "bubblewrap_version": components.bubblewrap_version,
        "appworld_package_sha256": components.appworld_package_sha256,
        "appworld_data_sha256": components.appworld_data_sha256,
        "ordered_task_ids_sha256": components.ordered_task_ids_sha256,
        "selection_recipe_sha256": components.selection_recipe_sha256,
        "execution_contract_sha256": components.execution_contract_sha256,
        "localbench_distribution_version": components.localbench_distribution_version,
        "worker_content_sha256": components.worker_content_sha256,
        "host_agent_loop_scorer_source_sha256": (
            components.host_agent_loop_scorer_source_sha256
        ),
    }


def canonical_agentic_runtime_identity(identity: JsonObject) -> str:
    return canonical_json_bytes(identity).decode("utf-8")


def agentic_runtime_identity_sha256(identity: JsonObject) -> str:
    return canonical_json_hash(identity)


def agentic_runtime_identity_from_sources(
    manifest: JsonObject,
    handshake: JsonObject,
    *,
    worker_identity: JsonObject | None = None,
    execution_contract: JsonObject | None = None,
) -> AgenticRuntimeIdentityComponents:
    if worker_identity is None:
        reported_version = handshake.get("localbench_distribution_version")
        reported_content_sha256 = handshake.get("worker_content_sha256")
        if (
            isinstance(reported_version, str)
            and reported_version
            and isinstance(reported_content_sha256, str)
            and reported_content_sha256
        ):
            worker_identity = handshake
        else:
            from localbench.scoring.agentic_exec.worker_identity import (  # noqa: PLC0415
                worker_implementation_identity,
            )

            host_identity = worker_implementation_identity()
            worker_identity = {
                "localbench_distribution_version": (
                    reported_version
                    if isinstance(reported_version, str) and reported_version
                    else _text(host_identity, "localbench_distribution_version")
                ),
                "worker_content_sha256": (
                    reported_content_sha256
                    if isinstance(reported_content_sha256, str)
                    and reported_content_sha256
                    else _text(host_identity, "worker_content_sha256")
                ),
            }
    if execution_contract is None:
        from localbench.scoring.agentic_exec.execution_contract import (  # noqa: PLC0415
            load_execution_contract,
        )

        execution_contract = load_execution_contract()

    rootfs = _object(manifest, "rootfs")
    worker = _object(manifest, "worker")
    tasks = _object(manifest, "task_identity")
    contract_payload = _object(execution_contract, "payload")
    covered_behavior = _object(contract_payload, "covered_behavior")

    runtime_id = _text(manifest, "runtime_id")
    protocol_version = _text(worker, "protocol_version")
    execution_contract_sha256 = _text(execution_contract, "payload_sha256")
    ordered_task_ids_sha256 = _text(tasks, "ordered_task_ids_sha256")
    selection_recipe_sha256 = _text(tasks, "selection_recipe_sha256")
    _assert_equal("runtime_id", runtime_id, _text(handshake, "runtime_id"))
    _assert_equal(
        "worker_protocol_version",
        AGENTIC_WORKER_PROTOCOL_VERSION,
        protocol_version,
    )
    _assert_equal(
        "worker_protocol_version",
        protocol_version,
        _text(handshake, "protocol_version"),
    )
    _assert_equal(
        "execution_contract_sha256",
        execution_contract_sha256,
        _text(manifest, "execution_contract_sha256"),
    )
    _assert_equal(
        "execution_contract_sha256",
        execution_contract_sha256,
        _text(handshake, "execution_contract_sha256"),
    )
    _assert_equal(
        "ordered_task_ids_sha256",
        ordered_task_ids_sha256,
        _text(handshake, "ordered_task_ids_sha256"),
    )
    _assert_equal(
        "selection_recipe_sha256",
        selection_recipe_sha256,
        _text(handshake, "selection_recipe_sha256"),
    )

    return AgenticRuntimeIdentityComponents(
        runtime_id=runtime_id,
        rootfs_sha256=_text(rootfs, "sha256"),
        worker_wheel_sha256=_text(worker, "sha256"),
        worker_protocol_version=protocol_version,
        python_version=_text(handshake, "python_version"),
        bubblewrap_version=_text(handshake, "bubblewrap_version"),
        appworld_package_sha256=_text(handshake, "appworld_package_sha256"),
        appworld_data_sha256=_text(handshake, "appworld_data_sha256"),
        ordered_task_ids_sha256=ordered_task_ids_sha256,
        selection_recipe_sha256=selection_recipe_sha256,
        execution_contract_sha256=execution_contract_sha256,
        localbench_distribution_version=_text(
            worker_identity, "localbench_distribution_version"
        ),
        worker_content_sha256=_text(worker_identity, "worker_content_sha256"),
        host_agent_loop_scorer_source_sha256=_text(
            covered_behavior, "host_agent_loop_scorer_source_sha256"
        ),
    )


def _object(source: JsonObject, key: str) -> JsonObject:
    value = source.get(key)
    if not isinstance(value, dict):
        raise AgenticRuntimeIdentityError(key, "object", repr(value))
    return value


def _text(source: JsonObject, key: str) -> str:
    value: JsonValue | None = source.get(key)
    if not isinstance(value, str) or not value:
        raise AgenticRuntimeIdentityError(key, "non-empty string", repr(value))
    return value


def _assert_equal(component: str, expected: str, observed: str) -> None:
    if expected != observed:
        raise AgenticRuntimeIdentityError(component, expected, observed)
