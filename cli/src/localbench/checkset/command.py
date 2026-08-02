from __future__ import annotations

from pathlib import Path

from localbench.checkset.build import build_t2_scaffold
from localbench.checkset.models import JsonObject, ModuleRecord
from localbench.checkset.sources import build_local_modules
from localbench.checkset.upstream import (
    GPQA_CONFIG,
    GPQA_REPO,
    GPQA_REVISION,
    OLYMMATH_MEDIUM_CONFIG,
    OLYMMATH_REPO,
    OLYMMATH_REVISION,
    UpstreamError,
    fetch_gpqa,
    fetch_math_medium,
)


def build_command(repo_root: Path, output: Path, *, offline_upstream: bool) -> tuple[int, str]:
    local_modules, exclusions = build_local_modules(repo_root)
    pending = ["tools-stateful", "sanity-gates"]
    modules: tuple[ModuleRecord, ...] = local_modules
    metadata: JsonObject = {
        "gpqa": {"repository": GPQA_REPO, "config": GPQA_CONFIG, "revision": GPQA_REVISION},
        "math_medium": {
            "repository": OLYMMATH_REPO,
            "config": OLYMMATH_MEDIUM_CONFIG,
            "revision": OLYMMATH_REVISION,
        },
    }
    knowledge_status = "pending_fetch"
    knowledge_error: str | None = "offline upstream mode"
    if offline_upstream:
        pending = ["knowledge", "math-medium", *pending]
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
            fetch_math_medium()
        except UpstreamError as error:
            pending.insert(0, "math-medium")
            math_metadata = metadata["math_medium"]
            if isinstance(math_metadata, dict):
                math_metadata["status"] = "blocked_locked_source_gap"
                math_metadata["error"] = str(error)
        else:
            raise UpstreamError(OLYMMATH_REPO, "medium rows unexpectedly became available; combine step requires T2 re-review")
    build_t2_scaffold(
        output,
        modules=modules,
        knowledge_status=knowledge_status,
        knowledge_error=knowledge_error,
        pool_exclusions=exclusions,
        pending_dependencies=pending,
        source_metadata=metadata,
    )
    detail = ", ".join(pending)
    return 2, f"wrote deterministic T2 scaffold to {output}; pending: {detail}"
