from __future__ import annotations

from typing import Final

from localbench._types import JsonObject
from localbench.scoring.benchmark_registry import scored_default_benches

SCORED_DEFAULT_BENCHES: Final[tuple[str, ...]] = scored_default_benches()


def resolve_run_benches(bench_arg: str, suite: JsonObject) -> list[str]:
    benches = suite.get("benches")
    if not isinstance(benches, dict):
        return []
    choice = bench_arg.strip()
    if choice == "all":
        return list(scored_default_benches(benches))
    return [name.strip() for name in choice.split(",") if name.strip()]
