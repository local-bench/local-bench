"""Distribution-aware suite resolution."""

from __future__ import annotations

import os
import shutil
import tempfile
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal
from urllib.parse import unquote, urljoin, urlparse

import httpx

from localbench._types import JsonObject, JsonValue
from localbench.http_errors import raise_for_status_with_body
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_release import SUITE_RELEASE_MANIFEST_FILE, suite_manifest_sha256
from localbench.suite_verify import license_manifest, read_json_object, suite_hash, verify_suite_dir

DEFAULT_SUITE_ID: Final = "suite-v1-full-exec-6axis-v1"
CORE_TEXT_SUITE_ID: Final = "core-text-v1"
TINY_SMOKE_SUITE_ID: Final = "tiny-smoke-v1"
STATIC_EXEC_SUITE_ID: Final = "suite-v1-static-exec-5axis-v1"
STATIC_CORE_DIAG_SUITE_ID: Final = "suite-v1-static-core-diag-v1"
PARTIAL_TEXT_CODE_SUITE_ID: Final = "suite-v1-partial-text-code-4axis-v1"
LEGACY_TEXT_CODE_AGENTIC_SUITE_ID: Final = "suite-v1-text-code-agentic-5axis-v1"
KNOWN_SUITE_IDS: Final[tuple[str, ...]] = (
    DEFAULT_SUITE_ID,
    STATIC_EXEC_SUITE_ID,
    STATIC_CORE_DIAG_SUITE_ID,
    LEGACY_TEXT_CODE_AGENTIC_SUITE_ID,
    PARTIAL_TEXT_CODE_SUITE_ID,
    CORE_TEXT_SUITE_ID,
    TINY_SMOKE_SUITE_ID,
)
LOCALBENCH_SUITE_DIR_ENV: Final = "LOCALBENCH_SUITE_DIR"
LOCALBENCH_SUITE_SOURCE_ENV: Final = "LOCALBENCH_SUITE_SOURCE"
LOCALBENCH_CACHE_DIR_ENV: Final = "LOCALBENCH_CACHE_DIR"

SuiteSource = Literal["suite-dir", "env", "cache", "package-data", "local-source", "remote-manifest"]


@dataclass(frozen=True, slots=True)
class SuiteRef:
    suite_id: str
    path: Path
    suite_hash: str
    source: SuiteSource
    version: str
    license_manifest: JsonObject


@dataclass(frozen=True, slots=True)
class RemoteSuiteFetch:
    accept_suite_terms: bool
    manifest_url: str
    cache_root: Path | None = None
    transport: httpx.BaseTransport | None = None
    bypass_token: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteSuiteFile:
    path: str
    sha256: str
    size: int
    url: str | None


@dataclass(frozen=True, slots=True)
class RemoteSuiteManifest:
    files: tuple[RemoteSuiteFile, ...]
    suite_hash: str | None
    suite_id: str
    suite_manifest_sha256: str | None
    version: str


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


def fetch_suite_from_manifest_url(config: RemoteSuiteFetch) -> SuiteRef:
    if not config.accept_suite_terms:
        raise SuiteResolutionError(
            "fetch-suite requires --accept-suite-terms before redistributing "
            "public suite items into the local cache",
        )
    local_manifest = _local_manifest_path(config.manifest_url)
    if local_manifest is not None:
        return _fetch_suite_from_local_manifest(config, local_manifest)
    with _http_client(config.transport) as client:
        manifest_response = client.get(
            config.manifest_url,
            headers=_bypass_headers(config.bypass_token, config.manifest_url, config.manifest_url),
        )
        raise_for_status_with_body(manifest_response)
        manifest = _remote_manifest(manifest_response.json(), base_url=config.manifest_url)
        with tempfile.TemporaryDirectory(prefix="localbench-suite-") as temp_name:
            temp_dir = Path(temp_name) / manifest.suite_id
            temp_dir.mkdir()
            for suite_file in manifest.files:
                _download_suite_file(
                    client,
                    temp_dir,
                    suite_file,
                    bypass_origin=config.manifest_url,
                    bypass_token=config.bypass_token,
                )
            if manifest.suite_manifest_sha256 is not None:
                _write_release_manifest_copy(temp_dir, manifest_response.json())
            ref = _verified_ref(manifest.suite_id, temp_dir, "remote-manifest")
            if manifest.suite_hash is not None and ref.suite_hash != manifest.suite_hash:
                raise SuiteResolutionError(
                    f"suite hash mismatch: {ref.suite_hash} != {manifest.suite_hash}",
                )
            target = suite_cache_root(config.cache_root) / manifest.suite_id / ref.suite_hash
            if target.exists():
                return _verified_ref(manifest.suite_id, target, "remote-manifest")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(temp_dir, target)
            return _verified_ref(manifest.suite_id, target, "remote-manifest")


def suite_cache_root(cache_root: Path | None = None) -> Path:
    """Return the directory that contains cached suites."""
    root = cache_root or _env_path(LOCALBENCH_CACHE_DIR_ENV)
    if root is None:
        root = Path.home() / ".cache" / "localbench"
    return root.expanduser() / "suites"


def normalize_suite_id(suite_id: str) -> str:
    """Normalize public aliases without accepting ambiguous suite names."""
    match suite_id:
        case "v1" | "suite-v1":
            return DEFAULT_SUITE_ID
        case "core-text-v1":
            return CORE_TEXT_SUITE_ID
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
    if suite_id not in {CORE_TEXT_SUITE_ID, TINY_SMOKE_SUITE_ID}:
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


def _http_client(transport: httpx.BaseTransport | None) -> httpx.Client:
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
    if transport is not None:
        return httpx.Client(transport=transport, timeout=timeout, follow_redirects=True)
    return httpx.Client(
        transport=httpx.HTTPTransport(retries=3),
        timeout=timeout,
        follow_redirects=True,
    )


def _fetch_suite_from_local_manifest(config: RemoteSuiteFetch, manifest_path: Path) -> SuiteRef:
    manifest_value = read_json_object(manifest_path)
    manifest = _remote_manifest(manifest_value, base_url=None)
    with tempfile.TemporaryDirectory(prefix="localbench-suite-") as temp_name:
        temp_dir = Path(temp_name) / manifest.suite_id
        temp_dir.mkdir()
        for suite_file in manifest.files:
            _copy_suite_file(manifest_path.parent, temp_dir, suite_file)
        _write_release_manifest_copy(temp_dir, manifest_value)
        ref = _verified_ref(manifest.suite_id, temp_dir, "remote-manifest")
        if manifest.suite_hash is not None and ref.suite_hash != manifest.suite_hash:
            raise SuiteResolutionError(
                f"suite hash mismatch: {ref.suite_hash} != {manifest.suite_hash}",
            )
        target = suite_cache_root(config.cache_root) / manifest.suite_id / ref.suite_hash
        if target.exists():
            return _verified_ref(manifest.suite_id, target, "remote-manifest")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temp_dir, target)
        return _verified_ref(manifest.suite_id, target, "remote-manifest")


def _remote_manifest(value: JsonValue, *, base_url: str | None) -> RemoteSuiteManifest:
    if not isinstance(value, dict):
        raise SuiteResolutionError("suite manifest must be a JSON object")
    schema_version = value.get("schema_version")
    match schema_version:
        case "localbench.suite-manifest.v1":
            return _legacy_remote_manifest(value)
        case "localbench.suite_release_manifest.v1":
            return _suite_release_manifest(value, base_url=base_url)
        case _:
            raise SuiteResolutionError("suite manifest schema_version is not supported")


def _legacy_remote_manifest(value: JsonObject) -> RemoteSuiteManifest:
    suite_id = _required_text(value, "suite_id")
    files_value = value.get("files")
    if not isinstance(files_value, list):
        raise SuiteResolutionError("suite manifest files must be a list")
    return RemoteSuiteManifest(
        files=tuple(_remote_file(file_value) for file_value in files_value),
        suite_hash=_required_hash(value, "suite_hash"),
        suite_id=normalize_suite_id(suite_id),
        suite_manifest_sha256=None,
        version=_required_text(value, "version"),
    )


def _suite_release_manifest(value: JsonObject, *, base_url: str | None) -> RemoteSuiteManifest:
    expected = _required_hash(value, "suite_manifest_sha256")
    actual = suite_manifest_sha256(value)
    if actual != expected:
        raise SuiteResolutionError(
            f"suite release manifest hash mismatch: {actual} != {expected}",
        )
    files_value = value.get("files")
    if not isinstance(files_value, list):
        raise SuiteResolutionError("suite release manifest files must be a list")
    suite_id = _required_text(value, "suite_release_id")
    return RemoteSuiteManifest(
        files=tuple(_suite_release_file(file_value, base_url=base_url) for file_value in files_value),
        suite_hash=None,
        suite_id=normalize_suite_id(suite_id),
        suite_manifest_sha256=expected,
        version=_required_text(value, "suite_semver"),
    )


def _remote_file(value: JsonValue) -> RemoteSuiteFile:
    if not isinstance(value, dict):
        raise SuiteResolutionError("suite manifest file entries must be objects")
    size_value = value.get("size")
    if not isinstance(size_value, int) or size_value < 0:
        raise SuiteResolutionError("suite manifest file size must be a non-negative integer")
    return RemoteSuiteFile(
        path=_safe_relative_path(_required_text(value, "path")),
        sha256=_required_hash(value, "sha256"),
        size=size_value,
        url=_required_text(value, "url"),
    )


def _suite_release_file(value: JsonValue, *, base_url: str | None) -> RemoteSuiteFile:
    if not isinstance(value, dict):
        raise SuiteResolutionError("suite release manifest file entries must be objects")
    size_value = value.get("size")
    if not isinstance(size_value, int) or size_value < 0:
        raise SuiteResolutionError("suite release manifest file size must be a non-negative integer")
    path = _safe_relative_path(_required_text(value, "path"))
    return RemoteSuiteFile(
        path=path,
        sha256=_required_hash(value, "sha256"),
        size=size_value,
        url=urljoin(base_url, path) if base_url is not None else None,
    )


def _download_suite_file(
    client: httpx.Client,
    suite_dir: Path,
    suite_file: RemoteSuiteFile,
    *,
    bypass_origin: str,
    bypass_token: str | None,
) -> None:
    if suite_file.url is None:
        raise SuiteResolutionError(f"suite file {suite_file.path} is missing a download URL")
    response = client.get(
        suite_file.url,
        headers=_bypass_headers(bypass_token, bypass_origin, suite_file.url),
    )
    raise_for_status_with_body(response)
    data = response.content
    _write_verified_suite_file(suite_dir, suite_file, data)


def _copy_suite_file(source_dir: Path, suite_dir: Path, suite_file: RemoteSuiteFile) -> None:
    source = source_dir / Path(*PurePosixPath(suite_file.path).parts)
    try:
        data = source.read_bytes()
    except FileNotFoundError as error:
        raise SuiteResolutionError(f"missing suite file: {suite_file.path}") from error
    _write_verified_suite_file(suite_dir, suite_file, data)


def _write_verified_suite_file(suite_dir: Path, suite_file: RemoteSuiteFile, data: bytes) -> None:
    if len(data) != suite_file.size:
        raise SuiteResolutionError(
            f"suite file size mismatch for {suite_file.path}: {len(data)} != {suite_file.size}",
        )
    digest = hashlib.sha256(data).hexdigest()
    if digest != suite_file.sha256:
        raise SuiteResolutionError(
            f"suite file sha256 mismatch for {suite_file.path}: {digest} != {suite_file.sha256}",
        )
    target = suite_dir / suite_file.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _write_release_manifest_copy(suite_dir: Path, manifest: JsonValue) -> None:
    if not isinstance(manifest, dict):
        return
    target = suite_dir / SUITE_RELEASE_MANIFEST_FILE
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bypass_headers(token: str | None, origin_url: str, request_url: str) -> dict[str, str]:
    if token is None or not _same_origin(origin_url, request_url):
        return {}
    return {"x-localbench-bypass": token}


def _same_origin(left: str, right: str) -> bool:
    left_url = urlparse(left)
    right_url = urlparse(right)
    return left_url.scheme == right_url.scheme and left_url.netloc == right_url.netloc


def _local_manifest_path(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).expanduser().resolve()
    if parsed.scheme in {"http", "https"}:
        return None
    return Path(value).expanduser().resolve()


def _safe_relative_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value.replace("\\", "/").startswith("/"):
        raise SuiteResolutionError(f"suite manifest path is unsafe: {value}")
    return value.replace("\\", "/")


def _required_text(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SuiteResolutionError(f"suite manifest {key} must be a non-empty string")
    return item


def _required_hash(value: JsonObject, key: str) -> str:
    item = _required_text(value, key)
    if len(item) != 64:
        raise SuiteResolutionError(f"suite manifest {key} must be a sha256 hex digest")
    try:
        bytes.fromhex(item)
    except ValueError as error:
        raise SuiteResolutionError(f"suite manifest {key} must be a sha256 hex digest") from error
    return item
