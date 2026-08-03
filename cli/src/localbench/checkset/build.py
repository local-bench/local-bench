from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from localbench.checkset.manifest_validation import validate_manifest_inputs
from localbench.checkset.models import ChecksetBuildError, JsonObject, JsonValue, ModuleRecord
from localbench.checkset.policy import policy_blocks
from localbench.submissions.canon import canonical_json_bytes

SPEC_SHA256: Final = "d8bbf9c6d5bb96c82c9827dc7e736cceaa2a1876b8ae1e9c0ee305b65b608629"
LOCKED_UTC: Final = "2026-08-03T00:00:00Z"
REVIEWED_BY: Final = "orchestrator"
REVIEWED_LOCAL: Final = "2026-08-03"
SUPERSEDES: Final[JsonObject] = {
    "previous_frozen_sha256": "177f3fa9ce8149026438ffed1777d62adea0e8dfd9d99721ff4fc4258ce24ef8",
    "reason": "pre-validation wording correction from smoke evidence (budget-control-02 named its answer ambiguously); zero scored results exist",
    "corrected_local": "2026-08-04",
}


def build_t2_scaffold(
    output: Path,
    *,
    modules: Sequence[ModuleRecord],
    knowledge_status: str,
    knowledge_error: str | None,
    pool_exclusions: Sequence[JsonObject] = (),
    pending_dependencies: Sequence[str] = ("tools-stateful", "sanity-gates"),
    source_metadata: JsonObject | None = None,
    stateful: JsonObject | None = None,
    sanity_gates: JsonObject | None = None,
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
            "stateful": stateful or {"status": "pending_t3", "templates": [], "instances": [], "spares_ordered": [], "cluster_map": {}},
            "sanity_gates": sanity_gates or {"status": "pending_t3", "definitions": []},
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
    sanity_gates: JsonObject,
    source_metadata: JsonObject,
    pool_exclusions: Sequence[JsonObject] = (),
    freeze: bool = False,
    reviewed_draft_sha: str | None = None,
) -> JsonObject:
    validate_manifest_inputs(
        modules=modules,
        stateful=stateful,
        sanity_gates=sanity_gates,
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
            "sanity_gates": sanity_gates,
            "source_metadata": source_metadata,
            "preregistration": {"spec_sha256": SPEC_SHA256, "locked_utc": LOCKED_UTC},
        }
    )
    if freeze:
        document = _freeze_reviewed_draft(document, reviewed_draft_sha)
    _write_canonical(output, document, sidecar=True)
    return document


def _freeze_reviewed_draft(document: JsonObject, reviewed_draft_sha: str | None) -> JsonObject:
    reviewed_draft_sha = validate_reviewed_draft_sha(reviewed_draft_sha)
    draft_sha256 = hashlib.sha256(_canonical_bytes(document)).hexdigest()
    if draft_sha256 != reviewed_draft_sha:
        raise ChecksetBuildError(
            "refusing to freeze unreviewed check-set-v1 draft: "
            f"fresh sha256 {draft_sha256} does not match reviewed {reviewed_draft_sha}"
        )
    frozen = dict(document)
    frozen.update(
        {
            "draft": False,
            "review": {
                "draft_sha256": reviewed_draft_sha,
                "reviewed_by": REVIEWED_BY,
                "reviewed_local": REVIEWED_LOCAL,
            },
            "status": "frozen",
            "supersedes": dict(SUPERSEDES),
        }
    )
    return frozen


def validate_reviewed_draft_sha(reviewed_draft_sha: str | None) -> str:
    if reviewed_draft_sha is None or re.fullmatch(r"[0-9a-fA-F]{64}", reviewed_draft_sha) is None:
        raise ChecksetBuildError("reviewed draft sha256 must be a 64-character hexadecimal value")
    return reviewed_draft_sha.lower()


def _canonical_bytes(document: JsonValue) -> bytes:
    return canonical_json_bytes(document) + b"\n"


def _write_canonical(output: Path, document: JsonValue, *, sidecar: bool) -> None:
    data = _canonical_bytes(document)
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_bytes(data)
    if sidecar:
        digest = hashlib.sha256(data).hexdigest()
        _ = output.with_name(f"{output.name}.sha256").write_text(
            f"{digest}  {output.name}\n",
            encoding="ascii",
            newline="\n",
        )
