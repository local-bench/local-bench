from __future__ import annotations

from pathlib import Path

from localbench.checkset.build import build_t2_scaffold, emit_manifest
from localbench.checkset.gates import build_sanity_gates
from localbench.checkset.models import JsonObject, ModuleRecord
from localbench.checkset.sources import build_local_modules
from localbench.checkset.stateful import build_stateful
from localbench.checkset.upstream import (
    GPQA_CONFIG,
    GPQA_REPO,
    GPQA_REVISION,
    OLYMMATH_AIME_CONFIG,
    OLYMMATH_REPO,
    OLYMMATH_REVISION,
    UpstreamError,
    combine_math_module,
    fetch_gpqa,
    fetch_math_aime,
)


def build_command(repo_root: Path, output: Path, *, offline_upstream: bool) -> tuple[int, str]:
    local_modules, exclusions = build_local_modules(repo_root)
    stateful_module, stateful = build_stateful(repo_root)
    gates_module, sanity_gates = build_sanity_gates(repo_root)
    pending: list[str] = []
    modules: tuple[ModuleRecord, ...] = (*local_modules, stateful_module, gates_module)
    metadata: JsonObject = {
        "gpqa": {"repository": GPQA_REPO, "config": GPQA_CONFIG, "revision": GPQA_REVISION},
        "math_aime": {
            "repository": OLYMMATH_REPO,
            "config": OLYMMATH_AIME_CONFIG,
            "revision": OLYMMATH_REVISION,
        },
    }
    knowledge_status = "pending_fetch"
    knowledge_error: str | None = "offline upstream mode"
    if offline_upstream:
        pending = ["knowledge", "math-aime", *pending]
    else:
        try:
            knowledge, canary_log = fetch_gpqa()
        except UpstreamError as error:
            pending.insert(0, "knowledge")
            knowledge_error = str(error)
        else:
            modules = (knowledge, *modules)
            knowledge_status = "ready"
            knowledge_error = None
            metadata["gpqa_canary_strip_log"] = list(canary_log)
        try:
            aime = fetch_math_aime()
        except UpstreamError as error:
            pending.insert(0, "math-aime")
            math_metadata = metadata["math_aime"]
            if isinstance(math_metadata, dict):
                math_metadata["status"] = "fetch_failed"
                math_metadata["error"] = str(error)
        else:
            legacy = next(module for module in modules if module.name == "math-legacy")
            math = combine_math_module(legacy, aime)
            modules = tuple(math if module.name == "math-legacy" else module for module in modules)
            math_metadata = metadata["math_aime"]
            if isinstance(math_metadata, dict):
                math_metadata["selected"] = [
                    {
                        "content_sha256": item.content_sha256,
                        "subject": item.subject,
                        "upstream_index": item.upstream_index,
                    }
                    for item in aime
                ]
    if not pending:
        _ = emit_manifest(
            output,
            modules=modules,
            stateful=stateful,
            sanity_gates=sanity_gates,
            source_metadata=metadata,
            pool_exclusions=exclusions,
        )
        return 0, f"wrote deterministic complete draft to {output}"
    _ = build_t2_scaffold(
        output,
        modules=modules,
        knowledge_status=knowledge_status,
        knowledge_error=knowledge_error,
        pool_exclusions=exclusions,
        pending_dependencies=pending,
        source_metadata=metadata,
        stateful=stateful,
        sanity_gates=sanity_gates,
    )
    detail = ", ".join(pending)
    return 2, f"wrote deterministic T2 scaffold to {output}; pending: {detail}"
