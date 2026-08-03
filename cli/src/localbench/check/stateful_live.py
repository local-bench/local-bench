from __future__ import annotations

import json
from collections.abc import Callable

from localbench._types import JsonObject, JsonValue
from localbench.check.types import CheckError
from localbench.checkset.models import ChecksetBuildError
from localbench.checkset.stateful import simulate_trajectory

GenerateTurn = Callable[[JsonObject], JsonObject]


def run_stateful_item(source: JsonObject, generate_turn: GenerateTurn) -> JsonObject:
    turn_budget = source.get("turn_budget")
    initial_state = source.get("initial_state")
    canonical = source.get("canonical_final_state")
    inspect_tool = source.get("inspect_tool")
    inspect_output = source.get("inspect_output")
    if not isinstance(turn_budget, dict) or not isinstance(initial_state, dict) or not isinstance(canonical, dict):
        raise CheckError("stateful live item is missing its fixed-turn simulator contract")
    max_turns = turn_budget.get("max_turns")
    answer_budget = turn_budget.get("answer_budget_tokens_per_turn")
    semantics = turn_budget.get("semantics")
    if (
        not isinstance(max_turns, int)
        or max_turns < 2
        or answer_budget != 512
        or semantics != "one tool call per assistant turn; final answer consumes the last turn"
    ):
        raise CheckError("stateful live item has an invalid fixed-turn budget")
    calls: list[JsonObject] = []
    transcript: list[JsonValue] = []
    generations: list[JsonObject] = []
    state = dict(initial_state)
    protocol_flag: str | None = None
    for _turn in range(max_turns - 1):
        turn_source = dict(source)
        turn_source["prompt"] = _turn_prompt(source, state, transcript)
        generation = generate_turn(turn_source)
        generations.append(generation)
        raw_calls = generation.get("parsed_tool_calls")
        if not isinstance(raw_calls, list) or len(raw_calls) != 1 or not isinstance(raw_calls[0], dict):
            protocol_flag = "stateful-single-call-required"
            break
        call = dict(raw_calls[0])
        calls.append(call)
        transcript_row: JsonObject = {"call": call}
        if call.get("name") == inspect_tool and isinstance(inspect_output, dict):
            transcript_row["result"] = dict(inspect_output)
        transcript.append(transcript_row)
        try:
            state = simulate_trajectory(source, calls)
        except ChecksetBuildError:
            protocol_flag = "stateful-invalid-transition"
            break
        if state == canonical:
            final_source = dict(source)
            final_source["prompt"] = _final_prompt(source, state, transcript)
            final_source["stateful_final"] = True
            generations.append(generate_turn(final_source))
            break
    else:
        protocol_flag = "stateful-turn-budget-exhausted"
    return _combine_generations(generations, calls, protocol_flag)


def _turn_prompt(source: JsonObject, state: JsonObject, transcript: list[JsonValue]) -> str:
    prompt = source.get("prompt")
    if not isinstance(prompt, str):
        raise CheckError("stateful live item prompt is missing")
    return (
        f"{prompt}\nCurrent state: {_canonical(state)}\n"
        f"Prior tool transcript: {_canonical(transcript)}\n"
        "Return exactly one next tool call in the declared canonical JSON format."
    )


def _final_prompt(source: JsonObject, state: JsonObject, transcript: list[JsonValue]) -> str:
    prompt = source.get("prompt")
    if not isinstance(prompt, str):
        raise CheckError("stateful live item prompt is missing")
    return (
        f"{prompt}\nTarget state reached: {_canonical(state)}\n"
        f"Completed tool transcript: {_canonical(transcript)}\nReturn DONE only."
    )


def _combine_generations(
    generations: list[JsonObject],
    calls: list[JsonObject],
    protocol_flag: str | None,
) -> JsonObject:
    if not generations:
        raise CheckError("stateful live item produced no turns")
    token_ids: list[JsonValue] = []
    reasoning: list[str] = []
    latency = 0.0
    usage_totals: JsonObject = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
    for generation in generations:
        raw_tokens = generation.get("token_ids")
        if isinstance(raw_tokens, list):
            token_ids.extend(raw_tokens)
        raw_reasoning = generation.get("reasoning_text")
        if isinstance(raw_reasoning, str) and raw_reasoning:
            reasoning.append(raw_reasoning)
        raw_latency = generation.get("latency_seconds")
        if isinstance(raw_latency, int | float) and not isinstance(raw_latency, bool):
            latency += float(raw_latency)
        usage = generation.get("usage")
        if isinstance(usage, dict):
            for key in usage_totals:
                value = usage.get(key)
                current = usage_totals[key]
                if isinstance(value, int) and not isinstance(value, bool) and isinstance(current, int):
                    usage_totals[key] = current + value
        turn_flag = generation.get("protocol_flag")
        if protocol_flag is None and isinstance(turn_flag, str):
            protocol_flag = turn_flag
    call_values: list[JsonValue] = [call for call in calls]
    return {
        "finish_reason": generations[-1].get("finish_reason"),
        "latency_seconds": latency,
        "parsed_tool_calls": call_values,
        "protocol_flag": protocol_flag,
        "reasoning_text": "\n\n".join(reasoning) or None,
        "server_start_id": generations[0].get("server_start_id"),
        "stateful_turns": len(generations),
        "text": _canonical({"calls": call_values}),
        "token_ids": token_ids,
        "usage": usage_totals,
    }


def _canonical(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
