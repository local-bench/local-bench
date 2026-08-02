from __future__ import annotations

from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError

THINK_BUDGET: Final = 4096
HEADROOM: Final = 256
ANSWER_BUDGETS: Final = {
    "knowledge": 512,
    "instruction": 1024,
    "math": 1536,
    "coding": 2048,
    "tools-single": 512,
    "tools-stateful": 512,
    "sanity-gates": 512,
}


def generation_parameters(module: str) -> JsonObject:
    answer_budget = ANSWER_BUDGETS.get(module)
    if answer_budget is None:
        raise CheckError(f"no locked answer budget for module {module!r}")
    return {
        "answer_budget_tokens": answer_budget,
        "headroom_tokens": HEADROOM,
        "max_tokens": THINK_BUDGET + answer_budget + HEADROOM,
        "seed": 1234,
        "temperature": 0,
        "think_budget_tokens": THINK_BUDGET,
    }


def normalize_generation(
    *,
    text: str,
    generated_token_ids: list[int],
    finish_reason: str,
    think_open: str,
    think_close: str,
) -> JsonObject:
    has_open = think_open in text
    has_close = think_close in text
    forced = has_open and not has_close and len(generated_token_ids) >= THINK_BUDGET
    protocol_flag: str | None = None
    normalized = text
    if forced:
        normalized = f"{text}{think_close}"
        protocol_flag = "think-budget-exhausted"
    elif not has_open and not has_close:
        protocol_flag = "think-markers-absent"
    elif has_open != has_close:
        protocol_flag = "think-markers-malformed"
    token_values: list[JsonValue] = [token_id for token_id in generated_token_ids]
    return {
        "finish_reason": finish_reason,
        "forced_close": forced,
        "generated_token_ids": token_values,
        "protocol_flag": protocol_flag,
        "rerun": False,
        "text": normalized,
    }
