from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Final

from localbench._types import JsonObject, JsonValue

_SEED: Final = 20260802
_RHO_VALUES: Final = (0.03, 0.06, 0.10, 0.20)
_POWER_Z: Final = NormalDist().inv_cdf(0.80)


def build_mde_artifact(manifest: JsonObject, *, simulations: int = 2_000) -> JsonObject:
    if simulations < 100:
        raise ValueError("MDE simulation requires at least 100 repetitions")
    counts = _area_counts(manifest)
    rng = random.Random(_SEED)
    maxima = [max(abs(rng.gauss(0.0, 1.0)) for _ in counts) for _ in range(simulations)]
    critical = _quantile(maxima, 0.95)
    rows: list[JsonValue] = []
    for area, n in counts.items():
        for disagreement in _RHO_VALUES:
            rows.append(
                {
                    "area": area,
                    "closed_form_pp": 100.0 * 2.8 * math.sqrt(disagreement / n),
                    "disagreement_rate": disagreement,
                    "n": n,
                    "simulation_mde_pp": 100.0 * (critical + _POWER_Z) * math.sqrt(disagreement / n),
                }
            )
    return {
        "approximation_formula": "2.8 * sqrt(disagreement_rate / n)",
        "approximation_label": "unadjusted marginal approximation",
        "bootstrap_seed": _SEED,
        "confidence": 0.95,
        "critical_value": critical,
        "manifest_edition": _required_str(manifest, "edition"),
        "power": 0.80,
        "procedure": "five-area two-sided simultaneous max-statistic Monte Carlo normal approximation",
        "published_mde_label": "simulation-derived",
        "rows": rows,
        "schema_version": "localbench-check-mde-v1",
        "simulations": simulations,
    }


def _area_counts(manifest: JsonObject) -> dict[str, int]:
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise ValueError("manifest has no module records")
    counts: dict[str, int] = {}
    tools = 0
    for module in modules:
        if not isinstance(module, dict):
            continue
        name = module.get("name")
        items = module.get("items")
        if not isinstance(name, str) or not isinstance(items, list) or name == "sanity-gates":
            continue
        if name in {"tools-single", "tools-stateful"}:
            tools += len(items)
        elif name in {"knowledge", "instruction", "coding", "math"}:
            counts[name] = len(items)
    counts["tools"] = tools
    expected = {"knowledge", "instruction", "coding", "math", "tools"}
    if set(counts) != expected or any(value <= 0 for value in counts.values()):
        raise ValueError("manifest does not define all five scored areas")
    return {area: counts[area] for area in ("knowledge", "instruction", "coding", "math", "tools")}


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _required_str(document: JsonObject, key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest field {key!r} is missing")
    return value
