from __future__ import annotations

from pathlib import Path
from typing import Final

if __package__:
    from suite import build_v1_bfcl_multi_turn as v1_builder
else:
    import build_v1_bfcl_multi_turn as v1_builder

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_DIR: Final = ROOT / "suite" / "v2"
BENCH_BY_CATEGORY: Final = {
    "multi_turn_base": "bfcl_multi_turn_base",
    "multi_turn_long_context": "bfcl_multi_turn_long_context",
}

JsonValue = v1_builder.JsonValue
JsonObject = v1_builder.JsonObject
BuildError = v1_builder.BuildError


def main() -> int:
    rows = v1_builder._load_candidates()
    selected = v1_builder._stratified_sample(
        rows,
        per_category=v1_builder.TARGET_PER_CATEGORY,
        sample_seed=v1_builder.SAMPLE_SEED,
    )
    partitions = _partition_selected(selected)
    for category, bench in BENCH_BY_CATEGORY.items():
        path = OUT_DIR / f"{bench}.jsonl"
        items = partitions[category]
        v1_builder._write_jsonl(path, items)
        print(f"{bench}: {len(items)} rows sha256={v1_builder._sha256(path)}")
    return 0


def _partition_selected(
    rows: list[JsonObject],
) -> dict[str, list[JsonObject]]:
    partitions = {category: [] for category in BENCH_BY_CATEGORY}
    for row in rows:
        category = v1_builder._required_str(row, "category")
        if category not in partitions:
            raise BuildError(f"Unexpected BFCL multi-turn category: {category}")
        partitions[category].append(row)
    for category, items in partitions.items():
        if len(items) != v1_builder.TARGET_PER_CATEGORY:
            raise BuildError(
                f"Expected {v1_builder.TARGET_PER_CATEGORY} {category} rows, found {len(items)}"
            )
    return partitions


if __name__ == "__main__":
    raise SystemExit(main())
