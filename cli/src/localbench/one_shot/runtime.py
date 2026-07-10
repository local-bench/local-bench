from __future__ import annotations

import argparse
from pathlib import Path

from localbench._types import JsonObject


def print_scorecard(record: JsonObject) -> None:
    scores = record.get("scores")
    if isinstance(scores, dict) and isinstance(
        scores.get("headline_score"), int | float
    ):
        print(f"scorecard headline {float(scores['headline_score']):.3f}")
    else:
        print("scorecard written")


def run_root(args: argparse.Namespace) -> Path:
    resume = getattr(args, "resume", None)
    if isinstance(resume, Path):
        return resume
    out = getattr(args, "out", None)
    if isinstance(out, Path):
        return out
    requested_model = str(getattr(args, "one_shot_model", "model"))
    return Path("runs") / "bench" / requested_model.replace("/", "__")
