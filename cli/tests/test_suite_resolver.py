"""Tests for distribution suite resolution and hash verification."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import httpx

from localbench.suite_resolver import (
    DEFAULT_SUITE_ID,
    LOCALBENCH_SUITE_DIR_ENV,
    RemoteSuiteFetch,
    SuiteResolutionError,
    fetch_suite,
    fetch_suite_from_manifest_url,
    resolve_suite_dir,
    suite_cache_root,
    suite_hash,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SITE_4AXIS = _REPO_ROOT / "web" / "public" / "suites" / "suite-v1-partial-text-code-4axis-v1"
_SITE_FULL = _REPO_ROOT / "web" / "public" / "suites" / DEFAULT_SUITE_ID


def test_resolve_suite_dir_when_explicit_path_is_given_wins_over_env_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: three valid suite locations.
    explicit = _write_suite(tmp_path / "explicit", version="explicit-suite")
    env_suite = _write_suite(tmp_path / "env", version="env-suite")
    cached = _write_suite(tmp_path / "cache-source", version="cache-suite")
    cache_root = tmp_path / "cache"
    cached_hash = suite_hash(cached)
    cache_target = cache_root / "suites" / DEFAULT_SUITE_ID / cached_hash
    _copy_suite(cached, cache_target)
    monkeypatch.setenv(LOCALBENCH_SUITE_DIR_ENV, str(env_suite))

    # When: resolving with an explicit suite dir.
    resolved = resolve_suite_dir(
        suite_id=DEFAULT_SUITE_ID,
        suite_dir=explicit,
        cache_root=cache_root,
    )

    # Then: the explicit path wins and was hash-verified.
    assert resolved.path == explicit
    assert resolved.source == "suite-dir"
    assert resolved.suite_hash == suite_hash(explicit)


def test_resolve_suite_dir_when_env_path_is_given_wins_over_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an env suite and a cached suite.
    env_suite = _write_suite(tmp_path / "env", version="env-suite")
    cached = _write_suite(tmp_path / "cache-source", version="cache-suite")
    cache_root = tmp_path / "cache"
    cache_target = cache_root / "suites" / DEFAULT_SUITE_ID / suite_hash(cached)
    _copy_suite(cached, cache_target)
    monkeypatch.setenv(LOCALBENCH_SUITE_DIR_ENV, str(env_suite))

    # When: resolving without --suite-dir.
    resolved = resolve_suite_dir(suite_id=DEFAULT_SUITE_ID, cache_root=cache_root)

    # Then: the environment path wins.
    assert resolved.path == env_suite
    assert resolved.source == "env"
    assert resolved.suite_hash == suite_hash(env_suite)


def test_resolve_suite_dir_when_cached_hash_matches_uses_user_cache(tmp_path: Path) -> None:
    # Given: a verified suite in the user cache under <id>/<hash>.
    source = _write_suite(tmp_path / "source", version="cache-suite")
    cache_root = tmp_path / "cache"
    expected_hash = suite_hash(source)
    cache_target = cache_root / "suites" / DEFAULT_SUITE_ID / expected_hash
    _copy_suite(source, cache_target)

    # When: resolving without explicit paths.
    resolved = resolve_suite_dir(suite_id=DEFAULT_SUITE_ID, cache_root=cache_root)

    # Then: the cached suite is selected.
    assert resolved.path == cache_target
    assert resolved.source == "cache"
    assert resolved.suite_hash == expected_hash


def test_resolve_suite_dir_when_item_hash_mismatches_fails_closed(tmp_path: Path) -> None:
    # Given: a suite whose lock claims the wrong item hash.
    suite_dir = _write_suite(tmp_path / "suite", version="bad-suite")
    lock_path = suite_dir / "itemsets.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["files"]["mmlu_pro.jsonl"]["sha256"] = "0" * 64
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    # When / Then: resolution fails instead of falling through to another source.
    with pytest.raises(SuiteResolutionError, match="sha256 mismatch"):
        resolve_suite_dir(suite_id=DEFAULT_SUITE_ID, suite_dir=suite_dir)


def test_resolve_suite_dir_when_tiny_smoke_requested_uses_package_data() -> None:
    # Given / When: the package-data smoke suite is requested.
    resolved = resolve_suite_dir(suite_id="tiny-smoke-v1")

    # Then: the fallback is a verified package-data suite.
    assert resolved.source == "package-data"
    assert resolved.path.name == "tiny-smoke-v1"
    assert resolved.suite_hash == suite_hash(resolved.path)


def test_fetch_suite_requires_terms_acceptance(tmp_path: Path) -> None:
    # Given: a local source suite.
    source = _write_suite(tmp_path / "source", version="source-suite")

    # When / Then: fetch refuses to redistribute without explicit acceptance.
    with pytest.raises(SuiteResolutionError, match="--accept-suite-terms"):
        fetch_suite(
            suite_id=DEFAULT_SUITE_ID,
            source=source,
            accept_suite_terms=False,
            cache_root=tmp_path / "cache",
        )


def test_fetch_suite_when_terms_accepted_copies_verified_local_source(tmp_path: Path) -> None:
    # Given: a local suite source and empty cache.
    source = _write_suite(tmp_path / "source", version="source-suite")
    cache_root = tmp_path / "cache"

    # When: fetching with explicit terms acceptance.
    resolved = fetch_suite(
        suite_id=DEFAULT_SUITE_ID,
        source=source,
        accept_suite_terms=True,
        cache_root=cache_root,
    )

    # Then: the verified suite is cached under its content hash.
    assert resolved.source == "local-source"
    assert resolved.path == cache_root / "suites" / DEFAULT_SUITE_ID / suite_hash(source)
    assert (resolved.path / "suite.json").exists()
    assert suite_cache_root(cache_root) == cache_root / "suites"


def test_fetch_suite_from_local_suite_release_manifest_verifies_manifest_hash(tmp_path: Path) -> None:
    # Given: the site-served 4-axis suite release manifest is addressed as a local fixture path.
    manifest_path = _SITE_4AXIS / "suite_release_manifest.json"

    # When: the remote-manifest resolver pulls it into a temp cache.
    resolved = fetch_suite_from_manifest_url(
        RemoteSuiteFetch(
            accept_suite_terms=True,
            manifest_url=str(manifest_path),
            cache_root=tmp_path / "cache",
        ),
    )

    # Then: the resolved runner suite is hash-verified and contains the coding axis item set.
    assert resolved.suite_id == "suite-v1-partial-text-code-4axis-v1"
    assert resolved.source == "remote-manifest"
    assert (resolved.path / "lcb.jsonl").exists()
    assert (resolved.path / "suite_release_manifest.json").read_bytes() == manifest_path.read_bytes()
    assert resolved.suite_hash == suite_hash(resolved.path)


def test_fetch_suite_from_local_legacy_manifest_copies_pinned_release_manifest(tmp_path: Path) -> None:
    # Given: a local copy of the live-site shape, where the legacy fetch manifest
    # sits beside a separately served release manifest.
    source = tmp_path / "source"
    shutil.copytree(_SITE_FULL, source)
    release = json.loads((source / "suite_release_manifest.json").read_text(encoding="utf-8"))
    files = release["files"]
    assert isinstance(files, list)
    fetch_manifest = source / "fetch-manifest.json"
    fetch_manifest.write_text(
        json.dumps(
            {
                "schema_version": "localbench.suite-manifest.v1",
                "suite_hash": suite_hash(source),
                "suite_id": DEFAULT_SUITE_ID,
                "version": "suite-v1",
                "files": [
                    {
                        "path": file["path"],
                        "sha256": file["sha256"],
                        "size": file["size"],
                        "url": f"https://local-bench.ai/suites/{DEFAULT_SUITE_ID}/{file['path']}",
                    }
                    for file in files
                    if isinstance(file, dict)
                ],
            },
        ),
        encoding="utf-8",
    )

    # When: the local legacy manifest is fetched into an empty cache.
    resolved = fetch_suite_from_manifest_url(
        RemoteSuiteFetch(
            accept_suite_terms=True,
            manifest_url=str(fetch_manifest),
            cache_root=tmp_path / "cache",
        ),
    )

    # Then: the separately stored release manifest is copied byte-for-byte.
    assert (resolved.path / "suite_release_manifest.json").read_bytes() == (
        source / "suite_release_manifest.json"
    ).read_bytes()


def test_fetch_suite_from_local_suite_release_manifest_rejects_manifest_hash_mismatch(
    tmp_path: Path,
) -> None:
    # Given: a local suite release manifest whose embedded canonical hash was tampered.
    manifest = json.loads((_SITE_4AXIS / "suite_release_manifest.json").read_text(encoding="utf-8"))
    manifest["suite_manifest_sha256"] = "0" * 64
    bad_manifest = tmp_path / "suite_release_manifest.json"
    bad_manifest.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    # When / Then: the resolver fails before copying runnable files.
    with pytest.raises(SuiteResolutionError, match="suite release manifest hash mismatch"):
        fetch_suite_from_manifest_url(
            RemoteSuiteFetch(
                accept_suite_terms=True,
                manifest_url=str(bad_manifest),
                cache_root=tmp_path / "cache",
            ),
        )


def test_fetch_suite_from_manifest_url_sends_bypass_header_to_site_requests(tmp_path: Path) -> None:
    # Given: the pinned full suite and its separately served release manifest.
    release = json.loads((_SITE_FULL / "suite_release_manifest.json").read_text(encoding="utf-8"))
    files = release["files"]
    assert isinstance(files, list)
    manifest_url = f"https://local-bench.ai/api/suites/{DEFAULT_SUITE_ID}/manifest"
    suite_prefix = f"/suites/{DEFAULT_SUITE_ID}/"
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers["x-localbench-bypass"] == "private-token"
        if request.url.path == f"/api/suites/{DEFAULT_SUITE_ID}/manifest":
            return httpx.Response(
                200,
                json={
                    "schema_version": "localbench.suite-manifest.v1",
                    "suite_hash": suite_hash(_SITE_FULL),
                    "suite_id": DEFAULT_SUITE_ID,
                    "version": "suite-v1",
                    "files": [
                        {
                            "path": file["path"],
                            "sha256": file["sha256"],
                            "size": file["size"],
                            "url": f"https://local-bench.ai{suite_prefix}{file['path']}",
                        }
                        for file in files
                        if isinstance(file, dict)
                    ],
                },
            )
        relative = request.url.path.removeprefix(suite_prefix)
        return httpx.Response(200, content=(_SITE_FULL / relative).read_bytes())

    # When: the remote fetcher pulls the suite through the site surface.
    resolved = fetch_suite_from_manifest_url(
        RemoteSuiteFetch(
            accept_suite_terms=True,
            bypass_token="private-token",
            cache_root=tmp_path / "cache",
            manifest_url=manifest_url,
            transport=httpx.MockTransport(handler),
        ),
    )

    # Then: both manifest and file calls carried the private-gate bypass header.
    assert resolved.source == "remote-manifest"
    assert seen_paths == [
        f"/api/suites/{DEFAULT_SUITE_ID}/manifest",
        f"{suite_prefix}suite_release_manifest.json",
        *(f"{suite_prefix}{file['path']}" for file in files if isinstance(file, dict)),
    ]


def _write_suite(path: Path, *, version: str) -> Path:
    path.mkdir(parents=True)
    (path / "mmlu_pro.jsonl").write_text(
        '{"id":"1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    (path / "ifbench.jsonl").write_text(
        '{"key":"if-1","prompt":"Say ok","instruction_id_list":[],"kwargs":[]}\n',
        encoding="utf-8",
    )
    mmlu_hash = _sha256(path / "mmlu_pro.jsonl")
    ifbench_hash = _sha256(path / "ifbench.jsonl")
    (path / "suite.json").write_text(
        json.dumps(
            {
                "id": DEFAULT_SUITE_ID,
                "version": version,
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {
                            "standard": {
                                "file": "mmlu_pro.jsonl",
                                "item_count": 1,
                                "sha256": mmlu_hash,
                            },
                        },
                        "template_text": "{question}\n{options}",
                    },
                    "ifbench": {
                        "chance_correction_baseline": 0.0,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {
                            "standard": {
                                "file": "ifbench.jsonl",
                                "item_count": 1,
                                "sha256": ifbench_hash,
                            },
                        },
                        "template_text": "{prompt}",
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps(
            {
                "files": {
                    "mmlu_pro.jsonl": {"item_count": 1, "sha256": mmlu_hash},
                    "ifbench.jsonl": {"item_count": 1, "sha256": ifbench_hash},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _copy_suite(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for source_file in source.iterdir():
        (target / source_file.name).write_bytes(source_file.read_bytes())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
