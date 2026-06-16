# /// script
# dependencies = ["huggingface_hub>=1.19.0"]
# ///
# --- How to run ---
# From the repository root:
#   cli/.venv/Scripts/python.exe suite/build_v1_toolhop.py

from __future__ import annotations

import ast
import hashlib
import json
import sys
import warnings
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

ROOT: Final = Path(__file__).resolve().parents[1]
CLI_SRC: Final = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))
warnings.filterwarnings("ignore", category=SyntaxWarning)

from localbench.scorers.toolhop._parser import parse_call  # noqa: E402
from localbench.scorers.toolhop._tool_loader import (  # noqa: E402
    ALLOWED_IMPORTS,
    FORBIDDEN_IMPORTS,
    function_names_from_source,
    validate_tool_source,
)

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

OUT_PATH: Final = ROOT / "suite" / "v1" / "toolhop.jsonl"
SOURCE_DATASET: Final = "bytedance-research/ToolHop"
TOOLHOP_REPO: Final = "https://huggingface.co/datasets/bytedance-research/ToolHop"
TOOLHOP_REVISION: Final = "b439d7279af359fda46e8117ae4f0245b75f5c6b"
TOOLHOP_DATA_FILE: Final = "data/ToolHop.json"
TOOLHOP_LICENSE: Final = "CC-BY-4.0"
TOOLHOP_CODE_LICENSE: Final = "Apache-2.0"
TARGET_COUNT: Final = 100
GOLD_TRACE_TARGET: Final = 20
SAMPLE_SEED: Final = "local-bench-suite-v1-toolhop-20260616"
MISSING_MODULES: Final = frozenset({"babel", "dicttoxml", "holidays", "pytz", "roman"})


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    accepted: bool
    reasons: tuple[str, ...]
    gold_calls: tuple[str, ...]


def main() -> int:
    rows = _load_source_rows()
    candidates, skipped = _load_candidates(rows)
    selected = _select_items(candidates, target_count=TARGET_COUNT)
    _write_jsonl(OUT_PATH, _assign_ids(selected))
    print(_datasheet_lines(selected, skipped=skipped, itemset_sha256=_sha256(OUT_PATH)))
    return 0


def _load_candidates(rows: list[JsonObject]) -> tuple[list[JsonObject], Counter[str]]:
    candidates: list[JsonObject] = []
    skipped: Counter[str] = Counter()
    for row in rows:
        validation = _validate_candidate(row)
        if not validation.accepted:
            skipped.update(validation.reasons)
            continue
        item = _normalize_item(len(candidates) + 1, row, gold_calls=list(validation.gold_calls))
        if item["gold_calls"] and not _gold_trace_scores(item):
            item["gold_calls"] = []
        candidates.append(item)
    if len(candidates) < TARGET_COUNT:
        raise BuildError(f"Need {TARGET_COUNT} confined ToolHop rows, found {len(candidates)}")
    return candidates, skipped


def _validate_candidate(row: Mapping[str, JsonValue]) -> CandidateValidation:
    reasons: list[str] = []
    functions = _str_list(row.get("functions"))
    tools = row.get("tools")
    sub_task = row.get("sub_task")
    if not isinstance(row.get("id"), int):
        reasons.append("schema:id")
    if not isinstance(row.get("question"), str) or not str(row.get("question")).strip():
        reasons.append("schema:question")
    if not isinstance(row.get("answer"), str) or not str(row.get("answer")).strip():
        reasons.append("schema:answer")
    if not isinstance(tools, dict) or not tools:
        reasons.append("schema:tools")
    if not isinstance(sub_task, dict) or not sub_task:
        reasons.append("schema:sub_task")
    if not functions:
        reasons.append("schema:functions")
    import_roots = set().union(*(_import_roots(source) for source in functions)) if functions else set()
    reasons.extend(f"missing_module:{root}" for root in sorted(import_roots & MISSING_MODULES))
    if not reasons:
        for source in functions:
            reasons.extend(validate_tool_source(source))
    tool_names = set(_tool_names(row))
    function_names = {name for source in functions for name in function_names_from_source(source)}
    missing_tools = tool_names - function_names
    reasons.extend(f"missing_tool_impl:{name}" for name in sorted(missing_tools))
    unsupported_roots = import_roots - ALLOWED_IMPORTS - MISSING_MODULES - FORBIDDEN_IMPORTS
    reasons.extend(f"unsupported_module:{root}" for root in sorted(unsupported_roots))
    gold_calls = tuple(_extract_gold_calls(functions))
    return CandidateValidation(accepted=not reasons, reasons=tuple(sorted(set(reasons))), gold_calls=gold_calls)


def _normalize_item(index: int, source: Mapping[str, JsonValue], *, gold_calls: list[str]) -> JsonObject:
    source_id = source.get("id")
    if not isinstance(source_id, int):
        raise BuildError("ToolHop source id must be an integer")
    domain = _required_str(source, "domain")
    sub_task = source.get("sub_task")
    return {
        "id": f"toolhop-{index:03d}",
        "source_id": source_id,
        "question": _required_str(source, "question"),
        "answer": _required_str(source, "answer"),
        "sub_task": dict(sub_task) if isinstance(sub_task, dict) else {},
        "tools": dict(source.get("tools")) if isinstance(source.get("tools"), dict) else {},
        "functions": _str_list(source.get("functions")),
        "domain": domain,
        "category": _category(domain),
        "answer_type": _required_str(source, "answer_type"),
        "previous_answer_type": _required_str(source, "previous_answer_type"),
        "hop_count": len(sub_task) if isinstance(sub_task, dict) else 0,
        "gold_calls": gold_calls,
        "source_dataset": SOURCE_DATASET,
        "source_revision": TOOLHOP_REVISION,
        "source_repo": TOOLHOP_REPO,
        "license": TOOLHOP_LICENSE,
        "code_license": TOOLHOP_CODE_LICENSE,
    }


def _select_items(rows: list[JsonObject], *, target_count: int) -> list[JsonObject]:
    with_gold = [row for row in rows if _str_list(row.get("gold_calls"))]
    seed_count = min(GOLD_TRACE_TARGET, len(with_gold), target_count)
    selected = _stratified_sample(with_gold, target_count=seed_count, sample_seed=f"{SAMPLE_SEED}:gold")
    selected_ids = {_source_id(row) for row in selected}
    remaining = [row for row in rows if _source_id(row) not in selected_ids]
    selected.extend(
        _stratified_sample(
            remaining,
            target_count=target_count - len(selected),
            sample_seed=f"{SAMPLE_SEED}:fill",
        ),
    )
    return sorted(selected, key=lambda row: _stable_digest("order", str(_source_id(row)), SAMPLE_SEED))


def _stratified_sample(rows: list[JsonObject], *, target_count: int, sample_seed: str) -> list[JsonObject]:
    if target_count <= 0:
        return []
    by_stratum: dict[str, list[JsonObject]] = {}
    for row in rows:
        by_stratum.setdefault(_stratum(row), []).append(row)
    for stratum_rows in by_stratum.values():
        stratum_rows.sort(key=lambda row: _stable_digest("sample", str(_source_id(row)), sample_seed))
    selected: list[JsonObject] = []
    while len(selected) < target_count and any(by_stratum.values()):
        for stratum in sorted(by_stratum):
            if not by_stratum[stratum]:
                continue
            selected.append(by_stratum[stratum].pop(0))
            if len(selected) == target_count:
                break
    return selected


def _assign_ids(rows: list[JsonObject]) -> list[JsonObject]:
    return [{**row, "id": f"toolhop-{index:03d}"} for index, row in enumerate(rows, start=1)]


def _extract_gold_calls(functions: list[str]) -> list[str]:
    calls: list[str] = []
    for source in functions:
        name = _first_function_name(source)
        if name is None:
            return []
        call = _first_literal_example_call(source, name)
        if call is None or parse_call(call) is None:
            return []
        calls.append(call)
    return calls


def _gold_trace_scores(item: Mapping[str, JsonValue]) -> bool:
    from localbench.scorers.toolhop import score_toolhop

    gold_calls = item.get("gold_calls")
    if not isinstance(gold_calls, list) or not gold_calls:
        return False
    score = score_toolhop(item, json.dumps(gold_calls))
    return score["correct"] is True


def _first_literal_example_call(source: str, function_name: str) -> str | None:
    tree = ast.parse(source)
    for stmt in tree.body:
        if isinstance(stmt, ast.Import | ast.ImportFrom | ast.FunctionDef | ast.ClassDef):
            continue
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == function_name and _literal_call(node):
                segment = ast.get_source_segment(source, node)
                return segment.strip() if segment is not None else None
    return None


def _literal_call(node: ast.Call) -> bool:
    return all(_literal_expr(arg) for arg in node.args) and all(
        keyword.arg is not None and _literal_expr(keyword.value) for keyword in node.keywords
    )


def _literal_expr(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _literal_expr(node.operand)
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return all(_literal_expr(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is not None and _literal_expr(key) and _literal_expr(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return False


def _datasheet_lines(
    items: list[Mapping[str, JsonValue]],
    *,
    skipped: Counter[str],
    itemset_sha256: str,
) -> str:
    lines = [
        f"source_dataset={SOURCE_DATASET}",
        f"source_repo={TOOLHOP_REPO}",
        f"toolhop_revision={TOOLHOP_REVISION}",
        f"license={TOOLHOP_LICENSE}",
        f"code_license={TOOLHOP_CODE_LICENSE}",
        f"emitted={len(items)}",
        f"itemset_sha256={itemset_sha256}",
        f"gold_trace_items={sum(1 for item in items if _str_list(item.get('gold_calls')))}",
        "category_distribution",
    ]
    lines.extend(f"  {key}: {count}" for key, count in sorted(Counter(_required_str(item, "category") for item in items).items()))
    lines.append("hop_distribution")
    lines.extend(f"  hop_{key}: {count}" for key, count in sorted(Counter(int(item["hop_count"]) for item in items).items()))
    lines.append("answer_type_distribution")
    lines.extend(f"  {key}: {count}" for key, count in sorted(Counter(_required_str(item, "answer_type") for item in items).items()))
    lines.append("skipped_for_confinement")
    lines.extend(f"  {key}: {count}" for key, count in sorted(skipped.items()))
    return "\n".join(lines)


def _load_source_rows() -> list[JsonObject]:
    from huggingface_hub import hf_hub_download

    data_path = Path(
        hf_hub_download(
            repo_id=SOURCE_DATASET,
            repo_type="dataset",
            filename=TOOLHOP_DATA_FILE,
            revision=TOOLHOP_REVISION,
        ),
    )
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise BuildError("ToolHop data file must contain a JSON array")
    rows: list[JsonObject] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise BuildError(f"ToolHop row {index} is not an object")
        rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Iterable[JsonObject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _import_roots(source: str) -> set[str]:
    roots: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _first_function_name(source: str) -> str | None:
    names = function_names_from_source(source)
    return names[0] if names else None


def _tool_names(row: Mapping[str, JsonValue]) -> list[str]:
    tools = row.get("tools")
    if not isinstance(tools, dict):
        return []
    names: list[str] = []
    for tool in tools.values():
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            names.append(tool["name"])
    return names


def _str_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _required_str(row: Mapping[str, JsonValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{key} must be a non-empty string")
    return value


def _category(domain: str) -> str:
    return " ".join(domain.casefold().split()) or "uncategorized"


def _source_id(row: Mapping[str, JsonValue]) -> int | str:
    value = row.get("source_id")
    if isinstance(value, int | str) and not isinstance(value, bool):
        return value
    return _required_str(row, "id")


def _stratum(row: Mapping[str, JsonValue]) -> str:
    return f"{_required_str(row, 'category')}|hop={int(row['hop_count'])}"


def _stable_digest(namespace: str, source_id: str, sample_seed: str) -> str:
    return hashlib.sha256(f"{sample_seed}:{namespace}:{source_id}".encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
