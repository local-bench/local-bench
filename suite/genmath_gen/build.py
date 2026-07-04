# /// script
# dependencies = []
# ///
# ----- How to run -----
# From the repo root:
#   cli/.venv/Scripts/python suite/genmath_gen/build.py --seed 20260612

"""Build generated-math suite-v0 item sets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genmath_gen.itemsets import (
    DEFAULT_PRIVATE_SEED as ITEMSETS_DEFAULT_PRIVATE_SEED,
    PRIVATE_DIR_NAME,
    PRIVATE_FILE,
    PRIVATE_LOCK_FILE,
    PRIVATE_SEED_ENV,
    JsonObject,
    build_itemsets,
    build_private_sentinel,
    jsonl_bytes,
)

DEFAULT_SEED = 20260612
DEFAULT_PRIVATE_SEED = ITEMSETS_DEFAULT_PRIVATE_SEED
ROOT = Path(__file__).resolve().parents[2]
STANDARD_FILE = "genmath_standard.jsonl"
QUICK_FILE = "genmath_quick.jsonl"
ENV_PRIVATE_SEED_SOURCE = f"{PRIVATE_SEED_ENV} environment variable was set for this local build."
EXPLICIT_PRIVATE_SEED_SOURCE = "private seed was supplied directly to build_files for this build."


@dataclass(frozen=True, slots=True)
class PrivateSeedConfig:
    seed: int
    source: str


@dataclass(frozen=True, slots=True)
class PrivateSeedConfigError(ValueError):
    env_var: str
    raw_value: str
    reason: str

    def __str__(self) -> str:
        return f"{self.env_var} {self.reason}: {self.raw_value!r}"


def build_files(seed: int = DEFAULT_SEED, repo_root: Path | None = None, private_seed: int | None = None) -> None:
    root = repo_root or ROOT
    suite_dir = root / "suite" / "v0"
    itemsets = build_itemsets(seed)

    suite_dir.mkdir(parents=True, exist_ok=True)

    _write_bytes(suite_dir / STANDARD_FILE, jsonl_bytes(itemsets.standard))
    _write_bytes(suite_dir / QUICK_FILE, jsonl_bytes(itemsets.quick))

    standard_entry = _lock_entry(suite_dir / STANDARD_FILE, len(itemsets.standard), seed)
    quick_entry = _lock_entry(suite_dir / QUICK_FILE, len(itemsets.quick), seed)
    _write_json(suite_dir / "itemsets.lock.json", _updated_lock(suite_dir, standard_entry, quick_entry))

    private_seed_config = _private_seed_config(public_seed=seed, private_seed=private_seed)
    if private_seed_config is None:
        print(f"private sentinel skipped (no seed; set {PRIVATE_SEED_ENV} or pass --private-seed)")
        return
    private_items = build_private_sentinel(itemsets.standard, private_seed_config.seed)
    _write_private_files(suite_dir, private_items, private_seed_config.source)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--private-seed", type=int, default=None)
    args = parser.parse_args(argv)
    build_files(seed=args.seed, private_seed=args.private_seed)
    return 0


def _write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _write_private_files(suite_dir: Path, private_items: list[JsonObject], seed_source: str) -> None:
    private_dir = suite_dir / PRIVATE_DIR_NAME
    private_dir.mkdir(parents=True, exist_ok=True)
    sentinel_path = private_dir / PRIVATE_FILE
    _write_bytes(sentinel_path, jsonl_bytes(private_items))
    _write_json(
        private_dir / PRIVATE_LOCK_FILE,
        {
            "item_count": len(private_items),
            "seed_source": seed_source,
            "sha256": hashlib.sha256(sentinel_path.read_bytes()).hexdigest(),
        },
    )


def _private_seed_config(public_seed: int, private_seed: int | None) -> PrivateSeedConfig | None:
    if private_seed is not None:
        return _checked_private_seed(public_seed, private_seed, EXPLICIT_PRIVATE_SEED_SOURCE)

    raw_seed = os.environ.get(PRIVATE_SEED_ENV)
    if raw_seed is None:
        return None

    try:
        parsed_seed = int(raw_seed)
    except ValueError as exc:
        raise PrivateSeedConfigError(
            env_var=PRIVATE_SEED_ENV,
            raw_value=raw_seed,
            reason="must be an integer",
        ) from exc
    return _checked_private_seed(public_seed, parsed_seed, ENV_PRIVATE_SEED_SOURCE)


def _checked_private_seed(public_seed: int, private_seed: int, source: str) -> PrivateSeedConfig:
    if private_seed == public_seed:
        raise PrivateSeedConfigError(
            env_var=PRIVATE_SEED_ENV,
            raw_value="<redacted>",
            reason="must differ from the public seed",
        )
    return PrivateSeedConfig(seed=private_seed, source=source)


def _lock_entry(path: Path, count: int, seed: int) -> JsonObject:
    return {
        "item_count": count,
        "seed": seed,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _updated_lock(suite_dir: Path, standard: JsonObject, quick: JsonObject) -> JsonObject:
    lock = _read_json(suite_dir / "itemsets.lock.json")
    files = lock.get("files")
    next_files = dict(files) if isinstance(files, dict) else {}
    next_files[STANDARD_FILE] = standard
    next_files[QUICK_FILE] = quick
    return {"files": next_files}


def _read_json(path: Path) -> JsonObject:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    raise SystemExit(main())
