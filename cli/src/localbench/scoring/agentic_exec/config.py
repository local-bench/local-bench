"""Configuration for the AppWorld-lite agentic execution harness."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgenticExecConfig:
    """Runtime and protocol budgets for one agentic task."""

    max_tool_calls: int = 11
    max_turns: int = 12
    token_budget_per_turn: int = 768
    token_budget_per_task: int = 6144
    context_window: int = 32_768
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    min_p: float = 0.0
    max_observation_chars_per_tool: int = 12_000
    max_api_doc_chars_per_call: int = 8_000
    max_wall_time_per_task_seconds: int = 240
    parse_retries: int = 1
