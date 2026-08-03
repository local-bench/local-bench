from __future__ import annotations

import importlib
import os
import random
from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager
from typing import Protocol, cast

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError
from localbench.checkset.select import SELECTION_SEED
from localbench.checkset.upstream import (
    GPQA_CONFIG,
    GPQA_REPO,
    GPQA_REVISION,
    OLYMMATH_AIME_CONFIG,
    OLYMMATH_REPO,
    OLYMMATH_REVISION,
)


class _DatasetLoader(Protocol):
    def __call__(
        self,
        path: str,
        name: str,
        *,
        split: str,
        revision: str,
        download_mode: str,
    ) -> object: ...


def load_upstream_sources(manifest: JsonObject) -> dict[str, JsonObject]:
    try:
        datasets_module = importlib.import_module("datasets")
    except ModuleNotFoundError as error:
        raise CheckError(
            "full live checks require the cached licensed datasets and localbench[build]"
        ) from error
    raw_loader = getattr(datasets_module, "load_dataset", None)
    if not callable(raw_loader):
        raise CheckError("datasets.load_dataset is unavailable")
    loader = cast(_DatasetLoader, raw_loader)
    with _offline_datasets():
        gpqa_rows = _rows(
            loader(
                GPQA_REPO,
                GPQA_CONFIG,
                split="train",
                revision=GPQA_REVISION,
                download_mode="reuse_dataset_if_exists",
            ),
            GPQA_REPO,
        )
        math_rows = _rows(
            loader(
                OLYMMATH_REPO,
                OLYMMATH_AIME_CONFIG,
                split="test",
                revision=OLYMMATH_REVISION,
                download_mode="reuse_dataset_if_exists",
            ),
            OLYMMATH_REPO,
        )
    sources = _gpqa_sources(gpqa_rows)
    sources.update(_math_sources(manifest, math_rows))
    return sources


def _gpqa_sources(rows: tuple[Mapping[str, JsonValue], ...]) -> dict[str, JsonObject]:
    if len(rows) != 198:
        raise CheckError(f"cached GPQA Diamond row count is {len(rows)}, expected 198")
    rng = random.Random(SELECTION_SEED)
    sources: dict[str, JsonObject] = {}
    for index, row in enumerate(rows):
        choices = [
            (_required_text(row, "Correct Answer"), True),
            (_required_text(row, "Incorrect Answer 1"), False),
            (_required_text(row, "Incorrect Answer 2"), False),
            (_required_text(row, "Incorrect Answer 3"), False),
        ]
        rng.shuffle(choices)
        record_id = _required_text(row, "Record ID")
        choice_values: list[JsonValue] = [choice[0] for choice in choices]
        sources[f"gpqa-diamond-{record_id or index}"] = {
            "answer_index": next(position for position, choice in enumerate(choices) if choice[1]),
            "choices": choice_values,
            "question": _required_text(row, "Question"),
            "record_id": record_id,
            "source_revision": GPQA_REVISION,
        }
    return sources


def _math_sources(
    manifest: JsonObject,
    rows: tuple[Mapping[str, JsonValue], ...],
) -> dict[str, JsonObject]:
    metadata = manifest.get("source_metadata")
    math = metadata.get("math_aime") if isinstance(metadata, dict) else None
    selected = math.get("selected") if isinstance(math, dict) else None
    if not isinstance(selected, list) or len(selected) != 30:
        raise CheckError("manifest math AIME source selection is invalid")
    sources: dict[str, JsonObject] = {}
    for record in selected:
        index = record.get("upstream_index") if isinstance(record, dict) else None
        if not isinstance(index, int) or index < 0 or index >= len(rows):
            raise CheckError("manifest math AIME upstream index is invalid")
        sources[f"olymmath-en-easy-{index:05d}"] = dict(rows[index])
    return sources


def _rows(value: object, source: str) -> tuple[Mapping[str, JsonValue], ...]:
    if not isinstance(value, Iterable):
        raise CheckError(f"cached dataset {source} is not iterable")
    rows: list[Mapping[str, JsonValue]] = []
    for raw_value in value:
        if not isinstance(raw_value, Mapping):
            raise CheckError(f"cached dataset {source} contains a non-object row")
        raw = cast(Mapping[object, object], raw_value)
        row: JsonObject = {}
        for key, item in raw.items():
            if not isinstance(key, str):
                raise CheckError(f"cached dataset {source} contains a non-string field")
            row[key] = cast(JsonValue, item)
        rows.append(row)
    return tuple(rows)


def _required_text(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise CheckError(f"cached GPQA field {key!r} is invalid")
    return value


@contextmanager
def _offline_datasets() -> Generator[None]:
    names = ("HF_DATASETS_OFFLINE", "HF_HUB_OFFLINE")
    previous = {name: os.environ.get(name) for name in names}
    for name in names:
        os.environ[name] = "1"
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                _ = os.environ.pop(name, None)
            else:
                os.environ[name] = value
