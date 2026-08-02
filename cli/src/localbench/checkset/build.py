from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from localbench.checkset.manifest_validation import validate_manifest_inputs
from localbench.checkset.models import JsonObject, JsonValue, ModuleRecord
from localbench.checkset.policy import policy_blocks
from localbench.submissions.canon import canonical_json_bytes

SPEC_SHA256: Final = "d8bbf9c6d5bb96c82c9827dc7e736cceaa2a1876b8ae1e9c0ee305b65b608629"
LOCKED_UTC: Final = "2026-08-03T00:00:00Z"
def build_t2_scaffold(
    output: Path,
    *,
    modules: Sequence[ModuleRecord],
    knowledge_status: str,
    knowledge_error: str | None,
    pool_exclusions: Sequence[JsonObject] = (),
    pending_dependencies: Sequence[str] = ("tools-stateful", "sanity-gates"),
    source_metadata: JsonObject | None = None,
) -> JsonObject:
    document = policy_blocks()
    document.update(
        {
            "schema_version": "localbench-check-set-manifest-v1",
            "edition": "check-set-v1",
            "draft": True,
            "status": "pending_dependencies",
            "pending_dependencies": list(pending_dependencies),
            "modules": [module.as_json() for module in modules],
            "knowledge": {"status": knowledge_status, "error": knowledge_error},
            "pool_exclusions": list(pool_exclusions),
            "stateful": {"status": "pending_t3", "templates": [], "instances": [], "spares_ordered": [], "cluster_map": {}},
            "preregistration": {"spec_sha256": SPEC_SHA256, "locked_utc": LOCKED_UTC},
            "source_metadata": source_metadata or {},
        }
    )
    _write_canonical(output, document, sidecar=False)
    return document


def emit_manifest(
    output: Path,
    *,
    modules: Sequence[ModuleRecord],
    stateful: JsonObject,
    source_metadata: JsonObject,
    pool_exclusions: Sequence[JsonObject] = (),
) -> JsonObject:
    validate_manifest_inputs(
        modules=modules,
        stateful=stateful,
        source_metadata=source_metadata,
        pool_exclusions=pool_exclusions,
    )
    document = policy_blocks()
    document.update(
        {
            "schema_version": "localbench-check-set-manifest-v1",
            "edition": "check-set-v1",
            "draft": True,
            "status": "complete-draft",
            "modules": [module.as_json() for module in modules],
            "pool_exclusions": list(pool_exclusions),
            "stateful": stateful,
            "source_metadata": source_metadata,
            "preregistration": {"spec_sha256": SPEC_SHA256, "locked_utc": LOCKED_UTC},
        }
    )
    _write_canonical(output, document, sidecar=True)
    return document


def _write_canonical(output: Path, document: JsonValue, *, sidecar: bool) -> None:
    data = canonical_json_bytes(document) + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    if sidecar:
        digest = hashlib.sha256(data).hexdigest()
        output.with_name(f"{output.name}.sha256").write_text(
            f"{digest}  {output.name}\n",
            encoding="ascii",
            newline="\n",
        )
