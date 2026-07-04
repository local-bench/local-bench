"""Budgets + knobs for the Protocol C agent loop (LOCKED design constants).

Distinct from the older ``config.AgenticExecConfig`` (which encodes the rejected
one-JSON-object-per-turn Protocol A: ``max_tool_calls=11``/``max_turns=12``). Protocol C is
code-as-action with a **turn cap of 24** (oracle-calibrated on dev only), a per-turn output
token cap, observation truncation, and the determinism contract.

Pure config: no AppWorld, no sandbox, no model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from localbench.scoring.agentic_exec.model_client import GenerationParams


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Per-task Protocol C budgets. Defaults are the LOCKED values."""

    # LOCKED: turn cap = 24 (oracle: 20-24; cap prevents runaway, must not decide a weak
    # model's one extra recovery turn). cap_exceeded is a normal, reported failure reason.
    # Calibrated on dev ONLY; never tune on test splits.
    max_turns: int = 24

    # Per-turn output token cap. Surfaced to the client via GenerationParams; a turn that
    # hits it returns finish_reason="length" and is treated as a (recoverable) format
    # failure for that turn. Generous: real Protocol C blocks are short (median ~5 blocks).
    max_output_tokens_per_turn: int = 1024

    # Observation truncation: the captured stdout fed back to the model is hard-capped to
    # this many characters (keeps a single chatty print from blowing the context window and
    # keeps observation canonicalisation bounded). Truncations are counted as a diagnostic.
    max_observation_chars: int = 8_000

    # Chat history window used by Protocol C. The loop keeps system/user anchors plus a fixed
    # number of recent turn/observation messages derived from this budget.
    context_window: int = 32_768

    # Determinism contract (LOCKED): greedy decoding, fixed seed. Passed to the client each
    # turn; the scripted client ignores it, a real client honours it.
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 0

    # Wall-clock guard intended for a single model .complete() call. This is currently not
    # enforced by the loop; the benchmark-level per_task_timeout_s below is the hard stop.
    model_call_timeout_s: float = 120.0

    # Hard wall-clock watchdog for one complete task attempt: sandbox setup, model loop, finalize,
    # and teardown. This bounds hangs outside the per-block sandbox wall timeout.
    per_task_timeout_s: float = 360.0
    attester_key_path: Path | None = field(default_factory=lambda: _env_path("LOCALBENCH_ATTESTER_KEY_FILE"))
    attestation_run_id: str = "appworld_c"

    def generation_params(self) -> GenerationParams:
        """The decoding intent handed to the model client every turn."""
        return GenerationParams(
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
            max_output_tokens=self.max_output_tokens_per_turn,
        )


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None
