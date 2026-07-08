from __future__ import annotations

import json
from pathlib import Path

import pytest

from localbench.one_shot.catalog import (
    CatalogArtifactConflictError,
    CatalogResolutionError,
    resolve_one_shot_model,
)
from localbench.one_shot.preflight import (
    OneShotChoiceError,
    PlanLockMismatch,
    build_identity_envelope,
    build_publishability_preflight_payload,
    prevalidate_identity_envelope,
    request_publishability_preflight,
    validate_one_shot_choices,
    validate_resume_plan_lock,
    write_plan_lock,
)
from localbench.one_shot.types import FULL_EXEC_SUITE_MANIFEST_SHA256, FULL_EXEC_SUITE_RELEASE_ID
from one_shot_fixtures import REV_A, REV_B, SHA_A, catalog_with_artifacts


def test_catalog_resolve_fails_closed_when_publishable_entry_lacks_immutable_hf_pin() -> None:
    catalog = {
        "models": [
            {
                "slug": "qwen3-6-27b",
                "catalog_id": "Qwen/Qwen3.6-27B",
                "family": "Qwen3.6",
                "gguf_repo": "unsloth/Qwen3.6-27B-MTP-GGUF",
                "runs": [{"quant_label": "Q4_K_M", "file_gb": 17.1, "vram_required_gb_8k": 19.5}],
            },
        ],
    }

    with pytest.raises(CatalogResolutionError, match="immutable HF artifact"):
        resolve_one_shot_model("qwen3-6-27b", catalog, quant="Q4_K_M", vram_gb=24.0)


def test_artifact_facts_take_precedence_and_conflicting_catalog_metadata_aborts() -> None:
    catalog = catalog_with_artifacts(
        artifacts=[
            {
                "quant_label": "Q4_K_M",
                "repo_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
                "filename": "qwen3-q4.gguf",
                "revision": REV_A,
                "sha256": SHA_A,
                "size_bytes": 1024,
                "vram_required_gb_8k": 19.5,
            },
        ],
        runs=[{"quant_label": "Q4_K_M", "file_size_bytes": 2048}],
    )

    with pytest.raises(CatalogArtifactConflictError, match="file_size_bytes"):
        resolve_one_shot_model("qwen3-6-27b", catalog, quant="Q4_K_M", vram_gb=24.0)


def test_catalog_resolve_selects_best_pinned_quant_that_fits_vram_budget() -> None:
    catalog = catalog_with_artifacts(
        artifacts=[
            {
                "quant_label": "Q6_K",
                "repo_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
                "filename": "qwen3-q6.gguf",
                "revision": REV_A,
                "sha256": SHA_A,
                "size_bytes": 3072,
                "vram_required_gb_32k": 29.0,
            },
            {
                "quant_label": "Q4_K_M",
                "repo_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
                "filename": "qwen3-q4.gguf",
                "revision": REV_B,
                "sha256": "2" * 64,
                "size_bytes": 2048,
                "vram_required_gb_32k": 22.0,
            },
        ],
    )

    resolved = resolve_one_shot_model("qwen3-6-27b", catalog, quant=None, vram_gb=24.0)

    assert resolved.catalog_model_id == "Qwen/Qwen3.6-27B"
    assert resolved.artifact.quant_label == "Q4_K_M"
    assert resolved.artifact.model_ref == f"hf://unsloth/Qwen3.6-27B-MTP-GGUF@{REV_B}#qwen3-q4.gguf"
    assert resolved.local_only is False
    assert resolved.publishable is True


def test_raw_hf_repo_resolves_local_only_for_0_3_0_scope() -> None:
    resolved = resolve_one_shot_model("owner/raw-gguf-repo", {"models": []}, quant="Q4_K_M", vram_gb=24.0)

    assert resolved.local_only is True
    assert resolved.publishable is False
    assert any("raw HF" in reason for reason in resolved.blocking_reasons)


def test_non_tty_one_shot_requires_explicit_submit_choice() -> None:
    with pytest.raises(OneShotChoiceError, match="--submit or --no-submit"):
        validate_one_shot_choices(
            is_tty=False,
            yes=True,
            submit_choice=None,
            accept_suite_terms=True,
            vram_gb=24.0,
            quant="Q4_K_M",
            vram_detected=False,
            offline=False,
        )


def test_offline_mode_rejects_submit_and_forces_local_only_choice() -> None:
    with pytest.raises(OneShotChoiceError, match="--offline cannot be combined with --submit"):
        validate_one_shot_choices(
            is_tty=True,
            yes=False,
            submit_choice=True,
            accept_suite_terms=True,
            vram_gb=24.0,
            quant="Q4_K_M",
            vram_detected=False,
            offline=True,
        )

    choices = validate_one_shot_choices(
        is_tty=False,
        yes=True,
        submit_choice=False,
        accept_suite_terms=True,
        vram_gb=24.0,
        quant="Q4_K_M",
        vram_detected=False,
        offline=True,
    )
    assert choices.submit is False


def test_plan_lock_resume_refuses_immutable_drift(tmp_path: Path) -> None:
    lock_path = tmp_path / "plan.lock.json"
    plan = {
        "schema_version": "localbench.one_shot_plan.v1",
        "requested_model": "qwen3-6-27b",
        "quant_label": "Q4_K_M",
        "artifact_revision": REV_A,
        "artifact_filename": "qwen3-q4.gguf",
        "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
        "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
        "cli_version": "0.2.5",
    }

    write_plan_lock(lock_path, plan)

    expected = dict(plan)
    expected["artifact_revision"] = REV_B
    with pytest.raises(PlanLockMismatch, match="artifact_revision"):
        validate_resume_plan_lock(lock_path, expected)

    assert json.loads(lock_path.read_text(encoding="utf-8")) == plan
    assert not (tmp_path / "plan.lock.json.partial").exists()


def test_identity_envelope_prevalidation_requires_pinned_artifact_and_full_suite_pair() -> None:
    resolved = resolve_one_shot_model(
        "qwen3-6-27b",
        catalog_with_artifacts(
            artifacts=[
                {
                    "quant_label": "Q4_K_M",
                    "repo_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
                    "filename": "qwen3-q4.gguf",
                    "revision": REV_A,
                    "sha256": SHA_A,
                    "size_bytes": 2048,
                    "vram_required_gb_32k": 22.0,
                },
            ],
        ),
        quant="Q4_K_M",
        vram_gb=24.0,
    )
    envelope = build_identity_envelope(resolved, cli_version="0.2.5")

    prevalidate_identity_envelope(envelope)

    broken = dict(envelope)
    broken["artifact"] = {**dict(envelope["artifact"]), "revision": None}
    with pytest.raises(CatalogResolutionError, match="pinned artifact revision"):
        prevalidate_identity_envelope(broken)


def test_publishability_preflight_uses_read_only_submission_preflight_endpoint() -> None:
    resolved = resolve_one_shot_model(
        "qwen3-6-27b",
        catalog_with_artifacts(
            artifacts=[
                {
                    "quant_label": "Q4_K_M",
                    "repo_id": "unsloth/Qwen3.6-27B-MTP-GGUF",
                    "filename": "qwen3-q4.gguf",
                    "revision": REV_A,
                    "sha256": SHA_A,
                    "size_bytes": 2048,
                    "vram_required_gb_32k": 22.0,
                },
            ],
        ),
        quant="Q4_K_M",
        vram_gb=24.0,
    )
    payload = build_publishability_preflight_payload(resolved, cli_version="0.2.5")
    http = _FakeHttp({"publishable": True, "reasons": []})

    response = request_publishability_preflight("https://local-bench.ai", payload, http=http)

    assert response == {"publishable": True, "reasons": []}
    assert http.calls == [("https://local-bench.ai/api/submissions/preflight", payload)]
    assert payload["suite_release_id"] == FULL_EXEC_SUITE_RELEASE_ID
    assert payload["suite_manifest_sha256"] == FULL_EXEC_SUITE_MANIFEST_SHA256
    assert payload["source"] == "one_shot"


class _FakeHttp:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((url, payload))
        return self._payload
