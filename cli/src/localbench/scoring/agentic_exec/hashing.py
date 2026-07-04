"""Stable hashing for agentic transcripts and scorecard identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from localbench._types import JsonObject, JsonValue
from localbench.scoring.agentic_exec import AXIS_ID
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.observations import normalize_json

PROTOCOL_VERSION: Final = "localbench-json-action-v0"
ADAPTER_VERSION: Final = "stub-appworld-lite-v0"
VERIFIER_VERSION: Final = "stub-final-state-v0"
APPWORLD_VERSION: Final = "stub-appworld-api-shape-v0"


@dataclass(frozen=True, slots=True)
class ScorecardTaskIdentity:
    """Task identity fields that enter the scorecard hash."""

    task_id: str
    family: str
    band: str


def transcript_sha256(transcript: list[JsonObject]) -> str:
    """Return SHA-256 of the canonical JSON transcript."""
    return _sha256_json(transcript)


def scorecard_identity_hash(
    *,
    config: AgenticExecConfig,
    tasks: tuple[ScorecardTaskIdentity, ...],
) -> str:
    """Hash the scaffold identity that makes scores comparable."""
    payload: JsonObject = {
        "axis_id": AXIS_ID,
        "protocol_version": PROTOCOL_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "appworld_version": APPWORLD_VERSION,
        "config": _config_payload(config),
        "tasks": [_task_payload(task) for task in tasks],
    }
    return _sha256_json(payload)


def _sha256_json(value: JsonValue) -> str:
    blob = json.dumps(
        normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _config_payload(config: AgenticExecConfig) -> JsonObject:
    return {
        "max_tool_calls": config.max_tool_calls,
        "max_turns": config.max_turns,
        "token_budget_per_turn": config.token_budget_per_turn,
        "token_budget_per_task": config.token_budget_per_task,
        "context_window": config.context_window,
        "temperature": config.temperature,
        "top_k": config.top_k,
        "top_p": config.top_p,
        "min_p": config.min_p,
        "max_observation_chars_per_tool": config.max_observation_chars_per_tool,
        "max_api_doc_chars_per_call": config.max_api_doc_chars_per_call,
        "max_wall_time_per_task_seconds": config.max_wall_time_per_task_seconds,
        "parse_retries": config.parse_retries,
    }


def _task_payload(task: ScorecardTaskIdentity) -> JsonObject:
    return {"task_id": task.task_id, "family": task.family, "band": task.band}
