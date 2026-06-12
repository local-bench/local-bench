from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "suite"
if str(SUITE_DIR) not in sys.path:
    sys.path.insert(0, str(SUITE_DIR))

genmath_build = importlib.import_module("genmath_gen.build")
DEFAULT_PRIVATE_SEED = genmath_build.DEFAULT_PRIVATE_SEED
DEFAULT_SEED = genmath_build.DEFAULT_SEED
PRIVATE_FILE = genmath_build.PRIVATE_FILE
PRIVATE_LOCK_FILE = genmath_build.PRIVATE_LOCK_FILE
build_files = genmath_build.build_files
build_itemsets = genmath_build.build_itemsets
build_private_sentinel = genmath_build.build_private_sentinel
jsonl_bytes = genmath_build.jsonl_bytes

ParamSignature = tuple[str, tuple[tuple[str, str | int], ...]]
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def test_private_sentinel_when_seed_repeats_is_deterministic_and_disjoint() -> None:
    # Given the committed public item set and a private seed.
    public = build_itemsets(DEFAULT_SEED).standard

    # When generating the private sentinel twice.
    first = build_private_sentinel(public, DEFAULT_PRIVATE_SEED)
    second = build_private_sentinel(public, DEFAULT_PRIVATE_SEED)

    # Then the private JSONL is deterministic and disjoint from public by statement/signature.
    assert len(first) == 60
    assert jsonl_bytes(first) == jsonl_bytes(second)
    assert _signatures(first).isdisjoint(_signatures(public))
    assert _statements(first).isdisjoint(_statements(public))


def test_private_sentinel_when_built_matches_public_category_difficulty_distribution() -> None:
    # Given public and private generated-math sets.
    public = build_itemsets(DEFAULT_SEED).standard
    private = build_private_sentinel(public, DEFAULT_PRIVATE_SEED)

    # When comparing category/difficulty buckets.
    public_distribution = _category_difficulty_counts(public)
    private_distribution = _category_difficulty_counts(private)

    # Then the private sentinel has the same category/difficulty mix at half size.
    assert {key: count * 2 for key, count in private_distribution.items()} == public_distribution


def test_build_files_when_private_enabled_writes_gitignored_private_outputs(tmp_path: Path) -> None:
    # Given a temporary repo root.
    repo_root = tmp_path

    # When building public and private generated-math files.
    build_files(seed=DEFAULT_SEED, repo_root=repo_root, private_seed=DEFAULT_PRIVATE_SEED)

    # Then private outputs land only under suite/v0/private with a seed-redacted lock.
    private_dir = repo_root / "suite" / "v0" / "private"
    sentinel_path = private_dir / PRIVATE_FILE
    lock_path = private_dir / PRIVATE_LOCK_FILE
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_text = json.dumps(lock_payload, sort_keys=True)

    assert sentinel_path.exists()
    assert lock_path.exists()
    assert sentinel_path.parent == private_dir
    assert lock_payload["item_count"] == 60
    assert lock_payload["sha256"] == hashlib.sha256(sentinel_path.read_bytes()).hexdigest()
    assert "seed" not in lock_payload
    assert str(DEFAULT_PRIVATE_SEED) not in lock_text


def test_private_dir_when_checked_is_gitignored() -> None:
    # Given the configured private sentinel output path.
    private_path = "suite/v0/private/genmath_sentinel.jsonl"

    # When asking git whether the path is ignored.
    result = subprocess.run(
        ["git", "check-ignore", private_path],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the private sentinel cannot be accidentally tracked.
    assert result.returncode == 0
    assert result.stdout.strip() == private_path


def _signatures(rows: list[Mapping[str, JsonValue]]) -> set[ParamSignature]:
    return {_signature(row) for row in rows}


def _signature(row: Mapping[str, JsonValue]) -> ParamSignature:
    params = row["params"]
    assert isinstance(params, dict)
    normalized_params: list[tuple[str, str | int]] = []
    for key, value in params.items():
        assert isinstance(value, str | int)
        normalized_params.append((key, value))
    return (str(row["template"]), tuple(sorted(normalized_params)))


def _statements(rows: list[Mapping[str, JsonValue]]) -> set[str]:
    return {str(row["statement"]) for row in rows}


def _category_difficulty_counts(rows: list[Mapping[str, JsonValue]]) -> Counter[tuple[str, str]]:
    return Counter((str(row["category"]), str(row["difficulty"])) for row in rows)
