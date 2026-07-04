from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from localbench._types import JsonObject
from localbench.suite_errors import SuiteResolutionError
from localbench.suite_resolver import DEFAULT_SUITE_ID, RemoteSuiteFetch, fetch_suite_from_manifest_url, suite_hash


def test_fetch_suite_from_manifest_url_downloads_and_hash_verifies_files(tmp_path: Path) -> None:
    # Given: a suite manifest served from local-bench.ai with file-level hashes.
    source = _write_suite(tmp_path / "source")
    manifest_url = "https://local-bench.ai/api/suites/core-text-v1/manifest"
    base_url = "https://local-bench.ai/suites/core-text-v1/"
    manifest = {
        "schema_version": "localbench.suite-manifest.v1",
        "files": [
            _manifest_file(source, base_url, "suite.json"),
            _manifest_file(source, base_url, "itemsets.lock.json"),
            _manifest_file(source, base_url, "mmlu_pro.jsonl"),
        ],
        "suite_hash": suite_hash(source),
        "suite_id": DEFAULT_SUITE_ID,
        "version": "core-text-v1",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        match str(request.url):
            case "https://local-bench.ai/api/suites/core-text-v1/manifest":
                return httpx.Response(200, json=manifest)
            case "https://local-bench.ai/suites/core-text-v1/suite.json":
                return httpx.Response(200, content=(source / "suite.json").read_bytes())
            case "https://local-bench.ai/suites/core-text-v1/itemsets.lock.json":
                return httpx.Response(200, content=(source / "itemsets.lock.json").read_bytes())
            case "https://local-bench.ai/suites/core-text-v1/mmlu_pro.jsonl":
                return httpx.Response(200, content=(source / "mmlu_pro.jsonl").read_bytes())
            case unreachable:
                raise AssertionError(f"unexpected URL: {unreachable}")

    # When: the CLI fetches the suite from the manifest.
    resolved = fetch_suite_from_manifest_url(
        RemoteSuiteFetch(
            accept_suite_terms=True,
            cache_root=tmp_path / "cache",
            manifest_url=manifest_url,
            transport=httpx.MockTransport(handler),
        ),
    )

    # Then: the verified suite is cached under its content hash.
    assert resolved.suite_id == DEFAULT_SUITE_ID
    assert resolved.source == "remote-manifest"
    assert resolved.path == tmp_path / "cache" / "suites" / DEFAULT_SUITE_ID / suite_hash(source)
    assert (resolved.path / "mmlu_pro.jsonl").read_bytes() == (source / "mmlu_pro.jsonl").read_bytes()


def test_fetch_suite_from_manifest_url_fails_closed_on_file_hash_mismatch(tmp_path: Path) -> None:
    # Given: a manifest whose file hash does not match the downloaded bytes.
    source = _write_suite(tmp_path / "source")
    manifest = {
        "schema_version": "localbench.suite-manifest.v1",
        "files": [
            {
                "path": "suite.json",
                "sha256": "0" * 64,
                "size": len((source / "suite.json").read_bytes()),
                "url": "https://local-bench.ai/suites/core-text-v1/suite.json",
            },
        ],
        "suite_hash": suite_hash(source),
        "suite_id": DEFAULT_SUITE_ID,
        "version": "core-text-v1",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/manifest"):
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, content=(source / "suite.json").read_bytes())

    # When / Then: the cache is not populated from tampered bytes.
    with pytest.raises(SuiteResolutionError, match="sha256 mismatch"):
        fetch_suite_from_manifest_url(
            RemoteSuiteFetch(
                accept_suite_terms=True,
                cache_root=tmp_path / "cache",
                manifest_url="https://local-bench.ai/api/suites/core-text-v1/manifest",
                transport=httpx.MockTransport(handler),
            ),
        )


def _manifest_file(source: Path, base_url: str, name: str) -> JsonObject:
    data = (source / name).read_bytes()
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "url": f"{base_url}{name}"}


def _write_suite(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "mmlu_pro.jsonl").write_text(
        '{"id":"1","question":"Pick A","options":["A","B"],"answer":"A"}\n',
        encoding="utf-8",
    )
    item_hash = hashlib.sha256((path / "mmlu_pro.jsonl").read_bytes()).hexdigest()
    (path / "suite.json").write_text(
        json.dumps(
            {
                "benches": {
                    "mmlu_pro": {
                        "chance_correction_baseline": 0.5,
                        "decoding": {"max_tokens": 16, "temperature": 0},
                        "itemsets": {"standard": {"file": "mmlu_pro.jsonl", "item_count": 1, "sha256": item_hash}},
                        "template_text": "{question}\n{options}",
                    },
                },
                "id": DEFAULT_SUITE_ID,
                "version": "core-text-v1",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (path / "itemsets.lock.json").write_text(
        json.dumps({"files": {"mmlu_pro.jsonl": {"item_count": 1, "sha256": item_hash}}}, sort_keys=True),
        encoding="utf-8",
    )
    return path
