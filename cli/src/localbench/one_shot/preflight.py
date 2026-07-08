from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from localbench._types import JsonObject
from localbench.one_shot.catalog import CatalogResolutionError
from localbench.one_shot.types import (
    FULL_EXEC_SUITE_MANIFEST_SHA256,
    FULL_EXEC_SUITE_RELEASE_ID,
    IDENTITY_ENVELOPE_SCHEMA_VERSION,
    ONE_SHOT_PLAN_SCHEMA_VERSION,
    PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION,
    ResolvedOneShotModel,
)
from localbench.persistence import atomic_write_json


class JsonPostClient(Protocol):
    def post_json(self, url: str, payload: JsonObject) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class OneShotChoiceError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class PlanLockMismatch(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class OneShotChoices:
    submit: bool | None
    accept_suite_terms: bool
    vram_gb: float | None
    quant: str | None
    offline: bool


def validate_one_shot_choices(
    *,
    is_tty: bool,
    yes: bool,
    submit_choice: bool | None,
    accept_suite_terms: bool,
    vram_gb: float | None,
    quant: str | None,
    vram_detected: bool,
    offline: bool,
) -> OneShotChoices:
    if offline and submit_choice is True:
        raise OneShotChoiceError("--offline cannot be combined with --submit")
    if not is_tty:
        if not yes:
            raise OneShotChoiceError("non-TTY one-shot runs require --yes")
        if submit_choice is None:
            raise OneShotChoiceError("non-TTY one-shot runs require --submit or --no-submit")
        if not accept_suite_terms:
            raise OneShotChoiceError("non-TTY one-shot runs require --accept-suite-terms")
        if not vram_detected and vram_gb is None and quant is None:
            raise OneShotChoiceError("non-TTY one-shot runs require --vram-gb or --quant when VRAM is undetected")
    return OneShotChoices(
        submit=False if offline else submit_choice,
        accept_suite_terms=accept_suite_terms,
        vram_gb=vram_gb,
        quant=quant,
        offline=offline,
    )


def write_plan_lock(lock_path: Path, plan: JsonObject) -> None:
    if plan.get("schema_version") != ONE_SHOT_PLAN_SCHEMA_VERSION:
        raise PlanLockMismatch("plan.lock.json schema_version is not localbench.one_shot_plan.v1")
    atomic_write_json(plan, lock_path)


def validate_resume_plan_lock(lock_path: Path, expected: JsonObject) -> JsonObject:
    try:
        loaded = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanLockMismatch(f"could not read plan.lock.json: {error}") from error
    if not isinstance(loaded, dict):
        raise PlanLockMismatch("plan.lock.json must contain an object")
    for key, expected_value in expected.items():
        if loaded.get(key) != expected_value:
            raise PlanLockMismatch(f"plan.lock.json immutable drift: {key}")
    return {str(key): value for key, value in loaded.items()}


def build_identity_envelope(resolved: ResolvedOneShotModel, *, cli_version: str) -> JsonObject:
    return {
        "schema_version": IDENTITY_ENVELOPE_SCHEMA_VERSION,
        "source": "one_shot",
        "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
        "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
        "cli_version": cli_version,
        "requested_model": resolved.requested,
        "catalog_model_id": resolved.catalog_model_id,
        "model_id": resolved.model_id,
        "family": resolved.family,
        "local_only": resolved.local_only,
        "publishable": resolved.publishable,
        "artifact": {
            "repo_id": resolved.artifact.repo_id,
            "filename": resolved.artifact.filename,
            "revision": resolved.artifact.revision,
            "sha256": resolved.artifact.sha256,
            "size_bytes": resolved.artifact.size_bytes,
            "quant_label": resolved.artifact.quant_label,
        },
    }


def prevalidate_identity_envelope(envelope: JsonObject) -> None:
    if envelope.get("schema_version") != IDENTITY_ENVELOPE_SCHEMA_VERSION:
        raise CatalogResolutionError("identity envelope schema_version is not supported")
    if envelope.get("suite_release_id") != FULL_EXEC_SUITE_RELEASE_ID:
        raise CatalogResolutionError("identity envelope suite_release_id is not publishable")
    if envelope.get("suite_manifest_sha256") != FULL_EXEC_SUITE_MANIFEST_SHA256:
        raise CatalogResolutionError("identity envelope suite_manifest_sha256 is not publishable")
    artifact = envelope.get("artifact")
    if not isinstance(artifact, dict):
        raise CatalogResolutionError("identity envelope artifact is missing")
    if not _full_revision(artifact.get("revision")):
        raise CatalogResolutionError("identity envelope requires a pinned artifact revision")
    if not _non_empty_text(artifact.get("repo_id")) or not _non_empty_text(artifact.get("filename")):
        raise CatalogResolutionError("identity envelope requires pinned artifact repo_id and filename")
    if not _sha256(artifact.get("sha256")):
        raise CatalogResolutionError("identity envelope requires pinned artifact sha256")


def build_publishability_preflight_payload(resolved: ResolvedOneShotModel, *, cli_version: str) -> JsonObject:
    envelope = build_identity_envelope(resolved, cli_version=cli_version)
    prevalidate_identity_envelope(envelope)
    return {
        "schema_version": PUBLISHABILITY_PREFLIGHT_SCHEMA_VERSION,
        "source": "one_shot",
        "suite_release_id": FULL_EXEC_SUITE_RELEASE_ID,
        "suite_manifest_sha256": FULL_EXEC_SUITE_MANIFEST_SHA256,
        "cli_version": cli_version,
        "catalog_model_id": resolved.catalog_model_id,
        "quant_label": resolved.artifact.quant_label,
        "artifact": _artifact_payload(envelope),
        "identity_envelope": envelope,
    }


def request_publishability_preflight(
    site: str,
    payload: JsonObject,
    *,
    http: JsonPostClient | None = None,
) -> JsonObject:
    client = http or _HttpJsonClient()
    url = f"{site.rstrip('/')}/api/submissions/preflight"
    return client.post_json(url, payload)


class _HttpJsonClient:
    def post_json(self, url: str, payload: JsonObject) -> JsonObject:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("publishability preflight response must be a JSON object")
        return {str(key): item for key, item in value.items()}


def _full_revision(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdefABCDEF" for char in value)


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _artifact_payload(envelope: JsonObject) -> JsonObject:
    artifact = envelope.get("artifact")
    if not isinstance(artifact, dict):
        raise CatalogResolutionError("identity envelope artifact is missing")
    return {str(key): item for key, item in artifact.items()}
