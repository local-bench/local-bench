from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass

from localbench._types import JsonObject, JsonValue
from localbench.check.budget import generation_parameters
from localbench.check.execution import collect_lce_identity
from localbench.check.live_coding import require_coding_consent, verify_coding_rows
from localbench.check.live_http import (
    LiveHttpConfig,
    build_live_prompt_renderer,
    generate_live_item,
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
from localbench.check.types import CheckError


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
