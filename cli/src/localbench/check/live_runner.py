from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass

from localbench._types import JsonObject, JsonValue
from localbench.check.budget import HEADROOM, THINK_BUDGET, generation_parameters
from localbench.check.execution import collect_lce_identity
from localbench.check.live_coding import require_coding_consent, verify_coding_rows
from localbench.check.live_http import (
    LiveHttpConfig,
    build_live_prompt_renderer,
    generate_live_item,
    live_prompt_character_count,
    render_live_prompt,
    tokenize_live_prompt,
)
from localbench.check.live_server import (
    InfrastructureFailure,
    LiveRunnerConfig,
    ServerController as ServerController,
    ServerFactory,
    owned_server_factory,
    run_server_cycle,
    server_port,
)
from localbench.prompt_rendering import PromptRenderer
from localbench.check.stateful_live import run_stateful_item
from localbench.check.types import CheckError, ConstructionDefect

PREFLIGHT_LONGEST_ITEMS = 10
LCE_CONTEXT_TOKENS = 32768


@dataclass(frozen=True, slots=True)
class LiveItem:
    item_id: str
    module: str
    source: JsonObject


@dataclass(frozen=True, slots=True)
class LiveExecutionResult:
    items: list[JsonObject]
    execution: JsonObject


def run_live_items(
    config: LiveRunnerConfig,
    items: Sequence[LiveItem],
    *,
    server_factory: ServerFactory | None = None,
) -> LiveExecutionResult:
    require_coding_consent(items, allow_untrusted_code=config.allow_untrusted_code)
    if not config.model_file.is_file() or not config.server_bin.is_file():
        missing = config.model_file if not config.model_file.is_file() else config.server_bin
        raise InfrastructureFailure("missing-file", f"required live-run file does not exist: {missing.resolve()}")
    port = server_port(config)
    api_key = secrets.token_urlsafe(32)
    launch = server_factory or owned_server_factory
    first = run_server_cycle(
        config,
        port=port,
        api_key=api_key,
        launch=launch,
        execute=lambda http_config, props: _execute_items(items, http_config, props),
    )
    try:
        verify_coding_rows(first.rows, allow_untrusted_code=config.allow_untrusted_code)
    except CheckError as error:
        raise InfrastructureFailure("coding-sandbox", str(error)) from error
    starts: list[JsonValue] = [first.start]
    canaries = tuple(item for item in items if item.source.get("category") == "determinism")
    if canaries:
        repeated = run_server_cycle(
            config,
            port=port,
            api_key=api_key,
            launch=launch,
            execute=lambda http_config, props: _execute_items(canaries, http_config, props),
        )
        starts.append(repeated.start)
        repeated_by_id = {row["item_id"]: row["candidate"] for row in repeated.rows}
        for row in first.rows:
            item_id = row.get("item_id")
            if isinstance(item_id, str) and item_id in repeated_by_id:
                row["candidate_repeat"] = repeated_by_id[item_id]
    backend = first.props.get("backend")
    driver = first.props.get("driver_version")
    execution = collect_lce_identity(
        config.server_bin.parent,
        backend=backend if isinstance(backend, str) else "unknown",
        props=first.props,
        driver=driver if isinstance(driver, str) else "unknown",
    )
    execution.update(
        {
            "runner": "llama-server-live",
            "server_starts": starts,
            "streaming": True,
        }
    )
    return LiveExecutionResult(first.rows, execution)


def _execute_items(
    items: Sequence[LiveItem],
    http_config: LiveHttpConfig,
    props: JsonObject,
) -> list[JsonObject]:
    renderer = build_live_prompt_renderer(http_config, props)
    _run_fit_preflight(items, http_config, renderer)
    return [
        {
            "candidate": _generate_runtime_item(http_config, item, renderer),
            "generation_parameters": generation_parameters(item.module),
            "item_id": item.item_id,
            "module": item.module,
            "source_item": item.source,
        }
        for item in items
    ]


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


def _run_fit_preflight(
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


def _generate_runtime_item(
    http_config: LiveHttpConfig,
    item: LiveItem,
    renderer: PromptRenderer,
) -> JsonObject:
    def generate(source: JsonObject) -> JsonObject:
        return generate_live_item(
            http_config,
            module=item.module,
            item_id=item.item_id,
            source=source,
            prompt_renderer=renderer,
        )

    if item.module == "tools-stateful":
        return run_stateful_item(item.source, generate)
    return generate(item.source)
