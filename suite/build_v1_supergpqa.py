# /// script
# dependencies = ["datasets>=2.20"]
# ///

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

try:
    from datasets import Dataset, load_dataset
    from huggingface_hub import HfApi
except ModuleNotFoundError as error:
    message = (
        "Missing build dependency. Run "
        "`cli/.venv/Scripts/python -m pip install -e cli[build]` from the repo root."
    )
    raise SystemExit(message) from error

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "supergpqa.jsonl"

DATASET_ID: Final = "m-a-p/SuperGPQA"
DATASET_REVISION: Final = "4430d4458112c7d4497fdcf94d7cc223313d6acf"
DATASET_SPLIT: Final = "train"
EXPECTED_LICENSE: Final = "odc-by"
EXPECTED_TOTAL_ROWS: Final = 26_529
TARGET_COUNT: Final = 400
SAMPLE_SEED: Final = "local-bench-suite-v1-supergpqa-20260614"
LETTERS: Final = "ABCDEFGHIJ"
PROVENANCE_FIELD_MARKERS: Final = ("source", "provenance", "origin", "upstream", "dataset")
DENIED_PROVENANCE_TERMS: Final = (
    "cc by-nc",
    "cc-by-nc",
    "gated",
    "non commercial",
    "non-commercial",
    "non-redistributable",
    "nonredistributable",
    "not for redistribution",
    "no redistribution",
    "proprietary",
    "research only",
    "research-only",
)
DIFFICULTY_ORDER: Final = {"easy": 0, "middle": 1, "hard": 2}

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
Stratum: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Candidate:
    uuid: str
    question: str
    options: tuple[str, ...]
    answer: str
    discipline: str
    difficulty: str


class BuildError(RuntimeError):
    pass


def main() -> int:
    _require_license()
    rows = _load_rows()
    candidates, drops, provenance_fields = _eligible_candidates(rows)
    selected = _stratified_sample(candidates)
    items = [_to_item(candidate, index) for index, candidate in enumerate(selected, start=1)]
    _write_jsonl(OUT_PATH, items)
    _print_datasheet(rows, candidates, selected, drops, provenance_fields)
    return 0


def _require_license() -> None:
    info = HfApi().dataset_info(DATASET_ID, revision=DATASET_REVISION)
    card_data = info.cardData
    license_value = getattr(card_data, "license", None)
    if info.sha != DATASET_REVISION:
        raise BuildError(f"{DATASET_ID} resolved to {info.sha!r}, expected {DATASET_REVISION!r}.")
    if license_value != EXPECTED_LICENSE:
        raise BuildError(
            f"{DATASET_ID}@{DATASET_REVISION} license is {license_value!r}, "
            f"expected {EXPECTED_LICENSE!r}."
        )


def _load_rows() -> list[Mapping[str, JsonValue]]:
    dataset = load_dataset(DATASET_ID, split=DATASET_SPLIT, revision=DATASET_REVISION)
    if not isinstance(dataset, Dataset):
        raise BuildError(f"Expected Dataset for {DATASET_ID}/{DATASET_SPLIT}.")
    rows = [dict(row) for row in dataset]
    if len(rows) != EXPECTED_TOTAL_ROWS:
        raise BuildError(f"Expected {EXPECTED_TOTAL_ROWS} rows, found {len(rows)}.")
    return rows


def _eligible_candidates(
    rows: list[Mapping[str, JsonValue]],
) -> tuple[list[Candidate], Counter[str], tuple[str, ...]]:
    drops: Counter[str] = Counter()
    provenance_fields: set[str] = set()
    candidates: list[Candidate] = []
    for source_index, row in enumerate(rows, start=1):
        row_provenance_fields = _provenance_fields(row)
        provenance_fields.update(row_provenance_fields)
        if _is_denied_provenance(row, row_provenance_fields):
            drops["identifiable_denied_provenance"] += 1
            continue
        candidate, drop_reason = _candidate_from_row(row)
        if drop_reason is not None:
            drops[drop_reason] += 1
            continue
        if candidate is None:
            raise BuildError(f"Row {source_index} returned no candidate and no drop reason.")
        candidates.append(candidate)
    return candidates, drops, tuple(sorted(provenance_fields))


def _candidate_from_row(
    row: Mapping[str, JsonValue],
) -> tuple[Candidate | None, str | None]:
    uuid = _stripped(row, "uuid")
    question = _stripped(row, "question")
    answer_text = _stripped(row, "answer")
    answer_letter = _stripped(row, "answer_letter")
    discipline = _stripped(row, "discipline")
    difficulty = _stripped(row, "difficulty")
    if None in (uuid, question, answer_text, answer_letter, discipline, difficulty):
        return None, "missing_required_field"

    options_value = row.get("options")
    if not isinstance(options_value, list):
        return None, "malformed_options"
    options: list[str] = []
    for option in options_value:
        if not isinstance(option, str) or not option.strip():
            return None, "malformed_options"
        options.append(option.strip())
    if len(options) < 2 or len(options) > len(LETTERS):
        return None, "unscorable_option_count"
    if len(options) != len(set(options)):
        return None, "ambiguous_duplicate_options"

    letter = answer_letter.upper()
    if len(letter) != 1 or letter not in LETTERS[: len(options)]:
        return None, "missing_or_ambiguous_gold"
    gold_index = LETTERS.index(letter)
    if options[gold_index] != answer_text.strip():
        return None, "missing_or_ambiguous_gold"

    return (
        Candidate(
            uuid=uuid,
            question=question,
            options=tuple(options),
            answer=letter,
            discipline=discipline,
            difficulty=difficulty,
        ),
        None,
    )


def _stratified_sample(candidates: list[Candidate]) -> list[Candidate]:
    strata_counts: Counter[Stratum] = Counter((row.discipline, row.difficulty) for row in candidates)
    allocations = _allocate_strata(strata_counts)
    by_stratum: dict[Stratum, list[Candidate]] = {}
    for candidate in candidates:
        by_stratum.setdefault((candidate.discipline, candidate.difficulty), []).append(candidate)

    selected: list[Candidate] = []
    for stratum, count in sorted(allocations.items(), key=lambda entry: _stratum_sort_key(entry[0])):
        stratum_rows = sorted(by_stratum[stratum], key=lambda row: _stable_digest("sample", row.uuid))
        selected.extend(stratum_rows[:count])
    if len(selected) != TARGET_COUNT:
        raise BuildError(f"Expected {TARGET_COUNT} selected rows, found {len(selected)}.")
    return sorted(selected, key=lambda row: _stable_digest("order", row.uuid))


def _allocate_strata(strata_counts: Counter[Stratum]) -> dict[Stratum, int]:
    if len(strata_counts) > TARGET_COUNT:
        raise BuildError(f"{len(strata_counts)} strata cannot fit target count {TARGET_COUNT}.")
    allocations = {stratum: 1 for stratum in strata_counts}
    remaining = TARGET_COUNT - len(strata_counts)
    capacities = {stratum: count - 1 for stratum, count in strata_counts.items()}
    total_capacity = sum(capacities.values())
    if remaining > total_capacity:
        raise BuildError(f"Target count {TARGET_COUNT} exceeds eligible row count.")

    remainders: list[tuple[float, Stratum]] = []
    for stratum, capacity in capacities.items():
        exact = capacity / total_capacity * remaining if total_capacity else 0.0
        extra = min(capacity, int(exact))
        allocations[stratum] += extra
        remainders.append((exact - extra, stratum))
    remaining = TARGET_COUNT - sum(allocations.values())
    ordered = sorted(remainders, key=lambda entry: (-entry[0], _stratum_sort_key(entry[1])))
    while remaining:
        made_progress = False
        for _remainder, stratum in ordered:
            if allocations[stratum] >= strata_counts[stratum]:
                continue
            allocations[stratum] += 1
            remaining -= 1
            made_progress = True
            if remaining == 0:
                break
        if not made_progress:
            raise BuildError("Could not allocate remaining SuperGPQA strata.")
    return allocations


def _to_item(candidate: Candidate, index: int) -> JsonObject:
    return {
        "id": f"supergpqa-{index:03d}",
        "question": candidate.question,
        "options": list(candidate.options),
        "answer": candidate.answer,
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
    provenance_fields: tuple[str, ...],
) -> None:
    print(f"dataset_id={DATASET_ID}")
    print(f"revision={DATASET_REVISION}")
    print(f"license={EXPECTED_LICENSE!r}")
    print(f"total_rows={len(rows)} eligible_after_filters={len(candidates)} emitted={len(selected)}")
    print(f"provenance_fields={list(provenance_fields)}")
    print(f"drops={dict(sorted(drops.items()))}")
    _print_counter("discipline_distribution", Counter(row.discipline for row in selected))
    _print_counter("difficulty_distribution", Counter(row.difficulty for row in selected))
    _print_counter(
        "discipline_difficulty_distribution",
        Counter(f"{row.discipline}/{row.difficulty}" for row in selected),
    )
    _print_counter("options_count_distribution", Counter(str(len(row.options)) for row in selected))


def _print_counter(title: str, counts: Counter[str]) -> None:
    print(title)
    for key, count in sorted(counts.items()):
        print(f"  {key}: {count}")


def _provenance_fields(row: Mapping[str, JsonValue]) -> tuple[str, ...]:
    return tuple(
        sorted(key for key in row if any(marker in key.lower() for marker in PROVENANCE_FIELD_MARKERS))
    )


def _is_denied_provenance(row: Mapping[str, JsonValue], fields: tuple[str, ...]) -> bool:
    provenance_text = " ".join(json.dumps(row[field], ensure_ascii=False) for field in fields).lower()
    return any(term in provenance_text for term in DENIED_PROVENANCE_TERMS)


def _stripped(row: Mapping[str, JsonValue], key: str) -> str | None:
    value = row.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _stable_digest(namespace: str, uuid: str) -> str:
    return hashlib.sha256(f"{SAMPLE_SEED}:{namespace}:{uuid}".encode()).hexdigest()


def _stratum_sort_key(stratum: Stratum) -> tuple[str, int, str]:
    discipline, difficulty = stratum
    return discipline, DIFFICULTY_ORDER.get(difficulty, len(DIFFICULTY_ORDER)), difficulty


if __name__ == "__main__":
    raise SystemExit(main())
