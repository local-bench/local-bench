"""Tests for distribution suite resolution and hash verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from localbench.suite_resolver import (
    DEFAULT_SUITE_ID,
    LOCALBENCH_SUITE_DIR_ENV,
    SuiteResolutionError,
    fetch_suite,
    resolve_suite_dir,
    suite_cache_root,
    suite_hash,
)


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
