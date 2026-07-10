from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import httpx
import pytest

from localbench._types import JsonObject
from localbench.one_shot.runner import _verify_suite_identity
from localbench.one_shot.types import FULL_EXEC_SUITE_IDENTITY
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_resolver import DEFAULT_SUITE_ID, RemoteSuiteFetch, fetch_suite_from_manifest_url, suite_hash

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FULL_EXEC_SUITE = _REPO_ROOT / "web" / "public" / "suites" / DEFAULT_SUITE_ID
_RELEASE_MANIFEST = _FULL_EXEC_SUITE / "suite_release_manifest.json"
_MANIFEST_URL = f"https://local-bench.ai/api/suites/{DEFAULT_SUITE_ID}/manifest"
_SUITE_BASE_URL = f"https://local-bench.ai/suites/{DEFAULT_SUITE_ID}/"


def test_fetch_suite_downloads_release_manifest_refreshes_cache_and_verifies_identity(
    tmp_path: Path,
) -> None:
    # Given: the live-site shape: the hash-verified fetch manifest does not list the
    # separately served suite release manifest.
    manifest = _legacy_fetch_manifest()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, content=_site_file(request).read_bytes())

    config = RemoteSuiteFetch(
        accept_suite_terms=True,
        cache_root=tmp_path / "cache",
        manifest_url=_MANIFEST_URL,
        transport=httpx.MockTransport(handler),
    )

    # When: the suite is fetched, then fetched again after simulating a 0.3.1 cache
    # that has all executable files but lacks the release manifest.
    resolved = fetch_suite_from_manifest_url(config)
    cached_manifest = resolved.path / "suite_release_manifest.json"
    assert cached_manifest.read_bytes() == _RELEASE_MANIFEST.read_bytes()
    _verify_suite_identity(resolved.path, FULL_EXEC_SUITE_IDENTITY)
    cached_manifest.unlink()
    refreshed = fetch_suite_from_manifest_url(config)

    # Then: the same cache directory is repaired without manual deletion and is a
    # valid one-shot suite identity end to end.
    assert refreshed.path == resolved.path
    assert refreshed.path == tmp_path / "cache" / "suites" / DEFAULT_SUITE_ID / suite_hash(_FULL_EXEC_SUITE)
    assert cached_manifest.read_bytes() == _RELEASE_MANIFEST.read_bytes()
    _verify_suite_identity(refreshed.path, FULL_EXEC_SUITE_IDENTITY)
    assert requests.count(f"{_SUITE_BASE_URL}suite_release_manifest.json") == 2


def test_fetch_suite_from_manifest_url_fails_closed_on_file_hash_mismatch(tmp_path: Path) -> None:
    # Given: a valid pinned release manifest but a fetch manifest whose suite.json
    # hash does not match the downloaded bytes.
    manifest = _legacy_fetch_manifest()
    suite_file = next(file for file in manifest["files"] if file["path"] == "suite.json")
    assert isinstance(suite_file, dict)
    suite_file["sha256"] = "0" * 64
    manifest["files"] = [suite_file]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, content=_site_file(request).read_bytes())

    # When / Then: the cache is not populated from tampered bytes.
    with pytest.raises(SuiteResolutionError, match="suite file sha256 mismatch for suite.json"):
        fetch_suite_from_manifest_url(
            RemoteSuiteFetch(
                accept_suite_terms=True,
                cache_root=tmp_path / "cache",
                manifest_url=_MANIFEST_URL,
                transport=httpx.MockTransport(handler),
            ),
        )


def test_fetch_suite_rejects_unpinned_release_manifest_content(tmp_path: Path) -> None:
    # Given: the fetched release manifest declares the pinned hash but its content was altered.
    manifest = _legacy_fetch_manifest()
    release = json.loads(_RELEASE_MANIFEST.read_text(encoding="utf-8"))
    release["coverage_profile_id"] = "tampered"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        if request.url.path.endswith("/suite_release_manifest.json"):
            return httpx.Response(200, json=release)
        return httpx.Response(200, content=_site_file(request).read_bytes())

    # When / Then: canonical release-pair verification fails before the cache is populated.
    with pytest.raises(SuiteResolutionError, match="suite release manifest sha256 mismatch"):
        fetch_suite_from_manifest_url(
            RemoteSuiteFetch(
                accept_suite_terms=True,
                cache_root=tmp_path / "cache",
                manifest_url=_MANIFEST_URL,
                transport=httpx.MockTransport(handler),
            ),
        )


def test_fetch_suite_reports_stale_suite_when_site_lacks_release_manifest(tmp_path: Path) -> None:
    # Given: an older site manifest that serves executable files but not the release manifest.
    manifest = _legacy_fetch_manifest()

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _MANIFEST_URL:
            return httpx.Response(200, json=manifest)
        if request.url.path.endswith("/suite_release_manifest.json"):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, content=_site_file(request).read_bytes())

    # When / Then: fetch fails as a controlled stale-suite preflight error.
    with pytest.raises(
        SuiteResolutionError,
        match=r"suite 'suite-v1-full-exec-6axis-v1' is stale: site does not serve suite_release_manifest.json",
    ):
        fetch_suite_from_manifest_url(
            RemoteSuiteFetch(
                accept_suite_terms=True,
                cache_root=tmp_path / "cache",
                manifest_url=_MANIFEST_URL,
                transport=httpx.MockTransport(handler),
            ),
        )


def _legacy_fetch_manifest() -> JsonObject:
    release = json.loads(_RELEASE_MANIFEST.read_text(encoding="utf-8"))
    files = release["files"]
    assert isinstance(files, list)
    return {
        "schema_version": "localbench.suite-manifest.v1",
        "files": [
            {
                "path": file["path"],
                "sha256": file["sha256"],
                "size": file["size"],
                "url": f"{_SUITE_BASE_URL}{file['path']}",
            }
            for file in files
            if isinstance(file, dict)
        ],
        "suite_hash": suite_hash(_FULL_EXEC_SUITE),
        "suite_id": DEFAULT_SUITE_ID,
        "version": "suite-v1",
    }


def _site_file(request: httpx.Request) -> Path:
    prefix = f"/suites/{DEFAULT_SUITE_ID}/"
    assert request.url.path.startswith(prefix)
    relative = PurePosixPath(request.url.path.removeprefix(prefix))
    return _FULL_EXEC_SUITE.joinpath(*relative.parts)
