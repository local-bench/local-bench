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
    AimeMathItem,
    select_math_aime,
)

GPQA_REPO: Final = "Idavidrein/gpqa"
GPQA_CONFIG: Final = "gpqa_diamond"
GPQA_REVISION: Final = "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
OLYMMATH_REPO: Final = "RUC-AIBOX/OlymMATH"
OLYMMATH_AIME_CONFIG: Final = "en-easy"
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
    row_documents: list[JsonValue] = [dict(row) for row in rows]
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
        records.append(
            ItemRecord(
                f"gpqa-diamond-{record_id or index:}",
                hashlib.sha256(canonical).hexdigest(),
                "complete",
            )
        )
        canary = _required_str(row, "Canary String")
        canary_log.append(
            {
                "field": "Canary String",
                "item_id": records[-1].item_id,
                "removed_sha256": hashlib.sha256(canary.encode("utf-8")).hexdigest(),
            }
        )
    return ModuleRecord(
        name="knowledge",
        scored=len(records),
        items=tuple(records),
        source={"dataset": GPQA_REPO, "revision": revision, "split": "train"},
        scorer={"name": "mcq", "version": "localbench-v1"},
        selection={
            "algorithm": "complete-seeded-choice-shuffle-v1",
            "inputs_sha256": _json_sha256(row_documents),
            "seed": SELECTION_SEED,
        },
    ), tuple(canary_log)


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


def fetch_math_aime() -> tuple[AimeMathItem, ...]:
    try:
        from datasets import Dataset, get_dataset_config_names, load_dataset
    except ModuleNotFoundError as error:
        raise UpstreamError(OLYMMATH_REPO, "datasets build dependency is not installed") from error
    configs = get_dataset_config_names(OLYMMATH_REPO, revision=OLYMMATH_REVISION)
    if OLYMMATH_AIME_CONFIG not in configs:
        available = ", ".join(configs)
        raise UpstreamError(
            OLYMMATH_REPO,
            f"locked revision {OLYMMATH_REVISION} has no {OLYMMATH_AIME_CONFIG!r} config; available: {available}",
        )
    dataset = load_dataset(
        OLYMMATH_REPO,
        OLYMMATH_AIME_CONFIG,
        split="test",
        revision=OLYMMATH_REVISION,
    )
    if not isinstance(dataset, Dataset):
        raise UpstreamError(OLYMMATH_REPO, "loader did not return a Dataset")
    rows = tuple(dict(row) for row in dataset)
    return select_math_aime(rows, quota=30)


def combine_math_module(legacy: ModuleRecord, aime: Sequence[AimeMathItem]) -> ModuleRecord:
    if legacy.name != "math-legacy" or legacy.scored != 30 or len(legacy.items) != 30:
        raise UpstreamError(OLYMMATH_REPO, "legacy math input must contain exactly 30 authored records")
    if len(aime) != 30:
        raise UpstreamError(OLYMMATH_REPO, f"AIME-band draw contains {len(aime)} rows, expected 30")
    aime_records = tuple(
        ItemRecord(
            f"olymmath-en-easy-{item.upstream_index:05d}",
            item.content_sha256,
            f"aime:{item.subject}",
        )
        for item in aime
    )
    legacy_revision = legacy.source.get("revision") if isinstance(legacy.source, dict) else _json_sha256(
        [item.as_json() for item in legacy.items]
    )
    legacy_inputs = legacy.selection.get("inputs_sha256") if isinstance(legacy.selection, dict) else legacy_revision
    return ModuleRecord(
        name="math",
        scored=60,
        items=legacy.items + aime_records,
        source={
            "dataset": "suite/v2/legacy-math+RUC-AIBOX/OlymMATH",
            "revision": _json_sha256({"legacy": legacy_revision, "olymmath": OLYMMATH_REVISION}),
            "split": "legacy-informative+test",
        },
        scorer={"name": "math_symbolic_numeric", "version": "localbench-v1"},
        selection={
            "algorithm": "legacy-cost-aware-plus-model-blind-subject-stratified-v1",
            "inputs_sha256": _json_sha256(
                {
                    "aime": [
                        {
                            "content_sha256": item.content_sha256,
                            "subject": item.subject,
                            "upstream_index": item.upstream_index,
                        }
                        for item in aime
                    ],
                    "legacy": legacy_inputs,
                }
            ),
            "seed": SELECTION_SEED,
        },
    )


def _json_sha256(value: JsonValue) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise UpstreamError(GPQA_REPO, f"{key!r} must be a string")
    return value
