from __future__ import annotations

import importlib.util
import inspect
import socket
import subprocess
from dataclasses import fields, replace
from pathlib import Path

import pytest

from localbench.appliance.manifest import PINNED_RUNTIME_ID
from localbench.appliance.runtime_identity import (
    AGENTIC_WORKER_PROTOCOL_VERSION,
    AgenticRuntimeIdentityComponents,
    agentic_runtime_identity_from_sources,
    agentic_runtime_identity_object,
    agentic_runtime_identity_sha256,
    canonical_agentic_runtime_identity,
)
from localbench.scoring.agentic_exec.execution_contract import load_execution_contract
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.scoring.agentic_exec.wsl_process import WslWorkerConfig


def test_runtime_identity_module_is_packaged() -> None:
    # Given: an installed localbench package import graph.
    # When: the C4 runtime identity module is resolved.
    spec = importlib.util.find_spec("localbench.appliance.runtime_identity")

    # Then: the module is package-visible without a source checkout.
    assert spec is not None


def _contract() -> dict[str, object]:
    # Ground truth: cli/src/localbench/data/contracts/
    # agentic-execution-contract-aw013p1-pypi28113a7a-v3.json.
    return load_execution_contract()


def _source_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    contract = _contract()
    payload = contract["payload"]
    assert isinstance(payload, dict)
    task_identity = payload["task_identity"]
    appworld_identity = payload["appworld_identity"]
    sandbox_identity = payload["sandbox_identity"]
    assert isinstance(task_identity, dict)
    assert isinstance(appworld_identity, dict)
    assert isinstance(sandbox_identity, dict)
    # Ground truth for manifest-only leaves: cli/tests/test_appliance_manifest.py:23-76.
    manifest = {
        "runtime_id": PINNED_RUNTIME_ID,
        "rootfs": {"sha256": "ab" * 32, "host_path": r"C:\machine-a\rootfs"},
        "worker": {
            "sha256": "ab" * 32,
            "protocol_version": AGENTIC_WORKER_PROTOCOL_VERSION,
        },
        "execution_contract_sha256": contract["payload_sha256"],
        "task_identity": {
            "ordered_task_ids_sha256": task_identity["ordered_task_ids_sha256"],
            "selection_recipe_sha256": task_identity["selection_recipe_sha256"],
        },
    }
    # Ground truth: appliance/worker.py handshake fields plus the signed contract above.
    handshake = {
        "runtime_id": PINNED_RUNTIME_ID,
        "protocol_version": AGENTIC_WORKER_PROTOCOL_VERSION,
        "python_version": appworld_identity["python_version"],
        "bubblewrap_version": sandbox_identity["bubblewrap_version"],
        "appworld_package_sha256": appworld_identity["appworld_package_sha256"],
        "appworld_data_sha256": appworld_identity["appworld_data_sha256"],
        "ordered_task_ids_sha256": task_identity["ordered_task_ids_sha256"],
        "selection_recipe_sha256": task_identity["selection_recipe_sha256"],
        "execution_contract_sha256": contract["payload_sha256"],
        "appworld_root": "/home/machine-a/appworld",
        "hostname": "machine-a",
    }
    # Ground truth: scoring/agentic_exec/worker_identity.py:47-50 and signed sandbox identity.
    worker_identity = {
        "localbench_distribution_version": "0.4.0",
        "worker_content_sha256": sandbox_identity["worker_content_sha256"],
    }
    return manifest, handshake, worker_identity


def _components() -> AgenticRuntimeIdentityComponents:
    manifest, handshake, worker_identity = _source_inputs()
    return agentic_runtime_identity_from_sources(
        manifest,
        handshake,
        worker_identity=worker_identity,
        execution_contract=_contract(),
    )


def test_identity_is_byte_identical_across_simulated_machines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: identical identity inputs on machines with different roots, hosts, and environments.
    first_root = tmp_path / "machine-a"
    second_root = tmp_path / "machine-b"
    first_root.mkdir()
    second_root.mkdir()
    monkeypatch.chdir(first_root)
    monkeypatch.setenv("HOME", str(first_root))
    monkeypatch.setattr(socket, "gethostname", lambda: "machine-a")

    # When: each machine builds the canonical identity string and digest.
    identity = agentic_runtime_identity_object(_components())
    first = canonical_agentic_runtime_identity(identity)
    first_digest = agentic_runtime_identity_sha256(identity)
    monkeypatch.chdir(second_root)
    monkeypatch.setenv("HOME", str(second_root))
    monkeypatch.setattr(socket, "gethostname", lambda: "machine-b")
    second_identity = agentic_runtime_identity_object(_components())
    second = canonical_agentic_runtime_identity(second_identity)
    second_digest = agentic_runtime_identity_sha256(second_identity)

    # Then: machine-local state has no effect on the bytes or digest.
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first_digest == second_digest


@pytest.mark.parametrize(
    "component_name",
    [
        "runtime_id",
        "rootfs_sha256",
        "worker_wheel_sha256",
        "worker_protocol_version",
        "python_version",
        "bubblewrap_version",
        "appworld_package_sha256",
        "appworld_data_sha256",
        "ordered_task_ids_sha256",
        "selection_recipe_sha256",
        "execution_contract_sha256",
        "localbench_distribution_version",
        "worker_content_sha256",
        "host_agent_loop_scorer_source_sha256",
    ],
)
def test_every_component_changes_identity_digest(component_name: str) -> None:
    # Given: the exact C4 component set and its baseline digest.
    components = _components()
    baseline = agentic_runtime_identity_sha256(
        agentic_runtime_identity_object(components)
    )

    # When: one component changes and every other component stays fixed.
    changed = replace(components, **{component_name: f"changed-{component_name}"})
    changed_digest = agentic_runtime_identity_sha256(
        agentic_runtime_identity_object(changed)
    )

    # Then: that component is identity-sensitive.
    assert changed_digest != baseline


def test_identity_object_contains_exactly_the_c4_components() -> None:
    # Given: a runtime identity built from the real contract and manifest fixture values.
    components = _components()

    # When: the public JSON object is exposed.
    identity = agentic_runtime_identity_object(components)

    # Then: no machine-local or general provenance fields enter the identity.
    assert set(identity) == {field.name for field in fields(components)}
    assert not {
        "git",
        "dirty_tree",
        "path",
        "hostname",
        "pid",
        "port",
        "timestamp",
        "env",
    } & set(identity)


def test_identity_build_succeeds_without_git_or_source_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an installed-wheel-shaped directory tree with no .git ancestor.
    installed = tmp_path / "site-packages" / "localbench"
    installed.mkdir(parents=True)
    monkeypatch.chdir(installed)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("identity must not invoke subprocess/git"),
    )

    # When: the identity is built and encoded.
    identity = agentic_runtime_identity_object(_components())
    encoded = canonical_agentic_runtime_identity(identity)

    # Then: construction succeeds without discovering or invoking git.
    assert len(agentic_runtime_identity_sha256(identity)) == 64
    assert encoded.startswith("{")


def test_identity_import_graph_has_no_git_state_usage() -> None:
    from localbench.appliance import runtime_identity
    from localbench.scoring.agentic_exec import execution_contract, worker_identity
    from localbench.submissions import canon

    # Given: every module directly imported to build and encode C4 identity.
    modules = (runtime_identity, execution_contract, worker_identity, canon)

    # When: their sources are inspected for the retired git-state identity operations.
    sources = "\n".join(inspect.getsource(module) for module in modules)

    # Then: neither rev-parse nor dirty-tree identity is reachable from this graph.
    assert "rev-parse" not in sources
    assert "dirty_tree" not in sources


def test_preflight_provenance_carries_identity_object_and_digest() -> None:
    # Given: a managed-worker preflight with the canonical C4 identity.
    identity = agentic_runtime_identity_object(_components())
    digest = agentic_runtime_identity_sha256(identity)
    preflight = WslPreflightResult(
        identity={},
        task_ids=("a30375d_1",),
        worker_config=WslWorkerConfig(
            venv_python="/opt/localbench/venv/bin/python",
            appworld_root="/home/lbworker/appworld",
        ),
        agentic_runtime_identity=identity,
        agentic_runtime_identity_sha256=digest,
    )

    # When: run-record provenance is assembled.
    provenance = preflight.provenance()

    # Then: both additive fields are carried unchanged.
    assert provenance["agentic_runtime_identity"] == identity
    assert provenance["agentic_runtime_identity_sha256"] == digest
