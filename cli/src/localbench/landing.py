"""Maintainer-only landing automation for verified benchmark runs."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.orchestrate import _budget_audit
from localbench.persistence import atomic_write_bytes, atomic_write_json
from localbench.scoring.board import build_board, write_board
from localbench.scoring.board_support import DEFAULT_OUT_V2, DEFAULT_RUNS_DIR, REPO_ROOT, read_json, slugify, write_json
from localbench.scoring.scorecard import scorecard_identity

DATA_SOURCES_PATH: Final = REPO_ROOT / "web" / "data_sources.json"
MODEL_CATALOG_PATH: Final = REPO_ROOT / "web" / "model_catalog.json"
LANDED_RUNS_DIR: Final = REPO_ROOT / "runs" / "bench" / "landed"
LAUNCH_FREEZE_PATH: Final = REPO_ROOT / "web" / "components" / "launch-freeze.ts"
BOARD_MANIFEST_PATH: Final = DEFAULT_OUT_V2.with_name("board_v2.manifest.json")


class LandingError(RuntimeError):
    """Raised when a run cannot be landed without violating publication gates."""


@dataclass(frozen=True, slots=True)
class LandingResult:
    board_sha256: str
    canonical_path: Path
    dry_run: bool
    launch_freeze_hash: str | None
    model_label: str
    model_sha256: str
    source_added: bool


def land_run(
    run_dir: Path,
    *,
    coding_verified_path: Path | None = None,
    dry_run: bool = False,
) -> LandingResult:
    """Stage, gate, and optionally apply the documented maintainer landing pipeline."""
    resolved_run_dir = run_dir.expanduser().resolve()
    if not resolved_run_dir.is_dir():
        raise LandingError(f"--run must be a run directory: {resolved_run_dir}")
    original_path = resolved_run_dir / "localbench-run.json"
    verified_path = _resolve_verified_path(resolved_run_dir, coding_verified_path)
    original = _read_object(original_path, "original run")
    verified = _read_object(verified_path, "coding-verified run")
    _assert_generations_untouched(original, verified)
    _assert_coding_verified(verified)
    _assert_agentic_verification(verified)

    rescored = _rescore(verified, original_path=original_path, verified_path=verified_path)
    model_sha = _model_sha(rescored)
    catalog_entry = _catalog_entry(rescored, resolved_run_dir)
    sources = _read_sources()
    source_template = _existing_source_template(sources, _required_text(catalog_entry, "id"))
    source = _source_entry(rescored, catalog_entry, source_template, model_sha=model_sha)
    canonical_path = _canonical_path(rescored, model_sha)
    relative_canonical = canonical_path.relative_to(REPO_ROOT).as_posix()
    source["file"] = relative_canonical

    existing_source = _source_for_artifact(sources, model_sha)
    source_added = existing_source is None
    if existing_source is not None:
        existing_file = existing_source.get("file")
        if existing_file != relative_canonical:
            raise LandingError(
                f"exact GGUF {model_sha} is already curated from {existing_file}; refusing a second canonical record"
            )

    current_board = _read_object(DEFAULT_OUT_V2, "current board")
    _validate_launch_freeze()
    frozen_timestamp = _generated_at(current_board)
    with tempfile.TemporaryDirectory(prefix="localbench-land-") as temp_name:
        temp_dir = Path(temp_name)
        staged_run = temp_dir / canonical_path.name
        atomic_write_json(rescored, staged_run)
        staged_sources = copy.deepcopy(sources)
        if source_added:
            staged_source = copy.deepcopy(source)
            staged_source["file"] = str(staged_run)
            staged_sources.append(staged_source)
        else:
            for item in staged_sources:
                if item.get("file") == relative_canonical:
                    item["file"] = str(staged_run)
                    break
        staged_curation = temp_dir / "data_sources.json"
        atomic_write_json(staged_sources, staged_curation)
        candidate_board = build_board(
            runs_dir=DEFAULT_RUNS_DIR,
            curation_path=staged_curation,
            generated_at=frozen_timestamp,
        )
        candidate_system = _candidate_system(candidate_board, canonical_path.stem, source)
        if candidate_system.get("ranked") is not True:
            raise LandingError("the verified run still fails ranked gates; refusing to curate it")
        changed = changed_existing_ranked_rows(current_board, candidate_board)
        if changed:
            raise LandingError(
                "candidate landing would change existing ranked row(s): " + ", ".join(changed)
            )
        staged_board = temp_dir / "board_v2.json"
        write_json(staged_board, candidate_board)
        _preflight_web_build(staged_curation, staged_board, temp_dir / "site-data")
        candidate_board_sha = _sha256_file(staged_board)

    if dry_run:
        return LandingResult(
            board_sha256=candidate_board_sha,
            canonical_path=canonical_path,
            dry_run=True,
            launch_freeze_hash=None,
            model_label=_required_text(source, "model_label"),
            model_sha256=model_sha,
            source_added=source_added,
        )

    original_sources_bytes = DATA_SOURCES_PATH.read_bytes()
    prior_canonical_bytes = canonical_path.read_bytes() if canonical_path.exists() else None
    board_bytes = DEFAULT_OUT_V2.read_bytes()
    board_manifest_bytes = BOARD_MANIFEST_PATH.read_bytes() if BOARD_MANIFEST_PATH.exists() else None
    try:
        atomic_write_json(rescored, canonical_path)
        if source_added:
            atomic_write_bytes(_append_json_array_item(original_sources_bytes, source), DATA_SOURCES_PATH)
        result = write_board(
            runs_dir=DEFAULT_RUNS_DIR,
            out=DEFAULT_OUT_V2,
            curation_path=DATA_SOURCES_PATH,
            check_parity=False,
        )
        rebuilt_board = _read_object(DEFAULT_OUT_V2, "rebuilt board")
        changed = changed_existing_ranked_rows(current_board, rebuilt_board)
        if changed:
            raise LandingError(
                "rebuilt board changed existing ranked row(s): " + ", ".join(changed)
            )
        _run_web_build()
        launch_hash = _git_object_hash(DEFAULT_OUT_V2)
        _update_launch_freeze(launch_hash)
    except Exception:
        atomic_write_bytes(original_sources_bytes, DATA_SOURCES_PATH)
        atomic_write_bytes(board_bytes, DEFAULT_OUT_V2)
        if board_manifest_bytes is not None:
            atomic_write_bytes(board_manifest_bytes, BOARD_MANIFEST_PATH)
        if prior_canonical_bytes is None:
            canonical_path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(prior_canonical_bytes, canonical_path)
        raise
    return LandingResult(
        board_sha256=result.board_sha256,
        canonical_path=canonical_path,
        dry_run=False,
        launch_freeze_hash=launch_hash,
        model_label=_required_text(source, "model_label"),
        model_sha256=model_sha,
        source_added=source_added,
    )


def changed_existing_ranked_rows(current: JsonObject, candidate: JsonObject) -> tuple[str, ...]:
    """Return existing ranked model slugs whose complete board objects changed or disappeared."""
    before = {
        _required_text(model, "slug"): model
        for model in _object_list(current.get("models"), "current board models")
        if model.get("ranked") is True
    }
    after = {
        _required_text(model, "slug"): model
        for model in _object_list(candidate.get("models"), "candidate board models")
    }
    return tuple(sorted(slug for slug, row in before.items() if after.get(slug) != row))


def print_landing_checklist(result: LandingResult) -> None:
    marker = "WOULD" if result.dry_run else "OK"
    print("final checklist")
    print(f"[{marker}] exact GGUF identity pinned: {result.model_sha256}")
    print(f"[{marker}] coding verdicts maintainer-verified and current scorer identity stamped")
    print(f"[{marker}] canonical record: {result.canonical_path}")
    print(f"[{marker}] web/data_sources.json: {'append entry' if result.source_added else 'entry already present'}")
    print(f"[{marker}] existing ranked rows unchanged")
    print(f"[{marker}] board rebuilt; sha256={result.board_sha256}")
    print(f"[{marker}] web public data rebuilt")
    if result.launch_freeze_hash is None:
        print("[WOULD] web/components/launch-freeze.ts boardSha256 re-pinned")
    else:
        print(f"[OK] web/components/launch-freeze.ts boardSha256={result.launch_freeze_hash}")
    print("[MANUAL] deploy and live smoke were not run")


def _resolve_verified_path(run_dir: Path, raw: Path | None) -> Path:
    if raw is None:
        return run_dir / "coding-verified.json"
    expanded = raw.expanduser()
    if expanded.is_absolute():
        return expanded
    cwd_candidate = expanded.resolve()
    return cwd_candidate if cwd_candidate.exists() else (run_dir / expanded).resolve()


def _read_object(path: Path, label: str) -> JsonObject:
    if not path.is_file():
        raise LandingError(f"{label} not found: {path}")
    value = read_json(path)
    if not isinstance(value, dict):
        raise LandingError(f"{label} must be a JSON object: {path}")
    return value


def _read_sources() -> list[JsonObject]:
    value = read_json(DATA_SOURCES_PATH)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LandingError(f"{DATA_SOURCES_PATH} must be an array of objects")
    return list(value)


def _assert_generations_untouched(original: JsonObject, verified: JsonObject) -> None:
    if original.get("model") != verified.get("model"):
        raise LandingError("coding verification changed the top-level model identity")
    original_manifest_model = _object(_object(original.get("manifest"), "original manifest").get("model"), "original manifest.model")
    verified_manifest_model = _object(_object(verified.get("manifest"), "verified manifest").get("model"), "verified manifest.model")
    if original_manifest_model != verified_manifest_model:
        raise LandingError("coding verification changed manifest.model")
    original_items = _object_list(original.get("items"), "original items")
    verified_items = _object_list(verified.get("items"), "verified items")
    if len(original_items) != len(verified_items):
        raise LandingError("coding verification changed the item count")
    mutable = {"code_artifact", "correct", "extracted", "failure_kind"}
    for before, after in zip(original_items, verified_items, strict=True):
        identity = (before.get("bench"), before.get("id"))
        if identity != (after.get("bench"), after.get("id")):
            raise LandingError(f"coding verification changed item order/identity at {identity}")
        if before.get("bench") != "bigcodebench_hard":
            if before != after:
                raise LandingError(f"coding verification changed non-coding item {identity[1]}")
            continue
        stable_before = {key: value for key, value in before.items() if key not in mutable}
        stable_after = {key: value for key, value in after.items() if key not in mutable}
        if stable_before != stable_after:
            raise LandingError(f"coding verification changed generation data for {identity[1]}")


def _assert_coding_verified(run: JsonObject) -> None:
    items = [item for item in _object_list(run.get("items"), "verified items") if item.get("bench") == "bigcodebench_hard"]
    if not items:
        raise LandingError("coding-verified record has no BigCodeBench-Hard items")
    missing = [str(item.get("id")) for item in items if not _trusted_coding_disposition(item)]
    if missing:
        suffix = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        raise LandingError(f"coding verifier left untrusted dispositions: {suffix}")


def _assert_agentic_verification(run: JsonObject) -> None:
    agentic = _object(run.get("agentic_run"), "agentic_run")
    runs = _object_list(agentic.get("runs"), "agentic_run.runs")
    if len(runs) < 2:
        raise LandingError("agentic verification must contain the full two-run campaign")
    subset_hashes = {_required_text(item, "subset_hash") for item in runs}
    if len(subset_hashes) != 1:
        raise LandingError("agentic verification runs do not use the same frozen task subset")
    for index, item in enumerate(runs, start=1):
        for gate in ("infra_timeout_rate", "infra_sandbox_rate", "harness_error_rate"):
            value = item.get(gate)
            if not isinstance(value, int | float) or isinstance(value, bool) or value != 0:
                raise LandingError(f"agentic run {index} failed infrastructure gate {gate}={value!r}")


def _trusted_coding_disposition(item: JsonObject) -> bool:
    artifact = item.get("code_artifact")
    if not isinstance(artifact, dict):
        return False
    if artifact.get("verdict_source") == "verifier":
        return True
    if item.get("correct") is not False:
        return False
    conformance = artifact.get("conformance_status")
    if isinstance(conformance, dict) and conformance.get("failure") == "coding_ast_rejected":
        return True
    extraction = artifact.get("extraction_status")
    return isinstance(extraction, dict) and extraction.get("status") not in (None, "ok")


def _rescore(run: JsonObject, *, original_path: Path, verified_path: Path) -> JsonObject:
    result = copy.deepcopy(run)
    manifest = _object(result.get("manifest"), "manifest")
    recorded = _object(manifest.get("scorecard"), "manifest.scorecard")
    profile_id = _required_text(recorded, "execution_profile_id")
    lane_spec_id = _required_text(recorded, "lane_spec_id")
    prior_scorecard_id = _required_text(recorded, "scorecard_id")
    current = scorecard_identity(profile_id, lane_spec_id=lane_spec_id)
    items = _object_list(result.get("items"), "items")
    budget = _budget_audit(items)  # type: ignore[arg-type]
    manifest["scorecard"] = current
    result["budget_audit"] = budget
    result["rescore_provenance"] = {
        "operation": "maintainer-land-run-current-scorer",
        "reason": (
            "coding verdicts re-executed by the maintainer verifier; scorecard identity and budget audit "
            "re-derived from current canonical functions; model generations unchanged"
        ),
        "source_run": original_path.name,
        "coding_verified_source": verified_path.name,
        "prior_scorecard_id": prior_scorecard_id,
        "rescored_scorecard_id": current["scorecard_id"],
        "generations_untouched": True,
        "coding_reverified": True,
    }
    return result


def _catalog_entry(run: JsonObject, run_dir: Path) -> JsonObject:
    catalog = _read_object(MODEL_CATALOG_PATH, "model catalog")
    models = _object_list(catalog.get("models"), "model catalog models")
    declared = _required_text(_object(run.get("model"), "run model"), "name")
    by_slug = [
        model for model in models
        if declared == _required_text(model, "slug") or declared.startswith(_required_text(model, "slug") + "-")
    ]
    if by_slug:
        return max(by_slug, key=lambda item: len(_required_text(item, "slug")))
    campaign_path = run_dir / "campaign.json"
    if campaign_path.is_file():
        campaign = _read_object(campaign_path, "campaign")
        hf_id = _object(campaign.get("model"), "campaign.model").get("hf_model_id")
        if isinstance(hf_id, str):
            exact = [model for model in models if str(model.get("id", "")).casefold() == hf_id.casefold()]
            if len(exact) == 1:
                return exact[0]
    raise LandingError(
        f"cannot map declared model {declared!r} to web/model_catalog.json; add the catalog entry before landing"
    )


def _existing_source_template(sources: list[JsonObject], model_id: str) -> JsonObject | None:
    return next((item for item in sources if str(item.get("model_id", "")).casefold() == model_id.casefold()), None)


def _source_entry(
    run: JsonObject,
    catalog: JsonObject,
    template: JsonObject | None,
    *,
    model_sha: str,
) -> JsonObject:
    manifest_model = _object(_object(run.get("manifest"), "manifest").get("model"), "manifest.model")
    suite = _object(_object(run.get("manifest"), "manifest").get("suite"), "manifest.suite")
    model_id = _required_text(catalog, "id")
    model_label = _template_text(template, "model_label") or _required_text(catalog, "display_name")
    family = _template_text(template, "family") or _required_text(catalog, "family")
    publisher = _template_text(template, "publisher") or _required_text(catalog, "org")
    gguf_repo = _template_text(template, "gguf_repo") or _optional_text(catalog.get("gguf_repo"))
    quant = _required_text(manifest_model, "quant_label")
    size = manifest_model.get("file_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise LandingError("manifest.model.file_size_bytes must be a positive integer")
    entry: JsonObject = {
        "kind": "community",
        "origin": "community_submission",
        "trust_label": "project_anchor",
        "agentic_provenance": "project_attested",
        "provenance_notes": [
            "maintainer_verified_exact_gguf",
            "maintainer_two_run_agentic_verification",
        ],
        "family": family,
        "model_id": model_id,
        "model_label": model_label,
        "quant_label": quant,
        "publisher": publisher,
        "gguf_repo": gguf_repo,
        "file": None,
        "reasoning_lane": _required_text(suite, "lane"),
        "independent_replication": False,
        "release_date": None,
        "vram_footprint_gb": size / 1_000_000_000,
        "notes": (
            f"Maintainer-landed exact GGUF {model_sha}; coding verdicts re-executed by the sandbox verifier, "
            "two-run agentic verification attached, and scorecard identity + budget audit re-derived with "
            "model generations unchanged."
        ),
    }
    return entry


def _canonical_path(run: JsonObject, model_sha: str) -> Path:
    name = _required_text(_object(run.get("model"), "run model"), "name")
    lane = _required_text(_object(_object(run.get("manifest"), "manifest").get("suite"), "manifest.suite"), "lane")
    return LANDED_RUNS_DIR / f"{slugify(name)}-{model_sha[:12]}-{slugify(lane)}.json"


def _model_sha(run: JsonObject) -> str:
    top = _required_text(_object(run.get("model"), "run model"), "file_sha256")
    manifest = _required_text(
        _object(_object(run.get("manifest"), "manifest").get("model"), "manifest.model"),
        "file_sha256",
    )
    if top != manifest or re.fullmatch(r"[0-9a-f]{64}", top) is None:
        raise LandingError("run model SHA-256 is missing, malformed, or inconsistent")
    return top


def _source_for_artifact(sources: list[JsonObject], model_sha: str) -> JsonObject | None:
    for source in sources:
        raw_path = source.get("file")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            continue
        try:
            run = _read_object(path, "curated run")
            if _model_sha(run) == model_sha:
                return source
        except (LandingError, OSError, json.JSONDecodeError):
            continue
    return None


def _candidate_system(board: JsonObject, stem: str, source: JsonObject) -> JsonObject:
    slug = slugify(_required_text(source, "model_label"))
    model = next(
        (item for item in _object_list(board.get("models"), "candidate models") if item.get("slug") == slug),
        None,
    )
    if model is None:
        raise LandingError(f"candidate board omitted landed model {slug}")
    run_id = f"{slug}__{stem}"
    system = next(
        (item for item in _object_list(model.get("systems"), f"{slug}.systems") if item.get("run_id") == run_id),
        None,
    )
    if system is None:
        raise LandingError(f"candidate board omitted landed system {run_id}")
    return system


def _preflight_web_build(sources: Path, board: Path, out_dir: Path) -> None:
    env = os.environ.copy()
    env["LOCALBENCH_BOARD_PATH"] = str(board)
    command = [sys.executable, "build_data.py", "--sources", str(sources), "--out", str(out_dir)]
    _checked(command, cwd=REPO_ROOT / "web", env=env, label="candidate web data build")


def _run_web_build() -> None:
    _checked([sys.executable, "build_data.py"], cwd=REPO_ROOT / "web", env=None, label="web data build")


def _checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    label: str,
) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LandingError(f"{label} failed: {detail}")


def _git_object_hash(path: Path) -> str:
    result = subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise LandingError(f"git hash-object failed for {path}: {result.stderr.strip()}")
    return value


def _update_launch_freeze(board_hash: str) -> None:
    original = LAUNCH_FREEZE_PATH.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(boardSha256:\s*")[0-9a-f]+(")',
        rf"\g<1>{board_hash}\g<2>",
        original,
        count=1,
    )
    if count != 1:
        raise LandingError(f"could not locate boardSha256 in {LAUNCH_FREEZE_PATH}")
    atomic_write_bytes(updated.encode("utf-8"), LAUNCH_FREEZE_PATH)


def _validate_launch_freeze() -> None:
    value = LAUNCH_FREEZE_PATH.read_text(encoding="utf-8")
    if re.search(r'boardSha256:\s*"[0-9a-f]+"', value) is None:
        raise LandingError(f"could not locate boardSha256 in {LAUNCH_FREEZE_PATH}")


def _append_json_array_item(original: bytes, item: JsonObject) -> bytes:
    text = original.decode("utf-8")
    stripped = text.rstrip()
    if not stripped.endswith("]"):
        raise LandingError(f"{DATA_SOURCES_PATH} is not a JSON array")
    prefix = stripped[:-1].rstrip()
    separator = ",\n" if prefix.endswith("}") else "\n"
    rendered = json.dumps(item, indent=2, ensure_ascii=False, allow_nan=False)
    indented = "\n".join("  " + line for line in rendered.splitlines())
    return f"{prefix}{separator}{indented}\n]\n".encode("utf-8")


def _generated_at(board: JsonObject) -> str | None:
    manifest = board.get("manifest")
    return _optional_text(manifest.get("generated_at")) if isinstance(manifest, dict) else None


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: JsonValue | None, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise LandingError(f"{label} must be an object")
    return value


def _object_list(value: JsonValue | None, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LandingError(f"{label} must be an array of objects")
    return list(value)


def _required_text(value: JsonObject, key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text:
        raise LandingError(f"{key} must be a non-empty string")
    return text


def _optional_text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def _template_text(template: JsonObject | None, key: str) -> str | None:
    return None if template is None else _optional_text(template.get(key))


__all__ = [
    "LandingError",
    "LandingResult",
    "changed_existing_ranked_rows",
    "land_run",
    "print_landing_checklist",
]
