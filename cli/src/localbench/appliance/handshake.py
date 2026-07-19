from __future__ import annotations

from localbench._types import JsonObject
from localbench.appliance.manifest import REQUIRED_CRITICAL_HASHES
from localbench.appliance.runtime_identity import (
    agentic_runtime_identity_from_sources,
    agentic_runtime_identity_object,
    agentic_runtime_identity_sha256,
)


def accept_handshake_identity(manifest: JsonObject, identity: JsonObject) -> JsonObject:
    from localbench.appliance.provisioner import ProvisioningError

    expected_hashes = _json_object(manifest, "critical_hashes")
    observed_hashes = identity.get("critical_hashes")
    if not isinstance(observed_hashes, dict) or set(observed_hashes) != set(
        REQUIRED_CRITICAL_HASHES
    ):
        raise ProvisioningError(
            "critical_hash_set_invalid", "worker set differs", "Reprovision"
        )
    if observed_hashes != expected_hashes:
        raise ProvisioningError(
            "runtime_mutated", "critical hash mismatch", "Reprovision"
        )
    if identity.get("execution_contract_sha256") != manifest.get(
        "execution_contract_sha256"
    ):
        raise ProvisioningError(
            "execution_contract_mismatch", "worker contract differs", "Reprovision"
        )
    tasks = _json_object(manifest, "task_identity")
    for field in (
        "ordered_task_ids_sha256",
        "selection_recipe_sha256",
        "semantic_task_sha256",
    ):
        if identity.get(field) != tasks.get(field):
            raise ProvisioningError("task_contract_mismatch", field, "Reprovision")
    worker = _json_object(manifest, "worker")
    required = {
        "runtime_id": manifest["runtime_id"],
        "protocol_version": worker["protocol_version"],
        "uid": "lbworker",
        "gid": "lbworker",
        "mnt_c_absent": True,
        "interop_blocked": True,
        "windows_path_absent": True,
    }
    for field, expected in required.items():
        if identity.get(field) != expected:
            raise ProvisioningError("runtime_identity_mismatch", field, "Reprovision")
    expected_python = str(_json_object(manifest, "python")["version"])
    if identity.get("python_version") != expected_python:
        raise ProvisioningError(
            "runtime_identity_mismatch", "python_version", "Reprovision"
        )
    expected_bubblewrap = str(_json_object(manifest, "bubblewrap")["version"])
    if identity.get("bubblewrap_version") not in {
        expected_bubblewrap,
        f"bubblewrap {expected_bubblewrap}",
    }:
        raise ProvisioningError(
            "runtime_identity_mismatch", "bubblewrap_version", "Reprovision"
        )
    for field, critical_field in (
        ("appworld_package_sha256", "appworld_installed_tree_sha256"),
        ("appworld_data_sha256", "appworld_data_tree_sha256"),
    ):
        if identity.get(field) != expected_hashes.get(critical_field):
            raise ProvisioningError("runtime_identity_mismatch", field, "Reprovision")
    components = agentic_runtime_identity_from_sources(manifest, identity)
    runtime_identity = agentic_runtime_identity_object(components)
    identity["agentic_runtime_identity"] = runtime_identity
    identity["agentic_runtime_identity_sha256"] = agentic_runtime_identity_sha256(
        runtime_identity
    )
    return identity


def _json_object(source: JsonObject, key: str) -> JsonObject:
    value = source.get(key)
    if not isinstance(value, dict):
        from localbench.appliance.provisioner import ProvisioningError

        raise ProvisioningError("manifest_invalid", key, "Reprovision")
    return value
