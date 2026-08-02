from __future__ import annotations

from pathlib import Path

from localbench.check.power import build_mde_artifact
from localbench.checkset.input_runs import read_json
from localbench.submissions.canon import canonical_json_bytes


def test_mde_artifact_is_deterministic_labeled_and_matches_checked_in_copy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = read_json(repo_root / "checkset" / "check-set-v1.manifest.json")

    first = build_mde_artifact(manifest, simulations=2_000)
    second = build_mde_artifact(manifest, simulations=2_000)

    assert first == second
    assert first["published_mde_label"] == "simulation-derived"
    assert first["approximation_label"] == "unadjusted marginal approximation"
    checked_in = read_json(repo_root / "checkset" / "check-set-v1.mde.json")
    assert canonical_json_bytes(first) == canonical_json_bytes(checked_in)
