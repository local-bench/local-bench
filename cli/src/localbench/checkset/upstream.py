from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from localbench.checkset.models import ItemRecord, JsonObject, JsonValue, ModuleRecord
from localbench.checkset.select import (
    SELECTION_SEED,
    MediumMathItem,
    select_math_medium,
)

GPQA_REPO: Final = "Idavidrein/gpqa"
GPQA_CONFIG: Final = "gpqa_diamond"
GPQA_REVISION: Final = "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
OLYMMATH_REPO: Final = "RUC-AIBOX/OlymMATH"
OLYMMATH_MEDIUM_CONFIG: Final = "en-medium"
OLYMMATH_REVISION: Final = "2c6532ea2cf929ac1c421532af5951553eaee727"


@dataclass(frozen=True, slots=True)
class UpstreamError(RuntimeError):
    source: str
    detail: str

    def __str__(self) -> str:
        return f"{self.source}: {self.detail}"


def prepare_gpqa(
    rows: Sequence[Mapping[str, JsonValue]],
    *,
    revision: str,
) -> tuple[ModuleRecord, tuple[JsonObject, ...]]:
    rng = random.Random(SELECTION_SEED)
    records: list[ItemRecord] = []
    canary_log: list[JsonObject] = []
    for index, row in enumerate(rows):
        record_id = _required_str(row, "Record ID")
        choices = [
            (_required_str(row, "Correct Answer"), True),
            (_required_str(row, "Incorrect Answer 1"), False),
            (_required_str(row, "Incorrect Answer 2"), False),
            (_required_str(row, "Incorrect Answer 3"), False),
        ]
        rng.shuffle(choices)
        content: JsonObject = {
            "answer_index": next(position for position, choice in enumerate(choices) if choice[1]),
            "choices": [choice[0] for choice in choices],
            "question": _required_str(row, "Question"),
            "record_id": record_id,
            "source_revision": revision,
        }
        canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        records.append(ItemRecord(f"gpqa-diamond-{record_id or index:}", hashlib.sha256(canonical).hexdigest()))
        canary = _required_str(row, "Canary String")
        canary_log.append(
            {
                "field": "Canary String",
                "item_id": records[-1].item_id,
                "removed_sha256": hashlib.sha256(canary.encode("utf-8")).hexdigest(),
            }
        )
    return ModuleRecord(name="knowledge", scored=len(records), items=tuple(records)), tuple(canary_log)


def fetch_gpqa() -> tuple[ModuleRecord, tuple[JsonObject, ...]]:
    try:
        from datasets import Dataset, load_dataset
    except ModuleNotFoundError as error:
        raise UpstreamError(GPQA_REPO, "datasets build dependency is not installed") from error
    try:
        dataset = load_dataset(GPQA_REPO, GPQA_CONFIG, split="train", revision=GPQA_REVISION)
    except (OSError, RuntimeError, ValueError) as error:
        raise UpstreamError(GPQA_REPO, str(error)) from error
    if not isinstance(dataset, Dataset):
        raise UpstreamError(GPQA_REPO, "loader did not return a Dataset")
    rows = tuple(dict(row) for row in dataset)
    if len(rows) != 198:
        raise UpstreamError(GPQA_REPO, f"Diamond row count is {len(rows)}, expected 198")
    return prepare_gpqa(rows, revision=GPQA_REVISION)


def fetch_math_medium() -> tuple[MediumMathItem, ...]:
    try:
        from datasets import Dataset, get_dataset_config_names, load_dataset
    except ModuleNotFoundError as error:
        raise UpstreamError(OLYMMATH_REPO, "datasets build dependency is not installed") from error
    configs = get_dataset_config_names(OLYMMATH_REPO, revision=OLYMMATH_REVISION)
    if OLYMMATH_MEDIUM_CONFIG not in configs:
        available = ", ".join(configs)
        raise UpstreamError(
            OLYMMATH_REPO,
            f"locked revision {OLYMMATH_REVISION} has no {OLYMMATH_MEDIUM_CONFIG!r} config; available: {available}",
        )
    dataset = load_dataset(
        OLYMMATH_REPO,
        OLYMMATH_MEDIUM_CONFIG,
        split="test",
        revision=OLYMMATH_REVISION,
    )
    if not isinstance(dataset, Dataset):
        raise UpstreamError(OLYMMATH_REPO, "loader did not return a Dataset")
    rows = tuple(dict(row) for row in dataset)
    return select_math_medium(rows, quota=30)


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise UpstreamError(GPQA_REPO, f"{key!r} must be a string")
    return value
