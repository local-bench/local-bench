# /// script
# dependencies = ["datasets>=2.20"]
# ///

# --- How to run ---
# cli/.venv/Scripts/python.exe suite/build_v1_mmlu_pro.py

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

_BUILD_DEP_MESSAGE: Final = (
    "Missing build dependency. Run "
    "`cli/.venv/Scripts/python -m pip install -e cli[build]` from the repo root."
)


def _require_build_deps() -> None:
    # Lazy: HF deps are build-only (not in cli[dev]); importing this module — e.g. for the pure
    # helper tests — must not require them. Only the actual build path calls this.
    try:
        import datasets  # noqa: F401
        import huggingface_hub  # noqa: F401
    except ModuleNotFoundError as error:
        raise SystemExit(_BUILD_DEP_MESSAGE) from error


ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "mmlu_pro.jsonl"

DATASET_ID: Final = "TIGER-Lab/MMLU-Pro"
DATASET_REVISION: Final = "b189ec765aa7ed75c8acfea42df31fdae71f97be"
DATASET_SPLIT: Final = "test"
EXPECTED_LICENSE: Final = "mit"
EXPECTED_TOTAL_ROWS: Final = 12_032
EXPECTED_CATEGORY_COUNT: Final = 14
TARGET_COUNT: Final = 400
SAMPLE_SEED: Final = "local-bench-suite-v1-mmlu-pro-20260616"
LETTERS: Final = "ABCDEFGHIJ"

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Candidate:
    question_id: int
    question: str
    options: tuple[str, ...]
    answer: str
    category: str


class BuildError(RuntimeError):
    pass


def main() -> int:
    _require_license()
    rows = _load_rows()
    candidates, drops = _eligible_candidates(rows)
    categories = Counter(candidate.category for candidate in candidates)
    if len(categories) != EXPECTED_CATEGORY_COUNT:
        raise BuildError(f"Expected {EXPECTED_CATEGORY_COUNT} categories, found {len(categories)}.")
    selected = _stratified_sample(candidates)
    items = [_to_item(candidate, index) for index, candidate in enumerate(selected, start=1)]
    _write_jsonl(OUT_PATH, items)
    _print_datasheet(rows, candidates, selected, drops)
    return 0


def _require_license() -> None:
    _require_build_deps()
    from huggingface_hub import HfApi

    info = HfApi().dataset_info(DATASET_ID, revision=DATASET_REVISION)
    card_data = info.cardData
    license_value = getattr(card_data, "license", None)
    if info.sha != DATASET_REVISION:
        raise BuildError(f"{DATASET_ID} resolved to {info.sha!r}, expected {DATASET_REVISION!r}.")
    if license_value != EXPECTED_LICENSE:
        raise BuildError(
            f"{DATASET_ID}@{DATASET_REVISION} dataset license is {license_value!r}, "
            f"expected {EXPECTED_LICENSE!r}."
        )


def _load_rows() -> list[Mapping[str, JsonValue]]:
    _require_build_deps()
    from datasets import Dataset, load_dataset

    dataset = load_dataset(DATASET_ID, split=DATASET_SPLIT, revision=DATASET_REVISION)
    if not isinstance(dataset, Dataset):
        raise BuildError(f"Expected Dataset for {DATASET_ID}/{DATASET_SPLIT}.")
    rows = [dict(row) for row in dataset]
    if len(rows) != EXPECTED_TOTAL_ROWS:
        raise BuildError(f"Expected {EXPECTED_TOTAL_ROWS} rows, found {len(rows)}.")
    return rows


def _eligible_candidates(
    rows: list[Mapping[str, JsonValue]],
) -> tuple[list[Candidate], Counter[str]]:
    drops: Counter[str] = Counter()
    candidates: list[Candidate] = []
    for source_index, row in enumerate(rows, start=1):
        candidate, drop_reason = _candidate_from_row(row)
        if drop_reason is not None:
            drops[drop_reason] += 1
            continue
        if candidate is None:
            raise BuildError(f"Row {source_index} returned no candidate and no drop reason.")
        candidates.append(candidate)
    return candidates, drops


def _candidate_from_row(
    row: Mapping[str, JsonValue],
) -> tuple[Candidate | None, str | None]:
    question_id = _int(row, "question_id")
    question = _stripped(row, "question")
    answer_letter = _stripped(row, "answer")
    answer_index = _int(row, "answer_index")
    category = _stripped(row, "category")
    if question_id is None or None in (question, answer_letter, answer_index, category):
        return None, "missing_required_field"

    options_value = row.get("options")
    if not isinstance(options_value, list):
        return None, "malformed_options"
    options: list[str] = []
    for option in options_value:
        if not isinstance(option, str) or not option.strip():
            return None, "malformed_options"
        options.append(option.strip())

    keyed_index = _keyed_index(answer_letter, answer_index, len(options))
    if keyed_index is None:
        return None, "missing_or_ambiguous_gold"
    keyed_text = options[keyed_index]
    if _is_na(keyed_text):
        return None, "gold_is_na"

    real_options = tuple(option for option in options if not _is_na(option))
    if len(real_options) < 2 or len(real_options) > len(LETTERS):
        return None, "unscorable_option_count"
    if len(real_options) != len(set(real_options)):
        return None, "ambiguous_duplicate_options"

    gold_matches = [index for index, option in enumerate(real_options) if option == keyed_text]
    if len(gold_matches) != 1:
        return None, "missing_or_ambiguous_gold"
    remapped_answer = LETTERS[gold_matches[0]]
    if real_options[gold_matches[0]] != keyed_text:
        return None, "missing_or_ambiguous_gold"

    return (
        Candidate(
            question_id=question_id,
            question=question,
            options=real_options,
            answer=remapped_answer,
            category=category,
        ),
        None,
    )


def _stratified_sample(
    candidates: list[Candidate],
    *,
    target_count: int = TARGET_COUNT,
    sample_seed: str = SAMPLE_SEED,
) -> list[Candidate]:
    category_counts: Counter[str] = Counter(row.category for row in candidates)
    allocations = _allocate_categories(category_counts, target_count=target_count)
    by_category: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_category.setdefault(candidate.category, []).append(candidate)

    selected: list[Candidate] = []
    for category, count in sorted(allocations.items()):
        category_rows = sorted(
            by_category[category],
            key=lambda row: _stable_digest("sample", row.question_id, sample_seed),
        )
        selected.extend(category_rows[:count])
    if len(selected) != target_count:
        raise BuildError(f"Expected {target_count} selected rows, found {len(selected)}.")
    return sorted(selected, key=lambda row: _stable_digest("order", row.question_id, sample_seed))


def _allocate_categories(
    category_counts: Counter[str],
    *,
    target_count: int,
) -> dict[str, int]:
    if len(category_counts) > target_count:
        raise BuildError(f"{len(category_counts)} categories cannot fit target count {target_count}.")
    allocations = {category: 1 for category in category_counts}
    remaining = target_count - len(category_counts)
    capacities = {category: count - 1 for category, count in category_counts.items()}
    total_capacity = sum(capacities.values())
    if remaining > total_capacity:
        raise BuildError(f"Target count {target_count} exceeds eligible row count.")

    remainders: list[tuple[float, str]] = []
    for category, capacity in capacities.items():
        exact = capacity / total_capacity * remaining if total_capacity else 0.0
        extra = min(capacity, int(exact))
        allocations[category] += extra
        remainders.append((exact - extra, category))
    remaining = target_count - sum(allocations.values())
    ordered = sorted(remainders, key=lambda entry: (-entry[0], entry[1]))
    while remaining:
        made_progress = False
        for _remainder, category in ordered:
            if allocations[category] >= category_counts[category]:
                continue
            allocations[category] += 1
            remaining -= 1
            made_progress = True
            if remaining == 0:
                break
        if not made_progress:
            raise BuildError("Could not allocate remaining MMLU-Pro categories.")
    return allocations


def _chance_baseline(candidates: Sequence[Candidate]) -> float:
    if not candidates:
        raise BuildError("Cannot compute chance baseline for an empty item set.")
    return sum(1 / len(candidate.options) for candidate in candidates) / len(candidates)


def _to_item(candidate: Candidate, index: int) -> JsonObject:
    return {
        "id": f"mmlu-pro-{index:03d}",
        "question": candidate.question,
        "options": list(candidate.options),
        "answer": candidate.answer,
        "category": candidate.category,
    }


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _print_datasheet(
    rows: list[Mapping[str, JsonValue]],
    candidates: list[Candidate],
    selected: list[Candidate],
    drops: Counter[str],
) -> None:
    print(f"dataset_id={DATASET_ID}")
    print(f"revision={DATASET_REVISION}")
    print(f"license={EXPECTED_LICENSE!r}")
    print(f"split={DATASET_SPLIT}")
    print(f"total_rows={len(rows)} eligible_after_filters={len(candidates)} emitted={len(selected)}")
    print(f"drops={dict(sorted(drops.items()))}")
    _print_counter("category_allocation", Counter(row.category for row in selected))
    _print_counter("options_count_distribution", Counter(str(len(row.options)) for row in selected))
    print(f"chance_correction_baseline={_chance_baseline(selected):.12f}")


def _print_counter(title: str, counts: Counter[str]) -> None:
    print(title)
    for key, count in sorted(counts.items()):
        print(f"  {key}: {count}")


def _keyed_index(answer_letter: str, answer_index: int, option_count: int) -> int | None:
    letter = answer_letter.upper()
    if len(letter) != 1 or letter not in LETTERS:
        return None
    keyed_index = LETTERS.index(letter)
    if answer_index != keyed_index or keyed_index >= option_count:
        return None
    return keyed_index


def _is_na(option: str) -> bool:
    return option.strip().upper() == "N/A"


def _stripped(row: Mapping[str, JsonValue], key: str) -> str | None:
    value = row.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _int(row: Mapping[str, JsonValue], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _stable_digest(namespace: str, question_id: int, sample_seed: str) -> str:
    return hashlib.sha256(f"{sample_seed}:{namespace}:{question_id}".encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
