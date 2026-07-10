"""The Protocol C agent loop — bounded code-as-action over the AppWorld sandbox.

Given a :class:`ModelClient` (scripted OR a real chat-completions client) and a ``task_id``,
this drives the LOCKED Protocol C interaction:

    build prompt (task instruction + supervisor email + format rules + on-demand api_docs)
    repeat up to ``max_turns`` (LOCKED = 24):
        text = model.complete(history, params)          # one assistant turn
        action = parse_turn(text)                        # EXACTLY ONE python block
        if format error: append corrective observation; continue   # recoverable
        obs = sandbox.run_block(action.code)             # run block in the jail
        append OBSERVATION(obs) to history               # truncated to the char cap
        if action.is_final: answer = read-back `answer`; verdict = sandbox.finalize(answer)
    record per-task diagnostics + outcome

Determinism: greedy decoding + fixed seed handed to the client each turn; AppWorld fixes task
time on the trusted side; observation truncation is deterministic. The loop itself adds no
randomness.

The loop executes sandbox operations through the tiny :class:`SandboxLike` protocol
(``run_block``/``finalize``) and imports only the sandbox exception types needed for failure
classification. Unit tests inject a mock sandbox and exercise every path (success, format
failure -> corrective, cap_exceeded, no-final, finalize) with NO bwrap and NO model. The real
run passes a live ``AppWorldSandbox``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, assert_never

from localbench._types import ChatMessage
from localbench.scorers._reasoning import strip_reasoning
from localbench.scoring.agentic_exec.block_introspect import (
    count_api_calls,
    truncate_observation,
)
from localbench.scoring.agentic_exec.block_parser import (
    BlockFormatError,
    TurnAction,
    parse_turn,
)
from localbench.scoring.agentic_exec.loop_config import LoopConfig
from localbench.scoring.agentic_exec.loop_types import (
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
    TurnRecord,
)
from localbench.scoring.agentic_exec.model_client import ModelClient
from localbench.scoring.agentic_exec.prompt import (
    build_initial_messages,
    format_observation,
)
from localbench.scoring.agentic_exec.sandbox import SandboxError, SandboxTimeoutError
from localbench.submissions.attestation import sign_verdict_attestation

# Variable name the model must bind for its final answer (matches the prompt + block_parser).
_ANSWER_VAR = "answer"
# Harness-side read-back of the answer variable: emits a tagged JSON line we parse out. Using a
# tag avoids confusion with any earlier prints in the same (final) block's stdout — but note
# this runs as its OWN block, so its stdout is just the tagged line.
_READBACK_TAG = "__LB_ANSWER__"
_READBACK_CODE = (
    "import json as _lbjson\n"
    f"print('{_READBACK_TAG}' + _lbjson.dumps({_ANSWER_VAR}))"
)
_ANCHOR_MESSAGE_COUNT = 2
_HISTORY_ANCHOR_RESERVE_TOKENS = 2_048
_HISTORY_TURN_OVERHEAD_TOKENS = 256
class SandboxLike(Protocol):
    """The minimal sandbox surface the loop needs (satisfied by ``AppWorldSandbox``)."""

    def run_block(self, code: str) -> Any:
        """Run one code block; return an object with ``.stdout: str`` and ``.error: str|None``."""
        ...

    def finalize(self, answer: Any) -> Any:
        """Finalize; return an object with ``.success``/``.collateral_damage``/``.failures``."""
        ...


@dataclass(frozen=True, slots=True)
class _Verdict:
    success: bool
    collateral_damage: bool
    failures: tuple[str, ...]


def _bootstrap_task_context(sandbox: SandboxLike) -> tuple[str, str | None]:
    """Fetch the task instruction + supervisor email on the trusted side (no model turn).

    Runs a harness-owned block through the sandbox to read what the prompt needs. This is NOT
    counted as a model turn or an API-call diagnostic — it is harness scaffolding, equivalent
    to AppWorld handing the agent its task. Degrades gracefully: if the bootstrap can't read a
    field, the prompt is built without it (the model can still call show_active_task itself).
    """
    instruction = ""
    supervisor_email: str | None = None
    code = (
        "import json as _lbjson\n"
        "_t = apis.supervisor.show_active_task()\n"
        "_instr = _t.get('instruction') if isinstance(_t, dict) else None\n"
        "_email = None\n"
        "if isinstance(_t, dict):\n"
        "    _sup = _t.get('supervisor')\n"
        "    if isinstance(_sup, dict):\n"
        "        _email = _sup.get('email')\n"
        "print('__LB_CTX__' + _lbjson.dumps({'instruction': _instr, 'email': _email}))"
    )
    obs = sandbox.run_block(code)
    stdout = getattr(obs, "stdout", "") or ""
    for line in stdout.splitlines():
        if line.startswith("__LB_CTX__"):
            try:
                payload = json.loads(line[len("__LB_CTX__"):])
            except (ValueError, TypeError):
                break
            if isinstance(payload, dict):
                instr = payload.get("instruction")
                if isinstance(instr, str):
                    instruction = instr
                email = payload.get("email")
                if isinstance(email, str):
                    supervisor_email = email
            break
    return instruction, supervisor_email


def _read_back_answer(sandbox: SandboxLike) -> tuple[Any, str | None]:
    """Read the model's ``answer`` variable out of the persistent namespace as JSON.

    Returns ``(answer, error)``; ``error`` is non-None if ``answer`` was never bound or is not
    JSON-serialisable (the model said FINAL_ANSWER without a usable answer).
    """
    obs = sandbox.run_block(_READBACK_CODE)
    if getattr(obs, "error", None):
        return None, str(obs.error)
    stdout = getattr(obs, "stdout", "") or ""
    for line in stdout.splitlines():
        if line.startswith(_READBACK_TAG):
            try:
                return json.loads(line[len(_READBACK_TAG):]), None
            except (ValueError, TypeError) as exc:
                return None, f"answer not JSON-serialisable: {exc}"
    return None, "answer variable was not set"


def _coerce_verdict(raw: Any) -> _Verdict:
    """Normalise a sandbox Verdict (or duck-typed mock) into the loop's small view."""
    return _Verdict(
        success=bool(getattr(raw, "success", False)),
        collateral_damage=bool(getattr(raw, "collateral_damage", False)),
        failures=tuple(getattr(raw, "failures", ()) or ()),
    )


def run_task(
    sandbox: SandboxLike,
    model: ModelClient,
    task_id: str,
    config: LoopConfig | None = None,
) -> TaskRunResult:
    """Run one AppWorld task through the Protocol C loop; return verdict + diagnostics."""
    cfg = config or LoopConfig()
    params = cfg.generation_params()

    try:
        instruction, supervisor_email = _bootstrap_task_context(sandbox)
    except (SandboxTimeoutError, SandboxError) as exc:
        return _sandbox_failure_result(task_id, exc)
    messages: list[ChatMessage] = build_initial_messages(instruction, supervisor_email)

    turns: list[TurnRecord] = []
    blocks_run = 0
    format_failures = 0
    syntax_errors = 0
    runtime_errors = 0
    total_api_calls = 0
    api_docs_uses = 0
    observation_truncations = 0
    total_output_tokens = 0
    transport_failure_count = 0
    transport_attempt_count = 0

    outcome: TaskOutcome = TaskOutcome.NO_FINAL_ANSWER
    verdict = _Verdict(success=False, collateral_damage=False, failures=())
    attestation: dict[str, Any] | None = None
    finalize_error: str | None = None
    finalization: dict[str, Any] | None = None
    failure_class = FailureClass.NONE

    for turn_index in range(1, cfg.max_turns + 1):
        response = model.complete(messages, params)
        transport_failure_count += response.transport_failure_count
        transport_attempt_count += response.transport_attempt_count
        out_tokens = (
            response.output_tokens
            if response.output_tokens is not None
            else _estimate_tokens(response.text)
        )
        total_output_tokens += out_tokens
        # Record the assistant turn in the history regardless of how it parses.
        messages.append(ChatMessage(role="assistant", content=strip_reasoning(response.text)))

        # A per-turn token-cap hit ("length") means the block is almost certainly truncated;
        # treat it as a format failure for the turn with a corrective nudge (recoverable).
        if response.finish_reason == "length":
            format_failures += 1
            turns.append(_format_turn(
                turn_index,
                response.finish_reason,
                out_tokens,
                "length",
                response.text,
                server_timings=response.server_timings,
            ))
            messages.append(_user_msg(
                "FORMAT ERROR: your reply was cut off at the per-turn token limit. Keep each "
                "turn short: write one compact ```python block and print only what you need."
            ))
            messages = _window_messages(messages, cfg)
            continue

        parsed = parse_turn(response.text)
        if isinstance(parsed, BlockFormatError):
            format_failures += 1
            turns.append(_format_turn(
                turn_index,
                response.finish_reason,
                out_tokens,
                parsed.kind,
                response.text,
                error_detail=getattr(response, "error_detail", None),
                server_timings=response.server_timings,
            ))
            messages.append(_user_msg(parsed.message))
            messages = _window_messages(messages, cfg)
            continue

        assert isinstance(parsed, TurnAction)
        counts = count_api_calls(parsed.code)
        total_api_calls += counts.api_calls
        api_docs_uses += counts.api_docs_calls

        blocks_run += 1
        try:
            obs = sandbox.run_block(parsed.code)
        except (SandboxTimeoutError, SandboxError) as exc:
            failure_class = _failure_class_for_sandbox_exception(exc)
            finalize_error = f"{type(exc).__name__}: {exc}"
            outcome = TaskOutcome.HARNESS_ERROR
            turns.append(TurnRecord(
                index=turn_index,
                finish_reason=response.finish_reason,
                output_tokens=out_tokens,
                had_block=True,
                format_error=None,
                syntax_error=False,
                runtime_error=False,
                api_calls=counts.api_calls,
                api_docs_calls=counts.api_docs_calls,
                observation_truncated=False,
                is_final=False,
                raw_response_text=response.text,
                server_timings=response.server_timings,
            ))
            break
        err = getattr(obs, "error", None)
        is_syntax = bool(err) and str(err).startswith("SyntaxError")
        is_runtime = bool(err) and not is_syntax
        if is_syntax:
            syntax_errors += 1
        if is_runtime:
            runtime_errors += 1

        trunc = truncate_observation(getattr(obs, "stdout", "") or "", cfg.max_observation_chars)
        if trunc.truncated:
            observation_truncations += 1
        messages.append(_user_msg(format_observation(trunc.text, err)))

        # Resolve the final-answer signal BEFORE recording the turn, so a "signalled final but
        # bound no usable answer" turn is recorded as a (recoverable) format failure, not a
        # successful finalize. A real finalize attempt only happens when answer read-back works.
        turn_format_error: str | None = None
        turn_is_final = False
        if parsed.is_final:
            try:
                answer, read_err = _read_back_answer(sandbox)
            except (SandboxTimeoutError, SandboxError) as exc:
                failure_class = _failure_class_for_sandbox_exception(exc)
                finalize_error = f"{type(exc).__name__}: {exc}"
                outcome = TaskOutcome.HARNESS_ERROR
                turns.append(TurnRecord(
                    index=turn_index,
                    finish_reason=response.finish_reason,
                    output_tokens=out_tokens,
                    had_block=True,
                    format_error=None,
                    syntax_error=is_syntax,
                    runtime_error=is_runtime,
                    api_calls=counts.api_calls,
                    api_docs_calls=counts.api_docs_calls,
                    observation_truncated=trunc.truncated,
                    is_final=False,
                    raw_response_text=response.text,
                    server_timings=response.server_timings,
                ))
                break
            if read_err is not None:
                # The model signalled final but bound no usable answer: a protocol-compliance
                # (format) failure. Nudge once; let the loop continue so the model can fix
                # `answer` next turn (unless the cap is hit).
                turn_format_error = "final_no_answer"
                format_failures += 1
                messages.append(_user_msg(
                    "FORMAT ERROR: you wrote the FINAL_ANSWER sentinel but I could not read a "
                    f"usable `answer` variable ({read_err}). Bind `answer` to a JSON-"
                    "serialisable value in a python block, then write FINAL_ANSWER again."
                ))
            else:
                turn_is_final = True

        turns.append(TurnRecord(
            index=turn_index,
            finish_reason=response.finish_reason,
            output_tokens=out_tokens,
            had_block=True,
            format_error=turn_format_error,
            syntax_error=is_syntax,
            runtime_error=is_runtime,
            api_calls=counts.api_calls,
            api_docs_calls=counts.api_docs_calls,
            observation_truncated=trunc.truncated,
            is_final=turn_is_final,
            raw_response_text=response.text,
            server_timings=response.server_timings,
        ))

        if turn_is_final:
            # Stamp finalization provenance BEFORE calling finalize: the descriptor + answer
            # hash document what the orchestrator attempted even when finalize itself errors.
            finalization = _finalization_record(sandbox, answer)
            try:
                verdict = _coerce_verdict(sandbox.finalize(answer))
            except SandboxError as exc:
                finalize_error = f"{type(exc).__name__}: {exc}"
                outcome = TaskOutcome.HARNESS_ERROR
                failure_class = _failure_class_for_sandbox_exception(exc)
                break
            except Exception as exc:  # noqa: BLE001 — finalize failure is a reported outcome.
                finalize_error = f"{type(exc).__name__}: {exc}"
                outcome = TaskOutcome.HARNESS_ERROR
                failure_class = FailureClass.HARNESS_ERROR
                break
            if cfg.attester_key_path is not None:
                attestation = sign_verdict_attestation(
                    bench="appworld_c",
                    task_id=task_id,
                    run_id=cfg.attestation_run_id,
                    verdict={"success": verdict.success, "collateral_damage": verdict.collateral_damage},
                    signing_key_path=cfg.attester_key_path,
                )
            outcome = TaskOutcome.SUCCESS if verdict.success else TaskOutcome.FAILURE
            failure_class = _failure_class_for_outcome(outcome)
            break
        messages = _window_messages(messages, cfg)
    else:
        # for-loop exhausted without break => never finalized within the cap.
        outcome = TaskOutcome.CAP_EXCEEDED
        failure_class = FailureClass.MODEL_NO_PROGRESS

    diagnostics = TaskDiagnostics(
        task_id=task_id,
        outcome=outcome,
        success=verdict.success,
        collateral_damage=verdict.collateral_damage,
        turns_used=len(turns),
        blocks_run=blocks_run,
        format_failures=format_failures,
        syntax_errors=syntax_errors,
        runtime_errors=runtime_errors,
        cap_exceeded=(outcome == TaskOutcome.CAP_EXCEEDED),
        total_api_calls=total_api_calls,
        api_docs_uses=api_docs_uses,
        observation_truncations=observation_truncations,
        total_output_tokens=total_output_tokens,
        failure_class=failure_class,
        transport_failure_count=transport_failure_count,
        transport_attempt_count=transport_attempt_count,
        transport_failure_rate=(
            transport_failure_count / transport_attempt_count
            if transport_attempt_count
            else 0.0
        ),
        finalize_error=finalize_error,
        finalization=finalization,
        turns=turns,
    )
    return TaskRunResult(
        task_id=task_id,
        success=verdict.success,
        outcome=outcome,
        collateral_damage=verdict.collateral_damage,
        diagnostics=diagnostics,
        attestation=attestation,
    )


def _finalization_record(sandbox: SandboxLike, answer: Any) -> dict[str, Any] | None:
    """Additive per-task finalization provenance, or None for sandboxes without a descriptor.

    ``answer_hash`` is the sha256 of the orchestrator's OWN read-back answer — the exact value
    handed to ``finalize`` — canonicalised as compact sorted-key ASCII JSON. It documents what
    the trusted side asked the env-host to evaluate, independent of the verdict outcome.
    """
    descriptor = getattr(sandbox, "finalization_provenance", None)
    if not callable(descriptor):
        return None
    record = dict(descriptor())
    try:
        answer_bytes = json.dumps(
            answer,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        # The answer came from json.loads so this is near-impossible; record the descriptor
        # with an explicit null hash rather than failing the task over provenance.
        record["answer_hash"] = None
        return record
    record["answer_hash"] = hashlib.sha256(answer_bytes).hexdigest()
    return record


def _user_msg(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _window_messages(messages: list[ChatMessage], config: LoopConfig) -> list[ChatMessage]:
    """Keep anchor messages plus a fixed recent-history budget derived from context size."""
    if len(messages) <= _ANCHOR_MESSAGE_COUNT:
        return messages
    recent_limit = _recent_history_message_limit(config)
    middle = messages[_ANCHOR_MESSAGE_COUNT:]
    if len(middle) <= recent_limit:
        return messages
    return messages[:_ANCHOR_MESSAGE_COUNT] + middle[-recent_limit:]


def _recent_history_message_limit(config: LoopConfig) -> int:
    observation_tokens = max(1, (config.max_observation_chars + 3) // 4)
    tokens_per_turn = (
        config.max_output_tokens_per_turn
        + observation_tokens
        + _HISTORY_TURN_OVERHEAD_TOKENS
    )
    available_tokens = max(tokens_per_turn, config.context_window - _HISTORY_ANCHOR_RESERVE_TOKENS)
    recent_turns = max(1, available_tokens // tokens_per_turn)
    return recent_turns * 2


def _failure_class_for_sandbox_exception(exc: SandboxError) -> FailureClass:
    match exc:
        case SandboxTimeoutError():
            return FailureClass.INFRA_TIMEOUT
        case SandboxError():
            return FailureClass.INFRA_SANDBOX


def _failure_class_for_outcome(outcome: TaskOutcome) -> FailureClass:
    match outcome:
        case TaskOutcome.SUCCESS:
            return FailureClass.NONE
        case TaskOutcome.FAILURE:
            return FailureClass.MODEL_FAILURE
        case TaskOutcome.CAP_EXCEEDED | TaskOutcome.NO_FINAL_ANSWER:
            return FailureClass.MODEL_NO_PROGRESS
        case TaskOutcome.HARNESS_ERROR:
            return FailureClass.HARNESS_ERROR
        case unreachable:
            assert_never(unreachable)


def _sandbox_failure_result(task_id: str, exc: SandboxError) -> TaskRunResult:
    failure_class = _failure_class_for_sandbox_exception(exc)
    diagnostics = TaskDiagnostics(
        task_id=task_id,
        outcome=TaskOutcome.HARNESS_ERROR,
        success=False,
        collateral_damage=False,
        turns_used=0,
        blocks_run=0,
        format_failures=0,
        syntax_errors=0,
        runtime_errors=0,
        cap_exceeded=False,
        total_api_calls=0,
        api_docs_uses=0,
        observation_truncations=0,
        total_output_tokens=0,
        failure_class=failure_class,
        finalize_error=f"{type(exc).__name__}: {exc}",
        turns=[],
    )
    return TaskRunResult(
        task_id=task_id,
        success=False,
        outcome=TaskOutcome.HARNESS_ERROR,
        collateral_damage=False,
        diagnostics=diagnostics,
    )


def _format_turn(
    index: int,
    finish_reason: str,
    out_tokens: int,
    kind: str,
    raw_response_text: str,
    error_detail: str | None = None,
    server_timings: dict[str, Any] | None = None,
) -> TurnRecord:
    """A TurnRecord for a turn that produced no runnable block (a format failure)."""
    return TurnRecord(
        index=index,
        finish_reason=finish_reason,
        output_tokens=out_tokens,
        had_block=False,
        format_error=kind,
        syntax_error=False,
        runtime_error=False,
        api_calls=0,
        api_docs_calls=0,
        observation_truncated=False,
        is_final=False,
        raw_response_text=raw_response_text,
        error_detail=error_detail,
        server_timings=server_timings,
    )


def _estimate_tokens(text: str) -> int:
    """Deterministic, dependency-free completion-token estimate for diagnostics.

    Used only when a client does not report usage (the scripted client). ~4 chars/token is a
    standard rough proxy; exactness does not matter for the per-task token diagnostic.
    """
    return max(1, (len(text) + 3) // 4)
