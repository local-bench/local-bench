from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
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
from localbench.check.live_preflight import run_fit_preflight, select_fit_preflight_items as select_fit_preflight_items
from localbench.check.live_runner_types import LiveItem as LiveItem
from localbench.check.live_server import (
    InfrastructureFailure,
    LiveRunnerConfig,
    ServerCycleOptions,
    ServerController as ServerController,
    ServerFactory,
    owned_server_factory,
    run_server_cycle,
    server_port,
)
from localbench.check.stateful_live import run_stateful_item
from localbench.check.types import CheckError
from localbench.prompt_rendering import PromptRenderer


@dataclass(frozen=True, slots=True)
class LiveExecutionResult:
    items: list[JsonObject]
    execution: JsonObject


RowSink = Callable[[JsonObject], None]
ExecutionSink = Callable[[JsonObject], None]


@dataclass(frozen=True, slots=True)
class LiveRunOptions:
    completed_rows: tuple[JsonObject, ...] = ()
    previous_execution: JsonObject | None = None
    row_sink: RowSink | None = None
    execution_sink: ExecutionSink | None = None
    server_factory: ServerFactory | None = None


def run_live_items(
    config: LiveRunnerConfig,
    items: Sequence[LiveItem],
    options: LiveRunOptions = LiveRunOptions(),
) -> LiveExecutionResult:
    require_coding_consent(items, allow_untrusted_code=config.allow_untrusted_code)
    if not config.model_file.is_file() or not config.server_bin.is_file():
        missing = config.model_file if not config.model_file.is_file() else config.server_bin
        raise InfrastructureFailure("missing-file", f"required live-run file does not exist: {missing.resolve()}")
    port = server_port(config)
    api_key = secrets.token_urlsafe(32)
    launch = options.server_factory or owned_server_factory
    rows_by_id = _completed_by_id(options.completed_rows)
    pending = tuple(item for item in items if item.item_id not in rows_by_id)
    starts = _server_starts(options.previous_execution)
    execution = options.previous_execution

    def ready(props: JsonObject, start: JsonObject) -> None:
        nonlocal execution
        starts.append(start)
        execution = _execution_identity(config, props, starts)
        if options.execution_sink is not None:
            options.execution_sink(execution)

    if pending or not rows_by_id:
        first = run_server_cycle(
            config,
            ServerCycleOptions(
                port=port,
                api_key=api_key,
                launch=launch,
                ready=ready,
                execute=lambda http_config, props: _execute_items(
                    pending,
                    http_config,
                    props,
                    options.row_sink,
                ),
            ),
        )
        try:
            verify_coding_rows(first.rows, allow_untrusted_code=config.allow_untrusted_code)
        except CheckError as error:
            raise InfrastructureFailure("coding-sandbox", str(error)) from error
        rows_by_id.update(_completed_by_id(first.rows))

    repeat_pending = tuple(
        item
        for item in items
        if item.source.get("category") == "determinism"
        and "candidate_repeat" not in rows_by_id[item.item_id]
    )
    if repeat_pending:
        def persist_repeat(row: JsonObject) -> None:
            item_id = row.get("item_id")
            repeated = row.get("candidate")
            if not isinstance(item_id, str) or not isinstance(repeated, dict):
                raise CheckError("determinism repeat row is invalid")
            merged = dict(rows_by_id[item_id])
            merged["candidate_repeat"] = repeated
            rows_by_id[item_id] = merged
            if options.row_sink is not None:
                options.row_sink(merged)

        _ = run_server_cycle(
            config,
            ServerCycleOptions(
                port=port,
                api_key=api_key,
                launch=launch,
                ready=ready,
                execute=lambda http_config, props: _execute_items(
                    repeat_pending,
                    http_config,
                    props,
                    persist_repeat,
                ),
            ),
        )
    if execution is None:
        raise CheckError("live execution identity is missing")
    return LiveExecutionResult([rows_by_id[item.item_id] for item in items], execution)


def _execute_items(
    items: Sequence[LiveItem],
    http_config: LiveHttpConfig,
    props: JsonObject,
    row_sink: RowSink | None,
) -> list[JsonObject]:
    renderer = build_live_prompt_renderer(http_config, props)
    run_fit_preflight(items, http_config, renderer)
    rows: list[JsonObject] = []
    for item in items:
        row: JsonObject = {
            "candidate": _generate_runtime_item(http_config, item, renderer),
            "generation_parameters": generation_parameters(item.module),
            "item_id": item.item_id,
            "module": item.module,
            "source_item": item.source,
        }
        rows.append(row)
        if row_sink is not None:
            row_sink(row)
    return rows


def _completed_by_id(rows: Sequence[JsonObject]) -> dict[str, JsonObject]:
    completed: dict[str, JsonObject] = {}
    for row in rows:
        item_id = row.get("item_id")
        candidate = row.get("candidate")
        if isinstance(item_id, str) and isinstance(candidate, dict):
            completed[item_id] = row
    return completed


def _server_starts(execution: JsonObject | None) -> list[JsonObject]:
    if execution is None:
        return []
    starts = execution.get("server_starts")
    if not isinstance(starts, list):
        return []
    return [start for start in starts if isinstance(start, dict)]


def _execution_identity(
    config: LiveRunnerConfig,
    props: JsonObject,
    starts: list[JsonObject],
) -> JsonObject:
    backend = props.get("backend")
    driver = props.get("driver_version")
    execution = collect_lce_identity(
        config.server_bin.parent,
        backend=backend if isinstance(backend, str) else "unknown",
        props=props,
        driver=driver if isinstance(driver, str) else "unknown",
    )
    start_values: list[JsonValue] = [start for start in starts]
    execution.update(
        {
            "runner": "llama-server-live",
            "server_starts": start_values,
            "streaming": True,
        }
    )
    return execution


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
