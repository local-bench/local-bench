"""AppWorld-lite adapter boundary for the agentic execution harness."""

from __future__ import annotations

from dataclasses import dataclass

from localbench._types import JsonValue
from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.observations import Observation, canonical_observation
from localbench.scoring.agentic_exec.stub_appworld import (
    StubAppWorld,
    StubEvalResult,
    StubToolError,
)
from localbench.scoring.agentic_exec.types import (
    FailureReason,
    FinalAnswerAction,
    ToolCallAction,
)


@dataclass(frozen=True, slots=True)
class LoadedTask:
    """Task metadata needed by the harness loop."""

    task_id: str
    instruction: str
    family: str
    band: str
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """Result of one whitelisted or rejected tool call."""

    observation: Observation
    failure_reason: FailureReason | None


@dataclass(frozen=True, slots=True)
class CompletionRecord:
    """Task completion and final verifier result."""

    task_id: str
    answer: JsonValue
    success: bool
    eval_result: StubEvalResult


class AppWorldLiteAdapter:
    """Adapter between the JSON protocol and AppWorld-like API execution."""

    def __init__(self, world: StubAppWorld, config: AgenticExecConfig) -> None:
        # SEAM: real AppWorld wires in here by replacing StubAppWorld with the real task world.
        self._world = world
        self._config = config

    def load_task(self, task_id: str) -> LoadedTask:
        """Load a task from the backing AppWorld-like substrate."""
        # SEAM: real AppWorld task loading wires in here.
        spec = self._world.load_task(task_id)
        return LoadedTask(
            task_id=spec.task_id,
            instruction=spec.instruction,
            family=spec.family,
            band=spec.band,
            allowed_tools=spec.allowed_tools,
        )

    def execute_tool_call(self, task: LoadedTask, action: ToolCallAction) -> ToolExecutionResult:
        """Whitelist-check and execute one API call."""
        if action.tool not in task.allowed_tools:
            observation = canonical_observation(
                {"error": FailureReason.FORBIDDEN_TOOL.value, "tool": action.tool},
                char_limit=self._config.max_observation_chars_per_tool,
            )
            return ToolExecutionResult(
                observation=observation,
                failure_reason=FailureReason.FORBIDDEN_TOOL,
            )

        # SEAM: real AppWorld whitelisted API dispatch wires in here.
        try:
            raw_observation = self._world.call_api(action.tool, action.arguments)
        except StubToolError as exc:
            observation = canonical_observation(
                {"error": FailureReason.TOOL_ERROR.value, "message": exc.message},
                char_limit=self._config.max_observation_chars_per_tool,
            )
            return ToolExecutionResult(
                observation=observation,
                failure_reason=FailureReason.TOOL_ERROR,
            )

        return ToolExecutionResult(
            observation=canonical_observation(
                raw_observation,
                char_limit=self._config.max_observation_chars_per_tool,
            ),
            failure_reason=None,
        )

    def final_answer(self, task: LoadedTask, action: FinalAnswerAction) -> CompletionRecord:
        """Complete the task and run deterministic final-state verification."""
        # SEAM: real AppWorld supervisor.complete_task/final-state verifier wires in here.
        eval_result = self._world.verify(task.task_id, action.answer)
        return CompletionRecord(
            task_id=task.task_id,
            answer=action.answer,
            success=eval_result.passed and not eval_result.collateral_damage,
            eval_result=eval_result,
        )
