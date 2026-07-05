"""Release manifest construction for board_v1."""

from __future__ import annotations

from collections.abc import Sequence

from localbench._types import JsonObject
from localbench.scoring.board_scoring import item_set_hashes
from localbench.scoring.board_support import DATASET_VERSION, REPO_ROOT, file_sha256, git_commit, object_value, text_value
from localbench.scoring.board_types import ScoredRun
from localbench.scoring.scorecard import SCORECARD_VERSION, scorecard_identity


def release_manifest(
    scored: Sequence[ScoredRun],
    *,
    skipped: Sequence[JsonObject],
    generated_at: str,
    suite_version: str,
    index_version: str,
) -> JsonObject:
    scorecard = scorecard_identity()
    return {
        "suite_version": suite_version,
        "scoring_version": SCORECARD_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_version_note": "No standalone dataset version is exposed; suite item_set_hashes are the dataset pins.",
        "index_version": index_version,
        "item_set_hashes": item_set_hashes(scored),
        "scorer_git_commit": git_commit(),
        "reasoning_registry_hash": file_sha256(REPO_ROOT / "cli" / "src" / "localbench" / "reasoning_registry.py"),
        "extractor_version": None,
        "extractor_version_note": "No standalone answer-extractor version is exposed; scorer_versions carry scorer identity.",
        "generated_at": generated_at,
        "scorecard_id": text_value(scorecard.get("scorecard_id")),
        "scorecard_version": text_value(scorecard.get("scorecard_version")),
        "registry_digest": text_value(scorecard.get("registry_digest")),
        "profile_catalog_digest": text_value(scorecard.get("profile_catalog_digest")),
        "lane_spec_id": text_value(scorecard.get("lane_spec_id")),
        "lane_spec_digest": text_value(scorecard.get("lane_spec_digest")),
        "execution_profile_id": text_value(scorecard.get("execution_profile_id")),
        "execution_profile_digest": text_value(scorecard.get("execution_profile_digest")),
        "scorer_versions": object_value(scorecard.get("scorer_versions"), "scorecard.scorer_versions"),
        "ci_method": text_value(scorecard.get("ci_method")),
        "sampling_pins": {"temperature": 0, "top_p": None, "top_k": None, "min_p": None, "seed": None},
        "skipped_runs": list(skipped),
    }
