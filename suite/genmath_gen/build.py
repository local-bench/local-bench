# /// script
# dependencies = []
# ///
# ----- How to run -----
# From the repo root:
#   cli/.venv/Scripts/python suite/genmath_gen/build.py --seed 20260612

"""Build generated-math suite-v0 item sets."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genmath_gen import TEMPLATES, Template, answer_to_string

DEFAULT_SEED = 20260612
ROOT = Path(__file__).resolve().parents[2]
STANDARD_FILE = "genmath_standard.jsonl"
QUICK_FILE = "genmath_quick.jsonl"
CATEGORY_ORDER = (
    "arithmetic",
    "number_theory",
    "algebra",
    "combinatorics",
    "probability",
    "geometry",
    "rates_word",
)
DIFFICULTY_ORDER = ("easy", "medium", "hard")
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class GeneratedItemsets:
    """Generated standard and quick item rows."""

    standard: list[JsonObject]
    quick: list[JsonObject]


def build_itemsets(seed: int) -> GeneratedItemsets:
    """Generate standard and quick genmath item sets."""
    standard: list[JsonObject] = []
    for template_index, template in enumerate(TEMPLATES):
        for instance_index in range(1, 3):
            standard.append(_make_item(template, seed, template_index, instance_index))
    quick_names = _quick_template_names(TEMPLATES)
    quick = [item for item in standard if str(item["template"]) in quick_names]
    return GeneratedItemsets(standard=standard, quick=quick)


def jsonl_bytes(rows: Iterable[Mapping[str, JsonValue]]) -> bytes:
    """Serialize rows to canonical JSONL bytes."""
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    return payload.encode("utf-8")


def build_files(seed: int = DEFAULT_SEED, repo_root: Path | None = None) -> None:
    """Write generated files, lock entries, suite entry, and review document."""
    root = repo_root or ROOT
    suite_dir = root / "suite" / "v0"
    docs_dir = root / "docs"
    template_dir = suite_dir / "templates"
    itemsets = build_itemsets(seed)

    suite_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    template_dir.mkdir(parents=True, exist_ok=True)

    _write_bytes(suite_dir / STANDARD_FILE, jsonl_bytes(itemsets.standard))
    _write_bytes(suite_dir / QUICK_FILE, jsonl_bytes(itemsets.quick))
    (template_dir / "genmath.txt").write_text("{statement}", encoding="utf-8", newline="\n")

    standard_entry = _lock_entry(suite_dir / STANDARD_FILE, len(itemsets.standard), seed)
    quick_entry = _lock_entry(suite_dir / QUICK_FILE, len(itemsets.quick), seed)
    _write_json(suite_dir / "itemsets.lock.json", _updated_lock(suite_dir, standard_entry, quick_entry))
    _write_json(suite_dir / "suite.json", _updated_suite(suite_dir, standard_entry, quick_entry))
    (docs_dir / "genmath-review.md").write_text(_review_doc(seed), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    build_files(seed=args.seed)
    return 0


def _make_item(template: Template, seed: int, template_index: int, instance_index: int) -> JsonObject:
    rng = random.Random(seed * 1_000_003 + template_index * 101 + instance_index)
    params = template.sample(rng)
    answer = template.answer(params)
    return {
        "id": f"genmath-v0-{template.name}-{instance_index}",
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


def _write_bytes(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


def _lock_entry(path: Path, count: int, seed: int) -> JsonObject:
    return {
        "item_count": count,
        "seed": seed,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _updated_lock(suite_dir: Path, standard: JsonObject, quick: JsonObject) -> JsonObject:
    lock = _read_json(suite_dir / "itemsets.lock.json")
    files = lock.get("files")
    next_files = dict(files) if isinstance(files, dict) else {}
    next_files[STANDARD_FILE] = standard
    next_files[QUICK_FILE] = quick
    return {"files": next_files}


def _updated_suite(suite_dir: Path, standard: JsonObject, quick: JsonObject) -> JsonObject:
    suite = _read_json(suite_dir / "suite.json")
    benches = suite.get("benches")
    next_benches = dict(benches) if isinstance(benches, dict) else {}
    next_benches["genmath"] = {
        "chance_correction_baseline": 0.0,
        "decoding": {"max_tokens": 8192, "temperature": 0},
        "itemsets": {
            "quick": _itemset_spec(QUICK_FILE, quick),
            "standard": _itemset_spec(STANDARD_FILE, standard),
        },
        "lane_caps": {},
        "template": "templates/genmath.txt",
    }
    return {"benches": next_benches, "version": str(suite.get("version") or "suite-v0")}


def _itemset_spec(filename: str, entry: Mapping[str, JsonValue]) -> JsonObject:
    return {
        "file": filename,
        "item_count": int(entry["item_count"]),
        "sha256": str(entry["sha256"]),
    }


def _read_json(path: Path) -> JsonObject:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _review_doc(seed: int) -> str:
    lines = [
        "# Generated Math Review",
        "",
        f"Seed: {seed}",
        f"Template count: {len(TEMPLATES)}",
        "",
    ]
    for index, template in enumerate(TEMPLATES):
        rng = random.Random(seed * 2_000_003 + index)
        params = template.sample(rng)
        answer = template.answer(params)
        lines.extend(
            [
                f"## {template.name}",
                "",
                f"- category: {template.category}",
                f"- difficulty: {template.difficulty}",
                f"- sample: {template.render(params)}",
                f"- answer: {answer_to_string(answer)}",
            ]
        )
        brute_line = _bruteforce_review_line(template, seed, index)
        if brute_line:
            lines.append(f"- {brute_line}")
        lines.append("")
    return "\n".join(lines)


def _bruteforce_review_line(template: Template, seed: int, template_index: int) -> str | None:
    if template.brute_force is None:
        return None
    instances = 50
    for offset in range(instances):
        params = template.sample(random.Random(seed * 3_000_001 + template_index * 211 + offset))
        if template.answer(params) != template.brute_force(params):
            raise AssertionError(f"brute-force check failed for {template.name}")
    return f"brute-force verified: yes/{instances}-instances"


if __name__ == "__main__":
    raise SystemExit(main())
