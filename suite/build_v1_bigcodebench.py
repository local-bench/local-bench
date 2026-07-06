"""Vendor + freeze the BigCodeBench-Hard task set (the opt-in code-EXECUTION axis).

BigCodeBench-Hard: 148 tasks, complex multi-library Python, unit-test scored. Apache-2.0.
We freeze the prompts + the task's own unit tests (which mock network/FS, so the tasks run
under our `--network none` sandbox). Generation happens at bench time; this only stores the
frozen items + provenance. Deterministic serialization → the jsonl's sha256 is the pin.
See docs/foundations/methodology-lock/CODING-EXEC-MODULE-SPEC.md.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

from datasets import load_dataset
from huggingface_hub import HfApi

DATASET_ID: Final = "bigcode/bigcodebench-hard"
DATASET_SPLIT: Final = "v0.1.4"  # latest corrected task revision (splits are dataset versions)
DATASET_LICENSE: Final = "Apache-2.0"
DATASET_URL: Final = "https://huggingface.co/datasets/bigcode/bigcodebench-hard"
HARNESS_REPO: Final = "https://github.com/bigcode-project/bigcodebench"
HARNESS_LICENSE: Final = "Apache-2.0"
ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "bigcodebench_hard.jsonl"
CANONICAL_MAX_TOKENS: Final = 16_384
CANONICAL_SAMPLING_PARAMS: Final[JsonObject] = {"temperature": 0}
CODE_ANSWER_RESERVE: Final = 4_096

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def main() -> int:
    revision = HfApi().dataset_info(DATASET_ID).sha
    rows = sorted(_load_rows(), key=lambda row: _required_str(row, "task_id"))
    selected = [_normalize_item(index, row, revision) for index, row in enumerate(rows, start=1)]
    _write_jsonl(OUT_PATH, selected)
    print(f"wrote {len(selected)} rows to {OUT_PATH} (revision {revision})")
    return 0


def _load_rows() -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(DATASET_ID, split=DATASET_SPLIT)
    return [_json_object(row) for row in dataset]


def _normalize_item(index: int, row: Mapping[str, JsonValue], revision: str) -> JsonObject:
    return {
        "id": f"bcbh-{index:03d}",
        "source_id": _required_str(row, "task_id"),
        "source_dataset": DATASET_ID,
        "source_split": DATASET_SPLIT,
        "source_revision": revision,
        "source_url": DATASET_URL,
        "license": DATASET_LICENSE,
        "harness_repo": HARNESS_REPO,
        "harness_license": HARNESS_LICENSE,
        "lane": "exec",
        "max_tokens": CANONICAL_MAX_TOKENS,
        "sampling_params": dict(CANONICAL_SAMPLING_PARAMS),
        "answer_reserve": CODE_ANSWER_RESERVE,
        "entry_point": _required_str(row, "entry_point"),
        "instruct_prompt": _required_str(row, "instruct_prompt"),
        "complete_prompt": _required_str(row, "complete_prompt"),
        "code_prompt": _required_str(row, "code_prompt"),
        "test": _required_str(row, "test"),
        "libs": _required_str(row, "libs"),
    }


def _json_object(row: Mapping[str, object]) -> JsonObject:
    result: JsonObject = {}
    for key, value in row.items():
        result[key] = value if isinstance(value, str | int | float | bool) or value is None else str(value)
    return result


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
