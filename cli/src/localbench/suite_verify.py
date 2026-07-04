"""Suite SHA-256 and item-set verification helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from localbench._types import JsonObject, JsonValue
from localbench.suite_errors import SuiteResolutionError


def suite_hash(suite_dir: Path) -> str:
    """Compute a stable content hash for executable suite files."""
    verified_files = _suite_files_for_hash(suite_dir)
    digest = hashlib.sha256()
    for relative in verified_files:
        data = (suite_dir / relative).read_bytes()
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify_suite_dir(suite_dir: Path) -> None:
    """Verify suite manifests, SHA256SUMS, and every locked item-set hash."""
    if not suite_dir.exists():
        raise SuiteResolutionError(f"suite directory does not exist: {suite_dir}")
    if not suite_dir.is_dir():
        raise SuiteResolutionError(f"suite path is not a directory: {suite_dir}")
    suite = read_json_object(suite_dir / "suite.json")
    lock = read_json_object(suite_dir / "itemsets.lock.json")
    _verify_locked_itemsets(suite_dir, lock)
    _verify_suite_manifest_hashes(suite, lock)
    _verify_sha256sums(suite_dir)


def read_json_object(path: Path) -> JsonObject:
    """Read a JSON object or raise a suite-resolution error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SuiteResolutionError(f"missing suite file: {path}") from error
    except json.JSONDecodeError as error:
        raise SuiteResolutionError(f"invalid JSON in suite file: {path}") from error
    return data if isinstance(data, dict) else {}


def license_manifest(suite: JsonObject, suite_dir: Path) -> JsonObject:
    """Return the accepted-license manifest carried by a suite."""
    manifest = suite.get("license_manifest")
    if isinstance(manifest, dict):
        return dict(manifest)
    lock = read_json_object(suite_dir / "itemsets.lock.json")
    files = lock.get("files")
    if not isinstance(files, dict):
        return {"files": {}}
    licenses: JsonObject = {}
    for file_name, entry in files.items():
        if not isinstance(file_name, str) or not isinstance(entry, dict):
            continue
        license_name = _text(entry.get("license"))
        if license_name is not None:
            licenses[file_name] = {"license": license_name}
    return {"files": licenses}


def _suite_files_for_hash(suite_dir: Path) -> tuple[Path, ...]:
    suite = read_json_object(suite_dir / "suite.json")
    lock = read_json_object(suite_dir / "itemsets.lock.json")
    files: set[Path] = {Path("suite.json"), Path("itemsets.lock.json")}
    locked = lock.get("files")
    if isinstance(locked, dict):
        files.update(Path(name) for name in locked if isinstance(name, str))
    benches = suite.get("benches")
    if isinstance(benches, dict):
        for bench in benches.values():
            if isinstance(bench, dict) and isinstance(bench.get("template"), str):
                files.add(Path(bench["template"]))
    return tuple(sorted(files, key=lambda value: value.as_posix()))


def _verify_locked_itemsets(suite_dir: Path, lock: JsonObject) -> None:
    files = lock.get("files")
    if not isinstance(files, dict) or not files:
        raise SuiteResolutionError("itemsets.lock.json must contain a non-empty files object")
    for name, entry in files.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise SuiteResolutionError("itemsets.lock.json files entries must be objects")
        expected_sha = _text(entry.get("sha256"))
        if expected_sha is None:
            raise SuiteResolutionError(f"{name}: missing sha256 in itemsets.lock.json")
        actual_sha = _file_sha256(suite_dir / name)
        if actual_sha != expected_sha:
            raise SuiteResolutionError(
                f"{name}: sha256 mismatch {actual_sha} != {expected_sha}",
            )
        expected_count = entry.get("item_count")
        if isinstance(expected_count, int) and not isinstance(expected_count, bool):
            actual_count = _jsonl_count(suite_dir / name)
            if actual_count != expected_count:
                raise SuiteResolutionError(
                    f"{name}: item_count mismatch {actual_count} != {expected_count}",
                )


def _verify_suite_manifest_hashes(suite: JsonObject, lock: JsonObject) -> None:
    benches = suite.get("benches")
    files = lock.get("files")
    if not isinstance(benches, dict) or not isinstance(files, dict):
        return
    for bench_name, bench in benches.items():
        if not isinstance(bench_name, str) or not isinstance(bench, dict):
            continue
        itemsets = bench.get("itemsets")
        if not isinstance(itemsets, dict):
            continue
        for tier, itemset in itemsets.items():
            if isinstance(tier, str) and isinstance(itemset, dict):
                _verify_manifest_itemset(bench_name, tier, itemset, files)


def _verify_manifest_itemset(
    bench_name: str,
    tier: str,
    itemset: Mapping[str, JsonValue],
    locked_files: Mapping[str, JsonValue],
) -> None:
    file_name = _text(itemset.get("file"))
    expected_sha = _text(itemset.get("sha256"))
    if file_name is None or expected_sha is None:
        raise SuiteResolutionError(f"{bench_name}.{tier}: file and sha256 are required")
    locked = locked_files.get(file_name)
    if not isinstance(locked, dict):
        raise SuiteResolutionError(f"{bench_name}.{tier}: {file_name} missing from lock")
    locked_sha = _text(locked.get("sha256"))
    if locked_sha != expected_sha:
        raise SuiteResolutionError(
            f"{bench_name}.{tier}: suite.json sha256 does not match itemsets.lock.json",
        )


def _verify_sha256sums(suite_dir: Path) -> None:
    sums_path = suite_dir / "SHA256SUMS"
    if not sums_path.exists():
        return
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64:
            raise SuiteResolutionError(f"invalid SHA256SUMS line: {line}")
        rel_path = PurePosixPath(relative)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise SuiteResolutionError(f"unsafe SHA256SUMS path: {relative}")
        actual = _file_sha256(suite_dir / Path(*rel_path.parts))
        if actual != digest:
            raise SuiteResolutionError(
                f"{relative}: SHA256SUMS mismatch {actual} != {digest}",
            )


def _jsonl_count(path: Path) -> int:
    count = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise SuiteResolutionError(f"missing item file: {path}") from error
    for line in lines:
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as error:
            raise SuiteResolutionError(f"invalid JSONL row in {path}") from error
        count += 1
    return count


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as error:
        raise SuiteResolutionError(f"missing hashed file: {path}") from error


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None
