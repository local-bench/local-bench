from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final, TypeAlias

DATASET_ID: Final = "gorilla-llm/Berkeley-Function-Calling-Leaderboard"
DATASET_REVISION: Final = "61fc0608cfd831fcfbbaa676ebdfef0ed963eeda"
DATASET_LICENSE: Final = "Apache-2.0"
BFCL_EVAL_REPO: Final = "https://github.com/ShishirPatil/gorilla"
BFCL_EVAL_REVISION: Final = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
BFCL_EVAL_LICENSE: Final = "Apache-2.0"
ITEMS_PER_CATEGORY: Final = 75
ROOT: Final = Path(__file__).resolve().parents[1]
OUT_PATH: Final = ROOT / "suite" / "v1" / "bfcl.jsonl"
HF_BASE_URL: Final = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/{DATASET_REVISION}"
CATEGORY_FILES: Final = {
    "simple": ("BFCL_v3_simple.json", "possible_answer/BFCL_v3_simple.json"),
    "multiple": ("BFCL_v3_multiple.json", "possible_answer/BFCL_v3_multiple.json"),
    "parallel": ("BFCL_v3_parallel.json", "possible_answer/BFCL_v3_parallel.json"),
    "parallel_multiple": ("BFCL_v3_parallel_multiple.json", "possible_answer/BFCL_v3_parallel_multiple.json"),
}

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

sys.path.insert(0, str(ROOT / "cli" / "src"))
from localbench.scorers.bfcl import score_bfcl  # noqa: E402


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    items: list[JsonObject] = []
    for category, (prompt_file, answer_file) in CATEGORY_FILES.items():
        prompts = _load_jsonl(_hf_url(prompt_file))
        answers = {str(row["id"]): row for row in _load_jsonl(_hf_url(answer_file))}
        candidates = [_normalize_item(0, category, prompt, answers[_required_str(prompt, "id")]) for prompt in prompts]
        selected = _stratified(_self_scorable(candidates), ITEMS_PER_CATEGORY)
        for prompt in selected:
            source_id = _required_str(prompt, "source_id")
            items.append({**prompt, "id": f"bfcl-{len(items) + 1:03d}", "source_id": source_id})
    _write_jsonl(OUT_PATH, items)
    return 0


def _normalize_item(index: int, category: str, prompt: Mapping[str, JsonValue], answer: Mapping[str, JsonValue]) -> JsonObject:
    source_id = _required_str(prompt, "id")
    answer_id = _required_str(answer, "id")
    if source_id != answer_id:
        raise ValueError(f"Prompt/answer id mismatch: {source_id} != {answer_id}")
    return {
        "id": f"bfcl-{index:03d}",
        "source_id": source_id,
        "category": category,
        "question": _required_json(prompt, "question"),
        "function": _required_json(prompt, "function"),
        "possible_answer": _required_json(answer, "ground_truth"),
    }


def _stratified(rows: list[JsonObject], count: int) -> list[JsonObject]:
    if len(rows) < count:
        raise ValueError(f"Need {count} rows, found {len(rows)}")
    if count == 1:
        return [rows[0]]
    indexes = [round(index * (len(rows) - 1) / (count - 1)) for index in range(count)]
    return [rows[index] for index in indexes]


def _self_scorable(rows: list[JsonObject]) -> list[JsonObject]:
    return [row for row in rows if score_bfcl(row, _expected_response(row))["correct"] is True]


def _hf_url(path: str) -> str:
    return f"{HF_BASE_URL}/{path}"


def _load_jsonl(url: str) -> list[JsonObject]:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            lines = response.read().decode("utf-8").splitlines()
    except urllib.error.URLError as error:
        raise SystemExit(f"Failed to fetch BFCL source file {url}: {error}") from error
    rows: list[JsonObject] = []
    for line_number, line in enumerate(lines, start=1):
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"{url}:{line_number} is not a JSON object")
        rows.append(parsed)
    return rows


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _required_json(row: Mapping[str, JsonValue], key: str) -> JsonValue:
    return row[key]


def _expected_response(item: Mapping[str, JsonValue]) -> str:
    possible_answer = item["possible_answer"]
    if not isinstance(possible_answer, list):
        raise TypeError("possible_answer must be a list")
    required_by_function = _required_by_function(item)
    calls = [_call_text(call, required_by_function) for call in possible_answer if isinstance(call, dict)]
    return "[" + ", ".join(calls) + "]"


def _required_by_function(item: Mapping[str, JsonValue]) -> dict[str, set[str]]:
    functions = item["function"]
    if not isinstance(functions, list):
        return {}
    required: dict[str, set[str]] = {}
    for function in functions:
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not isinstance(parameters, dict):
            continue
        required_params = parameters.get("required")
        if isinstance(required_params, list):
            required[name] = {param for param in required_params if isinstance(param, str)}
    return required


def _call_text(call: Mapping[str, JsonValue], required_by_function: Mapping[str, set[str]]) -> str:
    function_name, params = next(iter(call.items()))
    if not isinstance(params, dict):
        raise TypeError("params must be an object")
    required = required_by_function.get(function_name, set())
    args = [
        f"{key}={_repr_value(values)}"
        for key, values in params.items()
        if isinstance(values, list) and (key in required or "" not in values)
    ]
    return f"{function_name}(" + ", ".join(args) + ")"


def _repr_value(values: list[JsonValue]) -> str:
    value = next(item for item in values if item != "")
    return repr(_materialize(value))


def _materialize(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _materialize_list(item) if isinstance(item, list) else _materialize(item) for key, item in value.items()}
    return value


def _materialize_list(values: list[JsonValue]) -> JsonValue:
    value = next(item for item in values if item != "")
    return _materialize(value)


if __name__ == "__main__":
    raise SystemExit(main())
