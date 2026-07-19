from __future__ import annotations

from localbench._types import JsonObject


def coding_item_fully_graded(item: JsonObject) -> bool:
    artifact = item.get("code_artifact")
    if not isinstance(artifact, dict):
        return False
    verdict = artifact.get("verdict")
    image = artifact.get("image_digest")
    if (
        artifact.get("verdict_source") == "verifier"
        and isinstance(verdict, dict)
        and isinstance(verdict.get("passed"), bool)
        and isinstance(image, str)
        and "@sha256:" in image
    ):
        return True
    extraction = artifact.get("extraction_status")
    if (
        isinstance(extraction, dict)
        and isinstance(extraction.get("status"), str)
        and extraction["status"] != "ok"
        and verdict is None
        and artifact.get("verdict_source") is None
    ):
        return True
    scoring = item.get("client_scoring")
    failure_kind = item.get("failure_kind")
    if not isinstance(failure_kind, str) and isinstance(scoring, dict):
        failure_kind = scoring.get("failure_kind")
    conformance = artifact.get("conformance_status")
    return (
        failure_kind == "coding_ast_rejected"
        and isinstance(conformance, dict)
        and conformance.get("failure") == "coding_ast_rejected"
    )
