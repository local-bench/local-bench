from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Final, TypeAlias

SEED: Final = 20260616
ITEMS_PER_CELL: Final = 6
HAYSTACK_TOKENS: Final = 32_000
DEPTHS: Final = (0, 25, 50, 75, 100)
TASK_TYPES: Final = ("niah_single", "niah_multikey")
FILLER_CORPUS_ID: Final = "synthetic-ruler-local-v1"
ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "ruler_32k.jsonl"

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def main() -> int:
    rows = _rows()
    _write_jsonl(OUT_PATH, rows)
    print(f"wrote {len(rows)} rows to {OUT_PATH}")
    return 0


def _rows() -> list[JsonObject]:
    rows: list[JsonObject] = []
    for depth in DEPTHS:
        for task_type in TASK_TYPES:
            for cell_index in range(ITEMS_PER_CELL):
                item_index = len(rows) + 1
                seed = SEED + item_index * 10_007
                rows.append(_row(item_index, seed, task_type, depth, cell_index))
    return rows


def _row(
    item_index: int,
    seed: int,
    task_type: str,
    depth: int,
    cell_index: int,
) -> JsonObject:
    rng = random.Random(seed)
    base: JsonObject = {
        "id": f"ruler32k-{item_index:03d}",
        "task_type": task_type,
        "seed": seed,
        "haystack_token_count": HAYSTACK_TOKENS,
        "target_depth_percent": depth,
        "filler_corpus_id": FILLER_CORPUS_ID,
        "category": "long_context",
        "difficulty": "32k",
        "template": task_type,
        "source_dataset": "NVIDIA/RULER",
        "source_url": "https://github.com/NVIDIA/RULER",
        "source_revision": "algorithmic-reimplementation",
        "source_paper": "https://arxiv.org/abs/2404.06654",
        "license": "Apache-2.0",
        "generator_attribution": "Reimplemented from NVIDIA/RULER NIAH task pattern",
        "license_note": (
            "Stores compact seed parameters only; no upstream RULER code, prompts, "
            "or haystack data are vendored."
        ),
    }
    match task_type:
        case "niah_single":
            key = _key(rng, item_index, "single")
            value = _value(rng)
            return {**base, "needle_key": key, "needle_value": value}
        case "niah_multikey":
            keys = [_key(rng, item_index, f"multi{key_index}") for key_index in range(4)]
            values = [_value(rng) for _ in keys]
            target_offsets = (cell_index % 4, (cell_index + 2) % 4)
            target_keys = [keys[offset] for offset in target_offsets]
            answer_values = [values[offset] for offset in target_offsets]
            return {
                **base,
                "needle_keys": keys,
                "needle_values": values,
                "target_keys": target_keys,
                "answer_values": answer_values,
                "distractor_count": 2,
            }
        case _:
            raise TypeError(f"unsupported task_type: {task_type}")


def _key(rng: random.Random, item_index: int, suffix: str) -> str:
    left = rng.choice(("amber", "brisk", "crimson", "distant", "emerald", "frozen"))
    right = rng.choice(("anchor", "cipher", "glade", "harbor", "signal", "vertex"))
    return f"{left}-{right}-{item_index:03d}-{suffix}"


def _value(rng: random.Random) -> str:
    return f"RULER-{rng.randrange(1_000_000, 10_000_000)}"


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
