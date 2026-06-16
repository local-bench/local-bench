from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "bfcl_multi_turn.jsonl"
BFCL_EVAL_ROOT: Final = (
    ROOT / "cli" / ".venv" / "bfcl-eval-ref" / "berkeley-function-call-leaderboard"
)
BFCL_DATA_ROOT: Final = BFCL_EVAL_ROOT / "bfcl_eval" / "data"
BFCL_EVAL_REPO: Final = "https://github.com/ShishirPatil/gorilla"
BFCL_EVAL_REVISION: Final = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
BFCL_EVAL_LICENSE: Final = "Apache-2.0"
SOURCE_DATASET: Final = "vendored bfcl-eval BFCL_v4_multi_turn_base+long_context"
TARGET_PER_CATEGORY: Final = 50
SAMPLE_SEED: Final = "local-bench-suite-v1-bfcl-multi-turn-20260616"
SOURCE_FILES: Final = (
    "BFCL_v4_multi_turn_base.json",
    "BFCL_v4_multi_turn_long_context.json",
)
FUNC_DOC_FILES: Final = {
    "GorillaFileSystem": "gorilla_file_system.json",
    "MathAPI": "math_api.json",
    "MessageAPI": "message_api.json",
    "TwitterAPI": "posting_api.json",
    "TicketAPI": "ticket_api.json",
    "TradingBot": "trading_bot.json",
    "TravelAPI": "travel_booking.json",
    "VehicleControlAPI": "vehicle_control.json",
}

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class BuildError(RuntimeError):
    pass


def main() -> int:
    rows = _load_candidates()
    selected = _stratified_sample(rows, per_category=TARGET_PER_CATEGORY, sample_seed=SAMPLE_SEED)
    _write_jsonl(OUT_PATH, selected)
    print(_datasheet_lines(selected, itemset_sha256=_sha256(OUT_PATH)))
    return 0


def _load_candidates() -> list[JsonObject]:
    candidates: list[JsonObject] = []
    for file_name in SOURCE_FILES:
        source_rows = _load_jsonl(BFCL_DATA_ROOT / file_name)
        answers = {_required_str(row, "id"): row for row in _load_jsonl(BFCL_DATA_ROOT / "possible_answer" / file_name)}
        for source in source_rows:
            source_id = _required_str(source, "id")
            answer = answers.get(source_id)
            if answer is None:
                raise BuildError(f"Missing possible answer for {source_id}")
            function_docs = _function_docs(source)
            candidates.append(_normalize_item(len(candidates) + 1, source, answer, function_docs=function_docs))
    return candidates


def _normalize_item(
    index: int,
    source: Mapping[str, JsonValue],
    answer: Mapping[str, JsonValue],
    *,
    function_docs: list[JsonObject],
) -> JsonObject:
    source_id = _required_str(source, "id")
    if source_id != _required_str(answer, "id"):
        raise BuildError(f"Prompt/answer id mismatch for {source_id}")
    question = source.get("question")
    if not isinstance(question, list) or not question:
        raise BuildError(f"{source_id}: question must be a non-empty list")
    initial_config = source.get("initial_config")
    if not isinstance(initial_config, dict):
        raise BuildError(f"{source_id}: initial_config must be an object")
    ground_truth = answer.get("ground_truth")
    if not isinstance(ground_truth, list) or not ground_truth:
        raise BuildError(f"{source_id}: ground_truth must be a non-empty list")
    return {
        "id": f"bfcl-mt-{index:03d}",
        "source_id": source_id,
        "category": source_id.rsplit("_", 1)[0],
        "turn_count": len(question),
        "involved_classes": _str_list(source.get("involved_classes")),
        "question": question,
        "initial_config": initial_config,
        "path": _str_list(source.get("path")),
        "excluded_function": _str_list(source.get("excluded_function")),
        "function": function_docs,
        "ground_truth": ground_truth,
        "source_dataset": SOURCE_DATASET,
        "source_revision": BFCL_EVAL_REVISION,
        "license": BFCL_EVAL_LICENSE,
    }


def _stratified_sample(
    rows: list[JsonObject],
    *,
    per_category: int,
    sample_seed: str,
) -> list[JsonObject]:
    by_category: dict[str, list[JsonObject]] = {}
    for row in rows:
        by_category.setdefault(_required_str(row, "category"), []).append(row)
    selected: list[JsonObject] = []
    for category, category_rows in sorted(by_category.items()):
        if len(category_rows) < per_category:
            raise BuildError(f"Need {per_category} {category} rows, found {len(category_rows)}")
        ordered = sorted(category_rows, key=lambda row: _stable_digest("sample", _required_str(row, "source_id"), sample_seed))
        selected.extend(ordered[:per_category])
    ordered_selected = sorted(selected, key=lambda row: _stable_digest("order", _required_str(row, "source_id"), sample_seed))
    return [{**row, "id": f"bfcl-mt-{index:03d}"} for index, row in enumerate(ordered_selected, start=1)]


def _function_docs(source: Mapping[str, JsonValue]) -> list[JsonObject]:
    excluded = set(_str_list(source.get("excluded_function")))
    docs: list[JsonObject] = []
    for class_name in _str_list(source.get("involved_classes")):
        file_name = FUNC_DOC_FILES.get(class_name)
        if file_name is None:
            raise BuildError(f"Class is not allowlisted for BFCL multi-turn: {class_name}")
        docs.extend(_load_jsonl(BFCL_DATA_ROOT / "multi_turn_func_doc" / file_name))
    return [doc for doc in docs if _required_str(doc, "name") not in excluded]


def _datasheet_lines(items: list[Mapping[str, JsonValue]], *, itemset_sha256: str) -> str:
    lines = [
        f"source_dataset={SOURCE_DATASET}",
        f"bfcl_eval_repo={BFCL_EVAL_REPO}",
        f"bfcl_eval_revision={BFCL_EVAL_REVISION}",
        f"license={BFCL_EVAL_LICENSE}",
        f"emitted={len(items)}",
        f"itemset_sha256={itemset_sha256}",
        "category_distribution",
    ]
    counts = Counter(_required_str(item, "category") for item in items)
    lines.extend(f"  {key}: {count}" for key, count in sorted(counts.items()))
    classes = Counter(class_name for item in items for class_name in _str_list(item.get("involved_classes")))
    lines.append("class_distribution")
    lines.extend(f"  {key}: {count}" for key, count in sorted(classes.items()))
    return "\n".join(lines)


def _load_jsonl(path: Path) -> list[JsonObject]:
    rows: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise BuildError(f"{path.name}:{line_number} is not an object")
            rows.append(parsed)
    return rows


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_digest(namespace: str, source_id: str, sample_seed: str) -> str:
    return hashlib.sha256(f"{sample_seed}:{namespace}:{source_id}".encode()).hexdigest()


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise BuildError(f"{key} must be a non-empty string")
    return value


def _str_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


if __name__ == "__main__":
    raise SystemExit(main())
