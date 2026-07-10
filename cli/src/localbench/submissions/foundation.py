from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._scoring import BenchAggregate
from localbench._types import JsonObject, JsonValue
from localbench.scoring.axis_status import AxisStatusBlock, parse_axis_status_block
from localbench.scoring.scorecard import SCORECARD_VERSION
from localbench.serving.provenance import sanitize_launch_argv
from localbench.submissions.bundle_input import load_result_bundle_input
from localbench.submissions.canon import sha256_file
from localbench.submissions.contracts import (
    ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION,
    RESULT_BUNDLE_SCHEMA_VERSION,
    SUBMISSION_ENVELOPE_SCHEMA_VERSION,
)
from localbench.submissions.foundation_scores import score_summary
from localbench.submissions.origin import normalize_origin
from localbench.submissions.validate import SubmissionValidationError
from localbench.suite_release import (
    COVERAGE_PROFILES,
    build_suite_release_manifest,
    coverage_profile_for_benches,
)

VALIDATION_SCHEMA_VERSION: Final = "localbench.submission_validation.v1"
VALIDATOR_VERSION: Final = "localbench.submission-validator.v1"
SERVING_MODE_EXTERNAL: Final = "external_openai_compatible_endpoint"

_REMOVED_RESULT_FIELDS: Final = frozenset(
    {
        "schema",
        "submission_ticket_id",
        "server_nonce",
        "issued_at",
        "account",
        "trust_tier",
        "serving_verification_level",
        "composite",
        "source",
        "output_path",
    },
)
_MODEL_REQUIRED: Final = (
    "model.family",
    "model.quant_label",
    "model.file_name",
    "model.file_size_bytes",
    "model.file_sha256",
    "model.format",
    "model.tokenizer_digest",
    "model.chat_template_digest",
)
_RUNTIME_REQUIRED: Final = (
    "runtime.name",
    "runtime.version",
    "runtime.kv_cache_quant",
    "runtime.ctx_len_configured",
    "runtime.parallel_slots",
)
_SITE_RELEASED_SUITES: Final[dict[str, str]] = {
    # suite_release_id -> canonical suite_manifest_sha256 the SITE actually serves
    # (web/public/suites/<id>/suite_release_manifest.json). A bundle counts as
    # "site-released" ONLY if it DECLARES one of these exact pairs, i.e. it was produced by
    # a runner that pulled the site release. Validation must NOT infer this from a local
    # --suite-dir. core-text-v1 is intentionally absent: it has no published release
    # manifest yet and is not a publishable (headline-bearing) profile.
    "suite-v1-partial-text-code-4axis-v1": (
        "95f86098b23d4055b563f1ba015c005350a6f7a1d721489b26c6c1d86e8054e7"
    ),
    "suite-v1-text-code-agentic-5axis-v1": (
        "1b6a716050edd24fee4f0f0bea748407ee3fcd4d61622d69232943cc315f0a2f"
    ),
    "suite-v1-full-exec-6axis-v1": (
        "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468"
    ),
    "suite-v1-static-exec-5axis-v1": (
        "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64"
    ),
    "suite-v1-static-core-diag-v1": (
        "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69"
    ),
}


def site_released_suite_pairs() -> dict[str, str]:
    return dict(_SITE_RELEASED_SUITES)


def is_site_released_suite_pair(release_id: str, manifest_sha256: str) -> bool:
    return _SITE_RELEASED_SUITES.get(release_id) == manifest_sha256


@dataclass(frozen=True, slots=True)
class ResultBundleValidation:
    publishable: bool
    blocking_reasons: list[str]
    missing_required_fields: list[str]
    bundle_sha256: str | None = None


def normalize_result_bundle(
    record: JsonObject,
    *,
    suite_dir: Path | None = None,
) -> JsonObject:
    if (
        record.get("schema_version") == RESULT_BUNDLE_SCHEMA_VERSION
        and _REMOVED_RESULT_FIELDS.isdisjoint(record)
        and isinstance(record.get("scores"), dict)
    ):
        bundle = _copy_object(record)
        bundle["manifest"] = _normalize_manifest(_object(bundle.get("manifest")), bundle, suite_dir)
        return _sanitize_published_paths(_sanitize_output_path(bundle))
    manifest = _normalize_manifest(_object(record.get("manifest")), record, suite_dir)
    perf = _object(record.get("perf")) if "perf" in record else None
    bundle: JsonObject = {
        "schema_version": RESULT_BUNDLE_SCHEMA_VERSION,
        "run_started_at": record.get("run_started_at"),
        "run_finished_at": record.get("run_finished_at"),
        "producer": _string(record.get("source")) or "localbench-cli",
        "tier": _string(record.get("tier")) or "standard",
        "serving_mode": SERVING_MODE_EXTERNAL,
        "model": _object(record.get("model")),
        "manifest": manifest,
        "axis_status": _object(record.get("axis_status")),
        "headline_complete": bool(record.get("headline_complete")),
        "scores": score_summary(
            _benches(record),
            _axis_status(record),
            suite_axes=_suite_axes(manifest),
        ),
        "benches": _object(record.get("benches")),
        "conformance": _object(record.get("conformance")),
        "items": _list(record.get("items")),
        "totals": _object(record.get("totals")),
        **({"perf": perf} if perf is not None else {}),
        "warnings": _string_list(record.get("warnings")),
    }
    _copy_optional(record, bundle, "agentic_run")
    _copy_optional(record, bundle, "estimated_cost_usd")
    _copy_optional(record, bundle, "resumed")
    _copy_optional(record, bundle, "resume_count")
    _copy_optional(record, bundle, "segments")
    _copy_optional(record, bundle, "prompt_audit")
    _copy_optional(record, bundle, "budget_audit")
    _copy_optional(record, bundle, "sampler_audit")
    _copy_optional(record, bundle, "suite_coverage")
    _copy_optional(record, bundle, "index_version")
    return _sanitize_published_paths(bundle)


def validate_result_bundle(bundle: JsonObject) -> ResultBundleValidation:
    if bundle.get("schema_version") != RESULT_BUNDLE_SCHEMA_VERSION:
        raise SubmissionValidationError("result bundle schema_version is not supported")
    for field in _REMOVED_RESULT_FIELDS:
        if field in bundle:
            raise SubmissionValidationError(f"result bundle must not contain {field}")
    for field in ("manifest", "scores", "benches", "items", "axis_status"):
        if field not in bundle:
            raise SubmissionValidationError(f"result bundle missing {field}")
    integrity = _object(_object(bundle.get("manifest")).get("integrity"))
    return ResultBundleValidation(
        publishable=bool(integrity.get("publishable")),
        blocking_reasons=_string_list(integrity.get("blocking_reasons")),
        missing_required_fields=_string_list(integrity.get("missing_required_fields")),
    )


def validate_submission_bundle(
    path: Path,
    *,
    suite_dir: Path | None = None,
) -> JsonObject:
    loaded = load_result_bundle_input(path)
    bundle = normalize_result_bundle(loaded.record, suite_dir=suite_dir)
    validation = validate_result_bundle(bundle)
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "bundle_sha256": sha256_file(path),
        "publishable": validation.publishable,
        "blocking_reasons": validation.blocking_reasons,
        "missing_required_fields": validation.missing_required_fields,
    }


def validate_submission_envelope(envelope: JsonObject) -> None:
    if envelope.get("schema_version") != SUBMISSION_ENVELOPE_SCHEMA_VERSION:
        raise SubmissionValidationError("submission envelope schema_version is not supported")
    envelope["origin"] = normalize_origin(envelope.get("origin"))
    if envelope.get("allowed_schema") != RESULT_BUNDLE_SCHEMA_VERSION:
        raise SubmissionValidationError("submission envelope allowed_schema is not supported")
    digest = envelope.get("bundle_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SubmissionValidationError("submission envelope bundle_sha256 must be a sha256 hex digest")


def validate_accepted_result_projection(projection: JsonObject) -> None:
    if projection.get("schema_version") != ACCEPTED_RESULT_PROJECTION_SCHEMA_VERSION:
        raise SubmissionValidationError("accepted projection schema_version is not supported")
    for field in ("items", "output_path", "reasoning_text"):
        if field in projection:
            raise SubmissionValidationError(f"accepted projection must not contain {field}")
    for field in ("model", "runtime", "scores", "axes", "artifact_hashes", "validator"):
        if field not in projection:
            raise SubmissionValidationError(f"accepted projection missing {field}")
    normalize_origin(projection.get("origin"))
    if projection.get("trust_label") not in {"project_anchor", "community_self_submitted", "community_re_scored"}:
        raise SubmissionValidationError("accepted projection trust_label is not supported")
    if projection.get("verification_level") != "bundle_rescored":
        raise SubmissionValidationError("accepted projection verification_level is not supported")
    if projection.get("agentic_provenance") not in {"none", "project_attested", "self_reported"}:
        raise SubmissionValidationError("accepted projection agentic_provenance is not supported")
    notes = projection.get("provenance_notes")
    if notes is not None and (not isinstance(notes, list) or not all(isinstance(note, str) for note in notes)):
        raise SubmissionValidationError("accepted projection provenance_notes must be a list of strings")


def rescore_bundle(
    path: Path,
    *,
    suite_dir: Path,
    validated_at: str = "1970-01-01T00:00:00Z",
    origin: str = "project_anchor",
) -> JsonObject:
    from localbench.submissions.projection import rescore_bundle as _rescore_bundle

    return _rescore_bundle(path, suite_dir=suite_dir, validated_at=validated_at, origin=normalize_origin(origin))


def _normalize_manifest(
    manifest: JsonObject,
    record: JsonObject,
    suite_dir: Path | None,
) -> JsonObject:
    normalized = _copy_object(manifest)
    # Capture the suite identity the bundle ACTUALLY DECLARES, before _normalize_suite may
    # enrich/inject release fields from a local --suite-dir. The publishable gate's
    # site-released check must read this declared identity, never the locally-derived one.
    declared_suite = _copy_object(_object(normalized.get("suite")))
    suite = _normalize_suite(_object(normalized.get("suite")), record, suite_dir)
    normalized["suite"] = suite
    normalized["provenance"] = _provenance(_object(normalized.get("provenance")))
    missing = _missing_required_fields(normalized)
    blocking = _blocking_reasons(normalized, missing, declared_suite, record)
    normalized["integrity"] = {
        "publishable": blocking == [],
        "validation_profile": "publishable-result-bundle-v1",
        "blocking_reasons": blocking,
        "missing_required_fields": missing,
    }
    sampling = _object(normalized.get("sampling"))
    if "determinism_policy" not in sampling:
        sampling["determinism_policy"] = _determinism_policy(sampling)
    normalized["sampling"] = sampling
    return normalized


def _normalize_suite(
    suite: JsonObject,
    record: JsonObject,
    suite_dir: Path | None,
) -> JsonObject:
    benches = set(_object(record.get("benches")))
    profile = coverage_profile_for_benches(benches)
    normalized = _copy_object(suite)
    normalized["coverage_profile_id"] = profile.profile_id
    if suite_dir is None or profile.profile_id not in COVERAGE_PROFILES:
        normalized.setdefault("suite_release_id", f"{_string(suite.get('suite_version')) or 'suite'}-{profile.profile_id}")
        normalized.setdefault("suite_manifest_sha256", None)
        normalized.setdefault("suite_hash_algorithm", "sha256-canonical-json-v1")
        return normalized
    release = build_suite_release_manifest(suite_dir, coverage_profile_id=profile.profile_id)
    normalized["suite_release_id"] = release["suite_release_id"]
    normalized["suite_manifest_sha256"] = release["suite_manifest_sha256"]
    normalized["suite_hash_algorithm"] = release["suite_hash_algorithm"]
    normalized["axis_membership"] = release["axis_membership"]
    normalized["bench_membership"] = release["bench_membership"]
    normalized["license_manifest_sha256"] = release["license_manifest_sha256"]
    return normalized


def _missing_required_fields(manifest: JsonObject) -> list[str]:
    existing = _string_list(_object(manifest.get("integrity")).get("missing_fields"))
    existing.extend(_string_list(_object(manifest.get("integrity")).get("missing_required_fields")))
    missing = [field for field in (*_MODEL_REQUIRED, *_RUNTIME_REQUIRED) if _field_missing(manifest, field)]
    return _dedupe([*existing, *missing])


def _blocking_reasons(
    manifest: JsonObject,
    missing: list[str],
    declared_suite: JsonObject,
    record: JsonObject,
) -> list[str]:
    sampling = _object(manifest.get("sampling"))
    reasons: list[str] = []
    if sampling.get("top_k") != 1:
        reasons.append("sampler.top_k_unpinned")
    seed = sampling.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        reasons.append("sampler.seed_unpinned")
    if any(field in missing for field in _MODEL_REQUIRED):
        reasons.append("model.identity_missing")
    if any(field in missing for field in _RUNTIME_REQUIRED):
        reasons.append("runtime.identity_missing")
    if not _site_released(declared_suite):
        reasons.append("suite.not_site_released")
    if _requires_code_artifacts(declared_suite, record) and _has_missing_code_artifacts(record):
        reasons.append("missing_code_artifacts")
    # Tuple membership, not set: orchestrated manifests record determinism_policy as a
    # structured object, which is unhashable and only needs to count as "present".
    if reasons == [] and sampling.get("determinism_policy") in (None, ""):
        reasons.append("sampler.determinism_policy_missing")
    return reasons


def _requires_code_artifacts(suite: JsonObject, record: JsonObject) -> bool:
    release_id = suite.get("suite_release_id")
    return (
        release_id in {"suite-v1-full-exec-6axis-v1", "suite-v1-static-exec-5axis-v1"}
        and "bigcodebench_hard" in _object(record.get("benches"))
    )


def _has_missing_code_artifacts(record: JsonObject) -> bool:
    seen = False
    for item in _list(record.get("items")):
        if item.get("bench") != "bigcodebench_hard":
            continue
        seen = True
        if not isinstance(item.get("code_artifact"), dict):
            return True
    return not seen


def _site_released(suite: JsonObject) -> bool:
    # Honest gate: the BUNDLE must DECLARE a site-released suite_release_id AND the matching
    # canonical suite_manifest_sha256 the site serves. A release-id string alone is not enough,
    # and identity inferred from a local --suite-dir does not count.
    release_id = suite.get("suite_release_id")
    if not isinstance(release_id, str):
        return False
    manifest_sha256 = suite.get("suite_manifest_sha256")
    return isinstance(manifest_sha256, str) and is_site_released_suite_pair(release_id, manifest_sha256)


def _determinism_policy(sampling: JsonObject) -> str | None:
    seed = sampling.get("seed")
    if sampling.get("top_k") == 1 and isinstance(seed, int) and not isinstance(seed, bool):
        return "top_k_1_seeded"
    return None


def _field_missing(manifest: JsonObject, dotted: str) -> bool:
    head, _, tail = dotted.partition(".")
    section = _object(manifest.get(head))
    value = section.get(tail)
    return value is None or value in {"", "unknown", "UNHASHED", "endpoint-applied-unknown"}


def _provenance(existing: JsonObject) -> JsonObject:
    return {
        "localbench_repo_commit": existing.get("localbench_repo_commit"),
        "dirty_tree": bool(existing.get("dirty_tree", True)),
        "cli_version": existing.get("cli_version") or "0.1.0",
        "python_version": existing.get("python_version"),
        "dependency_lock_hash": existing.get("dependency_lock_hash"),
        "scorer_package_version": existing.get("scorer_package_version") or SCORECARD_VERSION,
        "extractor_versions": _object(existing.get("extractor_versions")),
        "runner_build_id": existing.get("runner_build_id"),
    }


def _sanitize_output_path(bundle: JsonObject) -> JsonObject:
    bundle.pop("output_path", None)
    return bundle


def _sanitize_published_paths(bundle: JsonObject) -> JsonObject:
    serving = _object(bundle.get("serving"))
    launch = _object(serving.get("launch"))
    cwd = launch.pop("cwd", None)
    if isinstance(cwd, str) and cwd:
        launch["cwd_sha256"] = hashlib.sha256(cwd.encode("utf-8")).hexdigest()
    argv = launch.get("argv")
    if isinstance(argv, list) and all(isinstance(item, str) for item in argv):
        launch["argv"] = sanitize_launch_argv(argv)
    if launch:
        serving["launch"] = launch
    if serving:
        bundle["serving"] = serving

    agentic_run = _object(bundle.get("agentic_run"))
    runs = agentic_run.get("runs")
    if isinstance(runs, list):
        for raw in runs:
            if not isinstance(raw, dict):
                continue
            results_path = raw.get("results_path")
            if isinstance(results_path, str) and _unsafe_relative_path(results_path):
                raw.pop("results_path", None)
    wsl_identity = _object(agentic_run.get("wsl_identity"))
    for field in ("venv_path", "bwrap_path", "appworld_root"):
        wsl_identity.pop(field, None)
    if wsl_identity:
        agentic_run["wsl_identity"] = wsl_identity
    if agentic_run:
        bundle["agentic_run"] = agentic_run
    return bundle


def _unsafe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith("/")
        or (len(normalized) >= 3 and normalized[0].isalpha() and normalized[1:3] == ":/")
        or ".." in normalized.split("/")
    )


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SubmissionValidationError("submission bundle must be a JSON object")
    return data


def _benches(record: JsonObject) -> dict[str, BenchAggregate]:
    raw = _object(record.get("benches"))
    benches: dict[str, BenchAggregate] = {}
    for name, value in raw.items():
        if isinstance(value, dict):
            benches[name] = {
                "n": _int(value.get("n")),
                "n_errors": _int(value.get("n_errors")),
                "n_extraction_failures": _int(value.get("n_extraction_failures")),
                "raw_accuracy": _number(value.get("raw_accuracy")),
                "chance_corrected": _number(value.get("chance_corrected")),
                "termination_rate": _number(value.get("termination_rate")),
                "conditional_accuracy": _number(value.get("conditional_accuracy")),
            }
    return benches


def _axis_status(record: JsonObject) -> AxisStatusBlock:
    return parse_axis_status_block(_object(record.get("axis_status")))


def _suite_axes(manifest: JsonObject) -> JsonObject | None:
    axes = _object(_object(manifest.get("suite")).get("axis_membership"))
    if not axes:
        return None
    return {axis: {"benches": benches} for axis, benches in axes.items()}


def _copy_object(value: JsonObject) -> JsonObject:
    data = json.loads(json.dumps(value, ensure_ascii=False))
    return data if isinstance(data, dict) else {}


def _copy_optional(source: JsonObject, target: JsonObject, field: str) -> None:
    if field in source:
        target[field] = json.loads(json.dumps(source[field], ensure_ascii=False))


def _object(value: JsonValue | None) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: JsonValue | None) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: JsonValue | None) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _number(value: JsonValue | None) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
