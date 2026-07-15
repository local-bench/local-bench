from __future__ import annotations

import pytest

from localbench.appliance.runtime_identity import (
    agentic_runtime_identity_object,
    agentic_runtime_identity_sha256,
)
from localbench.serving.agentic_resume import (
    build_agentic_resume_seed,
    normalize_wsl_kernel_family,
)
from test_appliance_runtime_identity import _components


def test_resume_seed_uses_c4_serving_wsl_gpu_and_driver_runtime_sources() -> None:
    # Given: the real C4 identity fixture and observed managed-serving components.
    runtime_identity = agentic_runtime_identity_object(_components())

    # When: the run-start seed and task-specific identity are built.
    seed = build_agentic_resume_seed(
        agentic_runtime_identity=runtime_identity,
        agentic_runtime_identity_digest=agentic_runtime_identity_sha256(runtime_identity),
        model_sha256="b" * 64,
        normalized_server_identity="c" * 64,
        lane="bounded-final-v2",
        profile="generic_think_tags_8192_v1",
        wsl_kernel="6.6.87.2-microsoft-standard-WSL2",
        gpu_architecture="NVIDIA RTX 4090",
        driver_version="600.1",
        cuda_version="13.0",
        runtime_name="vllm",
        runtime_version="0.24.0",
    )
    identity = seed.build(
        task_set_sha256="e" * 64,
        sampling={"temperature": 0.0, "top_p": 1.0, "seed": 1234},
    )

    # Then: every frozen resume component is present with no ephemeral machine state.
    assert identity.agentic_runtime_identity_sha256 == agentic_runtime_identity_sha256(
        runtime_identity
    )
    assert identity.host_loop_scorer_contract_digest == _components().host_agent_loop_scorer_source_sha256
    assert identity.wsl_kernel_family == "6.6-microsoft-standard-WSL2"
    assert identity.gpu_architecture == "NVIDIA RTX 4090"
    assert identity.driver_runtime_family == (
        '{"cuda":"13.0","driver":"600.1","runtime":"vllm","runtime_version":"0.24.0"}'
    )
    encoded = str(identity.as_dict())
    for forbidden in ("port", "pid", "timestamp", "C:\\", "/mnt/"):
        assert forbidden not in encoded.casefold()


def test_wsl_kernel_normalization_is_patch_count_agnostic() -> None:
    # Given / When: two patch releases from the same WSL2 kernel family are normalized.
    first = normalize_wsl_kernel_family("6.6.87.1-microsoft-standard-WSL2")
    second = normalize_wsl_kernel_family("6.6.99.9-microsoft-standard-WSL2")

    # Then: patch-only drift does not create a false resume mismatch.
    assert first == second == "6.6-microsoft-standard-WSL2"


@pytest.mark.parametrize(
    ("runtime_name", "gpu_evidence"),
    [
        (
            "llama.cpp",
            "Available devices:\nCUDA0: NVIDIA GeForce RTX 4090 (24564 MiB, 21731 MiB free)",
        ),
        ("vllm", "NVIDIA GeForce RTX 4090"),
        ("sglang", "NVIDIA GeForce RTX 4090"),
    ],
)
def test_resume_identity_excludes_volatile_gpu_memory_evidence(
    runtime_name: str,
    gpu_evidence: str,
) -> None:
    # Given: each serving lane's device evidence shape, including volatile llama.cpp free VRAM.
    runtime_identity = agentic_runtime_identity_object(_components())

    # When: the persisted resume identity is assembled.
    identity = build_agentic_resume_seed(
        agentic_runtime_identity=runtime_identity,
        agentic_runtime_identity_digest=agentic_runtime_identity_sha256(runtime_identity),
        model_sha256="b" * 64,
        normalized_server_identity="c" * 64,
        lane="bounded-final-v2",
        profile="generic_think_tags_8192_v1",
        wsl_kernel="6.6.87.2-microsoft-standard-WSL2",
        gpu_architecture=gpu_evidence,
        driver_version="600.1",
        cuda_version="13.0",
        runtime_name=runtime_name,
        runtime_version="fixture",
    ).build(
        task_set_sha256="e" * 64,
        sampling={"temperature": 0.0, "top_p": 1.0, "seed": 1234},
    )

    # Then: only the stable device name enters every resume-identity component.
    assert identity.gpu_architecture == "NVIDIA GeForce RTX 4090"
    encoded = str(identity.as_dict())
    assert "24564" not in encoded
    assert "21731" not in encoded
    assert "MiB" not in encoded
