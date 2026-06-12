from __future__ import annotations

import json
import random
from collections import Counter
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

from genmath_gen import TEMPLATES, Template, answer_to_string
from genmath_gen.models import ParamValue

DEFAULT_PRIVATE_SEED: Final = 2026061201
PRIVATE_SEED_ENV: Final = "LOCALBENCH_GENMATH_PRIVATE_SEED"
PRIVATE_DIR_NAME: Final = "private"
PRIVATE_FILE: Final = "genmath_sentinel.jsonl"
PRIVATE_LOCK_FILE: Final = "sentinel.lock.json"
PRIVATE_SENTINEL_COUNT: Final = len(TEMPLATES)
CATEGORY_ORDER: Final = (
    "arithmetic",
    "number_theory",
    "algebra",
    "combinatorics",
    "probability",
    "geometry",
    "rates_word",
)
DIFFICULTY_ORDER: Final = ("easy", "medium", "hard")
PRIVATE_MAX_ATTEMPTS: Final = 100
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
ParamSignature: TypeAlias = tuple[str, tuple[tuple[str, ParamValue], ...]]
Bucket: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GeneratedItemsets:
    standard: list[JsonObject]
    quick: list[JsonObject]


def build_itemsets(seed: int) -> GeneratedItemsets:
    standard: list[JsonObject] = []
    for template_index, template in enumerate(TEMPLATES):
        for instance_index in range(1, 3):
            standard.append(_make_item(template, seed, template_index, instance_index))
    quick_names = _quick_template_names(TEMPLATES)
    quick = [item for item in standard if str(item["template"]) in quick_names]
    return GeneratedItemsets(standard=standard, quick=quick)


def build_private_sentinel(public_items: Sequence[Mapping[str, JsonValue]], private_seed: int) -> list[JsonObject]:
    blocked_signatures = _item_signatures(public_items)
    blocked_statements = _item_statements(public_items)
    target_distribution = _private_target_distribution(public_items)
    private: list[JsonObject] = []

    if sum(target_distribution.values()) != PRIVATE_SENTINEL_COUNT:
        raise AssertionError("private sentinel target count must match template count")

    for bucket in _ordered_buckets():
        quota = target_distribution.get(bucket, 0)
        if quota == 0:
            continue
        private.extend(
            _make_disjoint_private_bucket_items(
                bucket=bucket,
                quota=quota,
                private_seed=private_seed,
                blocked_signatures=blocked_signatures,
                blocked_statements=blocked_statements,
            )
        )

    assert_public_private_disjoint(public_items, private)
    if len(private) != PRIVATE_SENTINEL_COUNT:
        raise AssertionError(f"private sentinel count mismatch: {len(private)}")
    return private


def _make_disjoint_private_bucket_items(
    bucket: Bucket,
    quota: int,
    private_seed: int,
    blocked_signatures: set[ParamSignature],
    blocked_statements: set[str],
) -> list[JsonObject]:
    items: list[JsonObject] = []
    candidates = [
        (template_index, template)
        for template_index, template in enumerate(TEMPLATES)
        if (template.category, template.difficulty) == bucket
    ]
    for instance_index in range(1, PRIVATE_MAX_ATTEMPTS + 1):
        for template_index, template in candidates:
            item = _make_item(
                template=template,
                seed=private_seed,
                template_index=template_index,
                instance_index=instance_index,
                id_prefix="genmath-v0-private",
            )
            signature = _item_signature(item)
            statement = str(item["statement"])
            if signature in blocked_signatures or statement in blocked_statements:
                continue
            items.append(item)
            blocked_signatures.add(signature)
            blocked_statements.add(statement)
            if len(items) == quota:
                return items
    raise AssertionError(f"could not draw {quota} disjoint private items for {bucket}")


def _private_target_distribution(public_items: Sequence[Mapping[str, JsonValue]]) -> Counter[Bucket]:
    public_distribution = Counter((str(item["category"]), str(item["difficulty"])) for item in public_items)
    target: Counter[Bucket] = Counter()
    for bucket, count in public_distribution.items():
        if count % 2 != 0:
            raise AssertionError(f"public bucket count must be even for {bucket}: {count}")
        target[bucket] = count // 2
    return target


def _ordered_buckets() -> list[Bucket]:
    return [(category, difficulty) for category in CATEGORY_ORDER for difficulty in DIFFICULTY_ORDER]


def assert_public_private_disjoint(
    public_items: Sequence[Mapping[str, JsonValue]],
    private_items: Sequence[Mapping[str, JsonValue]],
) -> None:
    signature_overlap = _item_signatures(public_items) & _item_signatures(private_items)
    if signature_overlap:
        raise AssertionError(f"public/private parameter overlap: {len(signature_overlap)}")
    statement_overlap = _item_statements(public_items) & _item_statements(private_items)
    if statement_overlap:
        raise AssertionError(f"public/private statement overlap: {len(statement_overlap)}")


def jsonl_bytes(rows: Iterable[Mapping[str, JsonValue]]) -> bytes:
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    return payload.encode("utf-8")


def _make_item(
    template: Template,
    seed: int,
    template_index: int,
    instance_index: int,
    id_prefix: str = "genmath-v0",
) -> JsonObject:
    rng = random.Random(seed * 1_000_003 + template_index * 101 + instance_index)
    params = template.sample(rng)
    answer = template.answer(params)
    return {
        "id": f"{id_prefix}-{template.name}-{instance_index}",
        "template": template.name,
        "category": template.category,
        "difficulty": template.difficulty,
        "statement": template.render(params),
        "answer": answer_to_string(answer),
        "params": dict(params),
    }


def _quick_template_names(templates: Iterable[Template]) -> set[str]:
    grouped: dict[str, list[Template]] = defaultdict(list)
    for template in templates:
        grouped[template.category].append(template)

    quotas = {
        "arithmetic": 3,
        "number_theory": 3,
        "algebra": 3,
        "combinatorics": 3,
        "probability": 3,
        "geometry": 3,
        "rates_word": 2,
    }
    selected: set[str] = set()
    for category in CATEGORY_ORDER:
        selected.update(_balanced_category_pick(grouped[category], quotas[category]))
    return selected


def _balanced_category_pick(templates: list[Template], quota: int) -> list[str]:
    by_difficulty = {
        difficulty: sorted(
            [template for template in templates if template.difficulty == difficulty],
            key=lambda template: template.name,
        )
        for difficulty in DIFFICULTY_ORDER
    }
    selected: list[str] = []
    while len(selected) < quota:
        for difficulty in ("medium", "easy", "hard"):
            candidates = by_difficulty[difficulty]
            if candidates and len(selected) < quota:
                selected.append(candidates.pop(0).name)
    return selected


def _item_signatures(rows: Sequence[Mapping[str, JsonValue]]) -> set[ParamSignature]:
    return {_item_signature(row) for row in rows}


def _item_signature(row: Mapping[str, JsonValue]) -> ParamSignature:
    params = row["params"]
    if not isinstance(params, dict):
        raise AssertionError("item params must be an object")
    normalized_params: list[tuple[str, ParamValue]] = []
    for key, value in params.items():
        if not isinstance(key, str) or not isinstance(value, str | int):
            raise AssertionError("item params must contain string, integer, or symbolic values")
        normalized_params.append((key, value))
    return (str(row["template"]), tuple(sorted(normalized_params)))


def _item_statements(rows: Sequence[Mapping[str, JsonValue]]) -> set[str]:
    return {str(row["statement"]) for row in rows}
