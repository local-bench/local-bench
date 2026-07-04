from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "web"))

import build_data  # noqa: E402
from localbench.scoring.scorecard import registry_digest, scorecard_identity  # noqa: E402


def test_scorecard_detail_separates_full_drift_from_registry_drift() -> None:
    current = scorecard_identity()
    current_id = current["scorecard_id"]
    current_registry = registry_digest()

    # Recorded under the CURRENT scorecard -> no drift of any kind.
    fresh = build_data._scorecard_detail(
        {"scorecard_id": current_id, "scorecard_version": "scorecard-v1.2", "registry_digest": current_registry}
    )
    assert fresh["drift"] is False
    assert fresh["registry_drift"] is False
    assert fresh["current_id"] == current_id

    # Same registry but a DIFFERENT scorecard id (e.g. a scorer-version bump) -> full
    # drift flagged, but the displayed composite is NOT a re-score (weights unchanged).
    scorer_changed = build_data._scorecard_detail(
        {"scorecard_id": "different", "registry_digest": current_registry}
    )
    assert scorer_changed["drift"] is True
    assert scorer_changed["registry_drift"] is False

    # Different registry -> both flags: the displayed composite IS a re-score.
    reweighted = build_data._scorecard_detail(
        {"scorecard_id": "different", "registry_digest": "0" * 64}
    )
    assert reweighted["drift"] is True
    assert reweighted["registry_drift"] is True

    # Pre-scorecard run (no recorded identity) -> unknown provenance, not a false drift.
    unknown = build_data._scorecard_detail({})
    assert unknown["drift"] is False
    assert unknown["registry_drift"] is False
    assert unknown["id"] is None


def test_contamination_label_keys_on_release_vs_suite_publication_date() -> None:
    # Released before the suite froze -> could not have been tuned to game THIS suite.
    assert build_data._contamination_label("2025-01-01") == "pre-suite-publication"
    # Released after -> possible contamination of our frozen subset (a flag, not proof).
    assert build_data._contamination_label("2027-01-01") == "post-suite-publication"
    # Unknown or unparseable date -> unverified (the default).
    assert build_data._contamination_label(None) == "unverified"
    assert build_data._contamination_label("not-a-date") == "unverified"
    # Boundary: exactly the publication date is NOT strictly before -> post.
    assert build_data._contamination_label(build_data.SUITE_V1_PUBLISHED.isoformat()) == "post-suite-publication"
