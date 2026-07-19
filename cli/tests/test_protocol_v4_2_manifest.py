from __future__ import annotations

import json
from pathlib import Path

from localbench.scoring.axes import AXES
from localbench.submissions.canon import canonical_json_hash
from localbench.submissions.contracts import ACCEPTED_RESULT_PROJECTION_SCHEMA, load_schema
from localbench.suite_release import build_suite_release_manifest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "protocol" / "index-v4.2.json"


def _manifest() -> dict[str, object]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_protocol_v4_2_manifest_hash_covers_its_canonical_payload() -> None:
    manifest = _manifest()
    recorded = manifest.pop("canonical_sha256")

    assert recorded == canonical_json_hash(manifest)


def test_protocol_v4_2_registry_axes_weights_membership_roles_and_facets_do_not_drift() -> None:
    manifest_axes = _manifest()["axes"]
    actual = [
        {
            "key": axis.key,
            "display": axis.display,
            "web_key": axis.web_key,
            "benches": list(axis.benches),
            "legacy_benches": list(axis.legacy_benches),
            "role": axis.role,
            "weight": axis.weight,
            "web_display": axis.web_display,
            "facets": [
                {"key": facet.key, "bench": facet.bench, "weight": facet.weight}
                for facet in axis.facets
            ],
        }
        for axis in AXES
    ]

    assert actual == manifest_axes


def test_protocol_v4_2_diagnostics_never_enter_headline_axes() -> None:
    manifest = _manifest()
    axes = manifest["axes"]
    headline_benches = {
        bench
        for axis in axes
        if axis["role"] == "headline"
        for bench in axis["benches"]
    }
    diagnostic_benches = {diagnostic["bench"] for diagnostic in manifest["diagnostics"]}

    assert headline_benches.isdisjoint(diagnostic_benches)
    assert all(axis["benches"] for axis in axes if axis["role"] == "headline")


def test_protocol_v4_2_public_suite_membership_is_conformant_and_complete() -> None:
    manifest = _manifest()
    release = build_suite_release_manifest(
        _REPO_ROOT / "suite" / "v1",
        coverage_profile_id="full-exec-6axis-v1",
    )
    release_benches = {
        bench
        for benches in release["axis_membership"].values()
        for bench in benches
    }
    protocol_benches = {
        bench
        for axis in manifest["axes"]
        for bench in axis["benches"]
    }
    headline_benches = {
        bench
        for axis in manifest["axes"]
        if axis["role"] == "headline"
        for bench in axis["benches"]
    }

    assert release["suite_release_id"] == "suite-v1-full-exec-6axis-v1"
    assert release_benches <= protocol_benches
    assert headline_benches <= release_benches


def test_protocol_v4_2_agentic_denominator_is_version_pinned() -> None:
    manifest = _manifest()
    agentic = manifest["agentic_protocol"]

    assert manifest["protocol_id"] == "index-v4.2"
    assert agentic["task_denominator"] == 96
    assert agentic["selection_version"] == "v1"
    assert agentic["split"] == "test_normal"
    assert agentic["seed"] == 20260624
    assert len(agentic["subset_sha256"]) == 64
    assert len(agentic["ordered_task_ids_sha256"]) == 64


def test_protocol_v4_2_is_admitted_without_removing_historical_projection_labels() -> None:
    schema = load_schema(ACCEPTED_RESULT_PROJECTION_SCHEMA)
    versions = schema["properties"]["index_version"]["enum"]

    assert versions == ["index-v3.0", "index-v4.0", "index-v4.1", "index-v4.2"]
