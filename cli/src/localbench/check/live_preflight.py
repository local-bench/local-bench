from __future__ import annotations

from collections.abc import Sequence

from localbench.check.budget import HEADROOM, THINK_BUDGET, generation_parameters
from localbench.check.live_http import (
    LiveHttpConfig,
    live_prompt_character_count,
    render_live_prompt,
    tokenize_live_prompt,
)
from localbench.check.live_runner_types import LiveItem
from localbench.check.types import CheckError, ConstructionDefect
from localbench.prompt_rendering import PromptRenderer

PREFLIGHT_LONGEST_ITEMS = 10
LCE_CONTEXT_TOKENS = 32768


def run_fit_preflight(
    items: Sequence[LiveItem],
    http_config: LiveHttpConfig,
    renderer: PromptRenderer,
) -> None:
    for item in select_fit_preflight_items(items):
        prompt = render_live_prompt(item.module, item.source, renderer)
        prompt_tokens = tokenize_live_prompt(http_config, prompt)
        params = generation_parameters(item.module)
        answer_budget = params.get("answer_budget_tokens")
        if not isinstance(answer_budget, int):
            raise CheckError(f"module {item.module!r} has invalid generation parameters")
        total = prompt_tokens + THINK_BUDGET + answer_budget + HEADROOM
        if total > LCE_CONTEXT_TOKENS:
            detail = (
                f"prompt fit preflight failed for {item.item_id}: "
                f"{prompt_tokens} + {THINK_BUDGET} + {answer_budget} + {HEADROOM} "
                f"= {total} > {LCE_CONTEXT_TOKENS}"
            )
            raise ConstructionDefect("prompt-fit", detail)


def select_fit_preflight_items(items: Sequence[LiveItem]) -> tuple[LiveItem, ...]:
    ordered = sorted(
        items,
        key=lambda item: (-live_prompt_character_count(item.module, item.source), item.item_id),
    )
    selected = ordered[:PREFLIGHT_LONGEST_ITEMS]
    selected_ids = {item.item_id for item in selected}
    needles = sorted(
        (
            item
            for item in items
            if item.source.get("category") == "long-context-needle" and item.item_id not in selected_ids
        ),
        key=lambda item: item.item_id,
    )
    return (*selected, *needles)
