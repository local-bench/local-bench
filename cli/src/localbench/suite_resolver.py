"""Distribution-aware suite resolution."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from localbench._types import JsonObject, JsonValue
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_verify import license_manifest, read_json_object, suite_hash, verify_suite_dir

DEFAULT_SUITE_ID: Final = "core-text-v1"
TINY_SMOKE_SUITE_ID: Final = "tiny-smoke-v1"
LOCALBENCH_SUITE_DIR_ENV: Final = "LOCALBENCH_SUITE_DIR"
LOCALBENCH_SUITE_SOURCE_ENV: Final = "LOCALBENCH_SUITE_SOURCE"
LOCALBENCH_CACHE_DIR_ENV: Final = "LOCALBENCH_CACHE_DIR"

SuiteSource = Literal["suite-dir", "env", "cache", "package-data", "local-source"]


@dataclass(frozen=True, slots=True)
class SuiteRef:
    suite_id: str
    path: Path
    suite_hash: str
    source: SuiteSource
    version: str
    license_manifest: JsonObject


def resolve_suite_dir(
    *,
    suite_id: str = DEFAULT_SUITE_ID,
    suite_dir: Path | None = None,
    accept_suite_terms: bool = False,
    source: Path | None = None,
    cache_root: Path | None = None,
) -> SuiteRef:
    """Resolve a suite in the planned fail-closed order."""
    normalized_id = normalize_suite_id(suite_id)
    if suite_dir is not None:
        return _verified_ref(normalized_id, suite_dir, "suite-dir")

    env_dir = os.environ.get(LOCALBENCH_SUITE_DIR_ENV)
    if env_dir:
        return _verified_ref(normalized_id, Path(env_dir), "env")

    cached = _cached_suite(normalized_id, cache_root)
    if cached is not None:
        return cached

    packaged = _package_data_suite(normalized_id)
    if packaged is not None:
        return packaged

    source_path = source or _env_path(LOCALBENCH_SUITE_SOURCE_ENV)
    if source_path is not None:
        return fetch_suite(
            suite_id=normalized_id,
            source=source_path,
            accept_suite_terms=accept_suite_terms,
            cache_root=cache_root,
        )
    raise SuiteResolutionError(
        f"suite {normalized_id!r} was not found in --suite-dir, "
        f"{LOCALBENCH_SUITE_DIR_ENV}, or the user cache; remote auto-fetch is "
        "not configured in this local build, so provide --suite-source or run "
        "fetch-suite --source with --accept-suite-terms",
    )


def fetch_suite(
    *,
    suite_id: str = DEFAULT_SUITE_ID,
    source: Path | None = None,
    accept_suite_terms: bool,
    cache_root: Path | None = None,
) -> SuiteRef:
    """Verify a local suite source and copy it into the user cache."""
    normalized_id = normalize_suite_id(suite_id)
    if not accept_suite_terms:
        raise SuiteResolutionError(
            "fetch-suite requires --accept-suite-terms before redistributing "
            "public suite items into the local cache",
        )
    source_ref = _packaged_or_local_source(normalized_id, source)
    source_path = source_ref.path
    if not source_path.is_dir():
        raise SuiteResolutionError(
            f"local suite source must be an extracted directory: {source_path}",
        )
    target = suite_cache_root(cache_root) / normalized_id / source_ref.suite_hash
    if target.exists():
        return _verified_ref(normalized_id, target, source_ref.source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_path, target)
    return _verified_ref(normalized_id, target, source_ref.source)


def suite_cache_root(cache_root: Path | None = None) -> Path:
    """Return the directory that contains cached suites."""
    root = cache_root or _env_path(LOCALBENCH_CACHE_DIR_ENV)
    if root is None:
        root = Path.home() / ".cache" / "localbench"
    return root.expanduser() / "suites"


def normalize_suite_id(suite_id: str) -> str:
    """Normalize public aliases without accepting ambiguous suite names."""
    match suite_id:
        case "v1" | "suite-v1" | "core-text-v1":
            return DEFAULT_SUITE_ID
        case "smoke" | "tiny-smoke" | "tiny-smoke-v1":
            return TINY_SMOKE_SUITE_ID
        case _:
            return suite_id


def _verified_ref(suite_id: str, path: Path, source: SuiteSource) -> SuiteRef:
    resolved_path = path.expanduser().resolve()
    verify_suite_dir(resolved_path)
    suite = read_json_object(resolved_path / "suite.json")
    return SuiteRef(
        suite_id=suite_id,
        path=resolved_path,
        suite_hash=suite_hash(resolved_path),
        source=source,
        version=_text(suite.get("version")) or suite_id,
        license_manifest=license_manifest(suite, resolved_path),
    )


def _cached_suite(suite_id: str, cache_root: Path | None) -> SuiteRef | None:
    root = suite_cache_root(cache_root) / suite_id
    if not root.exists():
        return None
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    for candidate in candidates:
        ref = _verified_ref(suite_id, candidate, "cache")
        if candidate.name != ref.suite_hash:
            raise SuiteResolutionError(
                f"cached suite hash directory mismatch: {candidate.name} != {ref.suite_hash}",
            )
        return ref
    return None


def _package_data_suite(suite_id: str) -> SuiteRef | None:
    if suite_id not in {DEFAULT_SUITE_ID, TINY_SMOKE_SUITE_ID}:
        return None
    package_suite = Path(__file__).resolve().parent / "data" / "suites" / suite_id
    return _verified_ref(suite_id, package_suite, "package-data")


def _packaged_or_local_source(suite_id: str, source: Path | None) -> SuiteRef:
    if source is not None:
        return _verified_ref(suite_id, source.expanduser().resolve(), "local-source")
    packaged = _package_data_suite(suite_id)
    if packaged is None:
        raise SuiteResolutionError(
            f"suite {suite_id!r} is not bundled with this localbench build; "
            "provide --source with --accept-suite-terms",
        )
    return packaged


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None
