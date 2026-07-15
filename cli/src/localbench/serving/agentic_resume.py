from __future__ import annotations

import re
from collections.abc import Callable
from functools import partial

import httpx

from localbench._types import JsonObject
from localbench.appliance.runtime_identity import (
    AgenticRuntimeIdentityError,
    agentic_runtime_identity_sha256,
)
from localbench.scoring.agentic_exec.task_journal import AgenticResumeSeed
from localbench.scoring.agentic_exec.wsl_bridge import WslPreflightResult
from localbench.serving.agentic_support import AgenticSetupError
from localbench.serving.provenance import ServingEvidence
from localbench.submissions.canon import canonical_json_bytes


def build_agentic_resume_seed(
    *,
    agentic_runtime_identity: JsonObject | None,
    agentic_runtime_identity_digest: str | None,
    model_sha256: str,
    normalized_server_identity: str,
    lane: str,
    profile: str,
    wsl_kernel: str,
    gpu_architecture: str | None,
    driver_version: str | None,
    cuda_version: str | None,
    runtime_name: str,
    runtime_version: str | None,
) -> AgenticResumeSeed:
    if agentic_runtime_identity is None or agentic_runtime_identity_digest is None:
        raise AgenticSetupError(detail="managed preflight omitted the C4 runtime identity")
    observed_digest = agentic_runtime_identity_sha256(agentic_runtime_identity)
    if observed_digest != agentic_runtime_identity_digest:
        raise AgenticRuntimeIdentityError(
            "agentic_runtime_identity_sha256",
            agentic_runtime_identity_digest,
            observed_digest,
        )
    host_digest = _required_text(
        agentic_runtime_identity,
        "host_agent_loop_scorer_source_sha256",
    )
    return AgenticResumeSeed(
        agentic_runtime_identity_sha256=agentic_runtime_identity_digest,
        model_sha256=_required_value(model_sha256, "model_sha256"),
        normalized_server_identity=_required_value(
            normalized_server_identity,
            "normalized_server_identity",
        ),
        host_loop_scorer_contract_digest=host_digest,
        lane=_required_value(lane, "lane"),
        profile=_required_value(profile, "profile"),
        wsl_kernel_family=normalize_wsl_kernel_family(wsl_kernel),
        gpu_architecture=_required_value(gpu_architecture, "gpu_architecture"),
        driver_runtime_family=canonical_json_bytes(
            {
                "driver": driver_version or "unavailable",
                "cuda": cuda_version or "unavailable",
                "runtime": runtime_name,
                "runtime_version": runtime_version or "unavailable",
            }
        ).decode("utf-8"),
    )


def build_agentic_resume_seed_from_runtime(
    *,
    preflight: WslPreflightResult,
    evidence: ServingEvidence,
    lane: str,
    profile: str,
) -> AgenticResumeSeed:
    wsl_kernel = preflight.identity.get("wsl_kernel")
    try:
        return build_agentic_resume_seed(
            agentic_runtime_identity=preflight.agentic_runtime_identity,
            agentic_runtime_identity_digest=preflight.agentic_runtime_identity_sha256,
            model_sha256=evidence.artifact.file_sha256,
            normalized_server_identity=evidence.resume_identity,
            lane=lane,
            profile=profile,
            wsl_kernel=wsl_kernel if isinstance(wsl_kernel, str) else "",
            gpu_architecture=evidence.device_name,
            driver_version=evidence.driver_version,
            cuda_version=evidence.cuda_version,
            runtime_name=evidence.runtime,
            runtime_version=evidence.engine_version or evidence.version_stdout,
        )
    except AgenticRuntimeIdentityError as error:
        raise AgenticSetupError(detail=str(error)) from None


def agentic_runtime_revalidator(
    *,
    endpoint: str,
    model_id: str,
    api_key: str,
) -> Callable[[], None]:
    return partial(
        revalidate_agentic_server,
        endpoint=endpoint,
        model_id=model_id,
        api_key=api_key,
    )


def normalize_wsl_kernel_family(kernel: str) -> str:
    value = _required_value(kernel, "wsl_kernel")
    version = re.match(r"^(\d+)\.(\d+)", value)
    if version is None:
        raise AgenticSetupError(detail=f"managed preflight reported an invalid WSL kernel: {value!r}")
    suffix = "microsoft-standard-WSL2" if "microsoft" in value.casefold() else "linux"
    return f"{version.group(1)}.{version.group(2)}-{suffix}"


def revalidate_agentic_server(
    *,
    endpoint: str,
    model_id: str,
    api_key: str,
) -> None:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(
            f"{endpoint.rstrip('/')}/models",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise AgenticSetupError(
            detail=f"post-sleep server/runtime revalidation failed: {error}"
        ) from error
    data = payload.get("data") if isinstance(payload, dict) else None
    models = [item.get("id") for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    if model_id not in models:
        raise AgenticSetupError(
            detail=(
                "post-sleep server/runtime revalidation failed: "
                f"expected model {model_id!r}, observed {models!r}"
            )
        )


def _required_text(source: JsonObject, key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise AgenticRuntimeIdentityError(key, "non-empty string", repr(value))
    return value


def _required_value(value: str | None, component: str) -> str:
    if value is None or not value:
        raise AgenticSetupError(detail=f"agentic resume identity is missing {component}")
    return value
