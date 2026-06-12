# /// script
# dependencies = ["datasets>=2.20"]
# ///
# ----- How to run -----
# From the repo root:
#   cli/.venv/Scripts/python suite/build_itemsets.py

"""Build frozen suite-v0 item sets from upstream Hugging Face datasets."""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

SEED = 20260612
ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
OUT_DIR = ROOT / "suite" / "v0"
MMLU_REPO = "TIGER-Lab/MMLU-Pro"
IFEVAL_REPO = "google/IFEval"

os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_DIR / "huggingface" / "hub"))
os.environ.setdefault("HF_DATASETS_CACHE", str(CACHE_DIR / "datasets"))

try:
    from datasets import Dataset, load_dataset
    from huggingface_hub import HfApi
except ModuleNotFoundError as error:
    message = (
        "Missing build dependency. Run "
        "`cli/.venv/Scripts/python -m pip install -e cli[build]` from the repo root."
    )
    raise SystemExit(message) from error

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    previous_lock = _read_previous_lock()
    mmlu_revision = _dataset_revision(MMLU_REPO)
    ifeval_revision = _dataset_revision(IFEVAL_REPO)

    mmlu_rows = _load_rows(MMLU_REPO, "test", mmlu_revision)
    ifeval_rows = _load_rows(IFEVAL_REPO, "train", ifeval_revision)

    mmlu_standard = _sample_mmlu(mmlu_rows, per_category=20, source_rows=None)
    ifeval_standard = _sort_ifeval(
        random.Random(SEED).sample([_normalize_ifeval(row) for row in ifeval_rows], 250)
    )
    outputs = {
        "mmlu_pro_standard.jsonl": _sort_mmlu(mmlu_standard),
        "mmlu_pro_quick.jsonl": _sort_mmlu(
            _sample_mmlu(mmlu_standard, per_category=8, source_rows=mmlu_standard)
        ),
        "ifeval_standard.jsonl": ifeval_standard,
        "ifeval_quick.jsonl": _sort_ifeval(random.Random(SEED).sample(ifeval_standard, 100)),
    }
    for filename, rows in outputs.items():
        _write_jsonl(OUT_DIR / filename, rows)

    lock = _build_lock(previous_lock, mmlu_revision, ifeval_revision)
    _write_json(OUT_DIR / "itemsets.lock.json", lock)
    _write_json(OUT_DIR / "suite.json", _suite_spec(lock))
    return 0


def _dataset_revision(repo_id: str) -> str | None:
    info = HfApi().dataset_info(repo_id)
    sha = getattr(info, "sha", None)
    if isinstance(sha, str) and sha:
        return sha
    return None


def _load_rows(repo_id: str, split: str, revision: str | None) -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(
        repo_id,
        split=split,
        revision=revision,
        cache_dir=str(CACHE_DIR),
    )
    if not isinstance(dataset, Dataset):
        raise TypeError(f"Expected Dataset for {repo_id}/{split}.")
    return [dict(row) for row in dataset]


def _sample_mmlu(
    rows: list[Mapping[str, JsonValue]],
    *,
    per_category: int,
    source_rows: list[JsonObject] | None,
) -> list[JsonObject]:
    grouped: dict[str, list[Mapping[str, JsonValue]]] = defaultdict(list)
    source = source_rows if source_rows is not None else rows
    for row in source:
        category = _required_str(row, "category")
        grouped[category].append(row)

    categories = sorted(grouped)
    if len(categories) != 14:
        raise ValueError(f"Expected 14 MMLU-Pro categories, found {len(categories)}.")

    rng = random.Random(SEED)
    sampled: list[JsonObject] = []
    for category in categories:
        candidates = grouped[category]
        if len(candidates) < per_category:
            raise ValueError(f"Category {category} has {len(candidates)} rows.")
        sampled.extend(_normalize_mmlu(row) for row in rng.sample(candidates, per_category))
    return sampled


def _normalize_mmlu(row: Mapping[str, JsonValue]) -> JsonObject:
    answer_index = _required_int(row, "answer_index")
    answer = _required_str(row, "answer")
    if len(answer) != 1 or not answer.isalpha():
        answer = chr(ord("A") + answer_index)
    return {
        "question_id": row["question_id"],
        "category": _required_str(row, "category"),
        "question": _required_str(row, "question"),
        "options": _required_str_list(row, "options"),
        "answer": answer.upper(),
        "answer_index": answer_index,
    }


def _normalize_ifeval(row: Mapping[str, JsonValue]) -> JsonObject:
    return {
        "key": _required_int(row, "key"),
        "prompt": _required_str(row, "prompt"),
        "instruction_id_list": _required_str_list(row, "instruction_id_list"),
        "kwargs": _required_object_list(row, "kwargs"),
    }


def _sort_mmlu(rows: Iterable[JsonObject]) -> list[JsonObject]:
    return sorted(rows, key=lambda row: _id_sort_key(row["question_id"]))


def _sort_ifeval(rows: Iterable[JsonObject]) -> list[JsonObject]:
    return sorted(rows, key=lambda row: _id_sort_key(row["key"]))


def _write_jsonl(path: Path, rows: list[JsonObject]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _build_lock(
    previous_lock: Mapping[str, JsonValue],
    mmlu_revision: str | None,
    ifeval_revision: str | None,
) -> JsonObject:
    files = {
        "mmlu_pro_standard.jsonl": (MMLU_REPO, mmlu_revision),
        "mmlu_pro_quick.jsonl": (MMLU_REPO, mmlu_revision),
        "ifeval_standard.jsonl": (IFEVAL_REPO, ifeval_revision),
        "ifeval_quick.jsonl": (IFEVAL_REPO, ifeval_revision),
    }
    return {
        "files": {
            filename: _lock_entry(filename, source, revision, previous_lock)
            for filename, (source, revision) in files.items()
        }
    }


def _lock_entry(
    filename: str,
    source: str,
    revision: str | None,
    previous_lock: Mapping[str, JsonValue],
) -> JsonObject:
    path = OUT_DIR / filename
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    previous = _previous_file_entry(previous_lock, filename)
    timestamp = _timestamp_for(previous, sha, revision)
    return {
        "item_count": path.read_bytes().count(b"\n"),
        "sha256": sha,
        "source_dataset": source,
        "source_revision": revision,
        "seed": SEED,
        "build_timestamp": timestamp,
    }


def _suite_spec(lock: Mapping[str, JsonValue]) -> JsonObject:
    files = _required_mapping(lock, "files")
    return {
        "version": "suite-v0",
        "benches": {
            "mmlu_pro": {
                "itemsets": {
                    "standard": _itemset_spec(files, "mmlu_pro_standard.jsonl"),
                    "quick": _itemset_spec(files, "mmlu_pro_quick.jsonl"),
                },
                "template": "templates/mcq_cot.txt",
                "decoding": {"temperature": 0, "max_tokens": 2048},
                "chance_correction_baseline": 0.10,
                "lane_caps": {},
            },
            "ifeval": {
                "itemsets": {
                    "standard": _itemset_spec(files, "ifeval_standard.jsonl"),
                    "quick": _itemset_spec(files, "ifeval_quick.jsonl"),
                },
                "template": "templates/ifeval.txt",
                "decoding": {"temperature": 0, "max_tokens": 1280},
                "chance_correction_baseline": 0.0,
                "lane_caps": {},
            },
        },
    }


def _itemset_spec(files: Mapping[str, JsonValue], filename: str) -> JsonObject:
    entry = _required_mapping(files, filename)
    return {
        "file": filename,
        "sha256": _required_str(entry, "sha256"),
        "item_count": _required_int(entry, "item_count"),
    }


def _read_previous_lock() -> Mapping[str, JsonValue]:
    path = OUT_DIR / "itemsets.lock.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data
    return {}


def _previous_file_entry(lock: Mapping[str, JsonValue], filename: str) -> Mapping[str, JsonValue]:
    files = lock.get("files")
    if not isinstance(files, dict):
        return {}
    entry = files.get(filename)
    if isinstance(entry, dict):
        return entry
    return {}


def _timestamp_for(previous: Mapping[str, JsonValue], sha: str, revision: str | None) -> str:
    if previous.get("sha256") == sha and previous.get("source_revision") == revision:
        timestamp = previous.get("build_timestamp")
        if isinstance(timestamp, str):
            return timestamp
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_mapping(row: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    value = row[key]
    if not isinstance(value, dict): raise TypeError(f"{key} must be an object.")
    return value


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str): raise TypeError(f"{key} must be a string.")
    return value


def _required_int(row: Mapping[str, JsonValue], key: str) -> int:
    value = row[key]
    if not isinstance(value, int) or isinstance(value, bool): raise TypeError(f"{key} must be an integer.")
    return value


def _required_str_list(row: Mapping[str, JsonValue], key: str) -> list[str]:
    value = row[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value): raise TypeError(f"{key} must be a list of strings.")
    return value


def _required_object_list(row: Mapping[str, JsonValue], key: str) -> list[JsonObject]:
    value = row[key]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value): raise TypeError(f"{key} must be a list of objects.")
    return value


def _id_sort_key(value: JsonValue) -> tuple[int, int | str]:
    if isinstance(value, int) and not isinstance(value, bool):
        return (0, value)
    if isinstance(value, str) and value.isdecimal():
        return (0, int(value))
    return (1, str(value))


if __name__ == "__main__":
    raise SystemExit(main())
