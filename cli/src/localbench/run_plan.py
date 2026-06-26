from __future__ import annotations

from typing import Final

from localbench._types import JsonObject

SCORED_DEFAULT_BENCHES: Final[tuple[str, ...]] = ("mmlu_pro", "ifbench", "tc_json_v1")


def resolve_run_benches(bench_arg: str, suite: JsonObject) -> list[str]:
    benches = suite.get("benches")
    if not isinstance(benches, dict):
        return []
    choice = bench_arg.strip()
    if choice == "all":
        return list(SCORED_DEFAULT_BENCHES)
    return [name.strip() for name in choice.split(",") if name.strip()]
