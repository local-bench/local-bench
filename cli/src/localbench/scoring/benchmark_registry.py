from __future__ import annotations

from collections.abc import Container
from dataclasses import dataclass
from typing import Final, Literal

ModuleLane = Literal["http", "agentic", "exec"]
ModuleRole = Literal["headline", "candidate"]


@dataclass(frozen=True, slots=True)
class BenchmarkModule:
    key: str
    display: str
    axis_keys: tuple[str, ...]
    default_benches: tuple[str, ...]
    opt_in_benches: tuple[str, ...]
    lane: ModuleLane
    role: ModuleRole
    target_minutes: str


OUT_OF_BAND_DEFAULT_BENCHES: Final = frozenset({"appworld_c"})

BENCHMARK_MODULES: Final[tuple[BenchmarkModule, ...]] = (
    BenchmarkModule(
        "core_text",
        "Core text",
        ("knowledge", "instruction_following"),
        ("mmlu_pro", "ifbench"),
        (),
        "http",
        "headline",
        "20-60",
    ),
    BenchmarkModule(
        "math",
        "Math",
        ("math",),
        ("olymmath_hard", "amo"),
        (),
        "http",
        "headline",
        "15-45",
    ),
    BenchmarkModule(
        "tool_calling",
        "Tool calling",
        ("tool_calling",),
        ("tc_json_v1",),
        (),
        "http",
        "headline",
        "10-30",
    ),
    BenchmarkModule(
        "coding",
        "Coding",
        ("coding",),
        ("bigcodebench_hard",),
        ("lcb",),
        "http",
        "headline",
        "15-45",
    ),
    BenchmarkModule(
        "agentic",
        "Agentic",
        ("agentic",),
        ("appworld_c",),
        (),
        "agentic",
        "headline",
        "30-90",
    ),
    BenchmarkModule(
        "long_context",
        "Long context",
        ("long_context",),
        (),
        ("ruler_32k",),
        "http",
        "candidate",
        "10-30",
    ),
)


def headline_modules() -> tuple[BenchmarkModule, ...]:
    return tuple(module for module in BENCHMARK_MODULES if module.role == "headline")


def scored_default_benches(available_benches: Container[str] | None = None) -> tuple[str, ...]:
    benches: list[str] = []
    for module in headline_modules():
        for bench in module.default_benches:
            if available_benches is None or bench in available_benches or bench in OUT_OF_BAND_DEFAULT_BENCHES:
                benches.append(bench)
    return tuple(benches)


def module_for_axis(axis_key: str) -> BenchmarkModule | None:
    for module in BENCHMARK_MODULES:
        if axis_key in module.axis_keys:
            return module
    return None
