from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from localbench.scoring.agentic_exec import funnel


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
