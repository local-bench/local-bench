from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from localbench._types import JsonValue
from localbench.scoring.agentic_exec import funnel
from localbench.submissions.canon import canonical_json_hash


def ordered_task_ids_sha256(task_ids: list[str] | tuple[str, ...]) -> str:
    """Hash the canonical JSON array of exact task IDs in execution order."""
    return canonical_json_hash(list(task_ids))


def selection_recipe_sha256(*, split: str, seed: int, selection_version: str) -> str:
    """Hash selection inputs only; task IDs and mutable result metadata are excluded."""
    return canonical_json_hash(
        {
            "selection_version": selection_version,
            "seed": seed,
            "split": split,
        },
    )


def semantic_task_sha256(task_contents: Mapping[str, JsonValue]) -> str:
    """Hash canonical task meaning independently of upstream enumeration order."""
    tasks = [
        {"task_id": task_id, "content": task_contents[task_id]}
        for task_id in sorted(task_contents)
    ]
    return canonical_json_hash(tasks)


def load_semantic_task_contents(
    task_ids: list[str] | tuple[str, ...],
    *,
    root: Path | None = None,
) -> dict[str, JsonValue]:
    """Read instructions, initial DB state, and evaluator criteria for exact task IDs."""
    tasks_root = (root or appworld_root()) / "data" / "tasks"
    try:
        return {
            task_id: _semantic_task_content(tasks_root / task_id)
            for task_id in sorted(task_ids)
        }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        from localbench.scoring.agentic_exec.execution_contract import TaskIdentityDriftError

        raise TaskIdentityDriftError(
            "semantic_task_contents", "readable canonical task data", type(exc).__name__
        ) from exc


def _semantic_task_content(task_dir: Path) -> JsonValue:
    specs = _json_file(task_dir / "specs.json")
    dbs = {
        path.name: _jsonl_file(path)
        for path in sorted((task_dir / "dbs").glob("*.jsonl"), key=lambda item: item.name)
    }
    ground_truth_dir = task_dir / "ground_truth"
    criteria: dict[str, JsonValue] = {
        path.name: _json_file(path)
        for path in sorted(ground_truth_dir.glob("*.json"), key=lambda item: item.name)
    }
    evaluation_path = ground_truth_dir / "evaluation.py"
    criteria["evaluation.py"] = _canonical_text(evaluation_path.read_text(encoding="utf-8"))
    return {
        "instructions": specs,
        "setup_state": dbs,
        "evaluation_criteria": criteria,
    }


def _json_file(path: Path) -> JsonValue:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    return value


def _jsonl_file(path: Path) -> JsonValue:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _canonical_text(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).rstrip("\n") + "\n"


def load_split_ids(split: str) -> list[str]:
    from appworld import load_task_ids

    return list(load_task_ids(split))


def appworld_root() -> Path:
    root = os.environ.get("APPWORLD_ROOT")
    if not root:
        raise RuntimeError("APPWORLD_ROOT is not set (needed to read task metadata for strata).")
    return Path(root)


def load_metadata(task_ids: list[str]) -> dict[str, funnel.TaskMeta]:
    root = appworld_root()
    out: dict[str, funnel.TaskMeta] = {}
    for task_id in task_ids:
        meta_path = root / "data" / "tasks" / task_id / "ground_truth" / "metadata.json"
        difficulty: int | None = None
        primary: str | None = None
        num_calls: int | None = None
        try:
            doc = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                difficulty = coerce_int(doc.get("difficulty"))
                num_calls = coerce_int(doc.get("num_api_calls"))
                primary = primary_app(doc)
        except (OSError, ValueError, TypeError):
            pass
        out[task_id] = funnel.TaskMeta(
            task_id=task_id,
            difficulty=difficulty,
            primary_app=primary,
            num_api_calls=num_calls,
        )
    return out


def coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def primary_app(doc: Mapping[str, object]) -> str | None:
    for key in ("primary_app", "app", "app_name"):
        value = doc.get(key)
        if isinstance(value, str) and value:
            return value
    apps = doc.get("apps") or doc.get("required_apps")
    if isinstance(apps, list) and apps and isinstance(apps[0], str):
        return sorted(apps)[0]
    return None


def build_subset(
    stage: funnel.Stage,
    *,
    wide_smoke: bool,
    with_metadata: bool,
) -> funnel.SubsetSpec:
    needed_split = {
        funnel.Stage.SMOKE: funnel.SMOKE_SPLIT,
        funnel.Stage.LITE: funnel.LITE_SPLIT,
        funnel.Stage.SCORED: funnel.SCORED_SPLIT,
    }[stage]
    task_ids = load_split_ids(needed_split)
    metadata = load_metadata(task_ids) if with_metadata else None
    return funnel.subset_for_stage(
        stage,
        {needed_split: task_ids},
        metadata=metadata,
        wide_smoke=wide_smoke,
    )


def subset_from_task_ids(
    task_ids: list[str],
    *,
    canonical_task_ids: list[str],
) -> funnel.SubsetSpec:
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("supplied agentic task IDs must be unique")
    if len(canonical_task_ids) != len(set(canonical_task_ids)):
        raise ValueError("canonical scored task IDs must be unique")
    canonical = set(canonical_task_ids)
    unknown = [task_id for task_id in task_ids if task_id not in canonical]
    if unknown:
        raise ValueError(f"supplied agentic task IDs are outside the canonical scored set: {unknown}")
    return funnel.SubsetSpec(
        name="injected",
        split="injected",
        size=len(task_ids),
        seed=0,
        task_ids=tuple(task_ids),
    )
