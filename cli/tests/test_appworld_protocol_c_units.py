"""Host-agnostic unit tests for the Protocol C agent loop (NO model, NO bwrap, NO appworld).

These lock in the loop mechanics + diagnostics with a deterministic in-memory FakeSandbox that
mimics the real ``AppWorldSandbox`` surface (``run_block``/``finalize``) closely enough to drive
the loop down every path: success, format-failure -> corrective observation, cap_exceeded,
no-final, observation truncation, api_docs usage, and the benchmark aggregate. They run anywhere
(Windows/Linux/WSL) under any Python the repo targets.

The live two-process gate (scripted agent through the REAL sandbox) lives in
``test_appworld_sandbox_acceptance.py`` and runs under WSL.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "cli" / "src"))

from localbench._types import ChatMessage  # noqa: E402
from localbench.scoring.agentic_exec import benchmark as bench  # noqa: E402
from localbench.scoring.agentic_exec import block_introspect as bi  # noqa: E402
from localbench.scoring.agentic_exec import block_parser as bp  # noqa: E402
from localbench.scoring.agentic_exec import prompt as prompt_mod  # noqa: E402
from localbench.scoring.agentic_exec import sandbox as sandbox_mod  # noqa: E402
from localbench.scoring.agentic_exec import scripted_agent as sa  # noqa: E402
from localbench.scoring.agentic_exec.loop_config import LoopConfig  # noqa: E402
from localbench.scoring.agentic_exec.loop_types import (  # noqa: E402
    FailureClass,
    TaskDiagnostics,
    TaskOutcome,
    TaskRunResult,
)
from localbench.scoring.agentic_exec.model_client import (  # noqa: E402
    GenerationParams,
    ModelResponse,
)
from localbench.scoring.agentic_exec.protocol_c_loop import run_task  # noqa: E402
from localbench.scoring.agentic_exec.sandbox import (  # noqa: E402
    SandboxConfig,
    SandboxError,
    SandboxTimeoutError,
)


# ==============================================================================================
# block_parser
# ==============================================================================================
def test_parser_extracts_single_python_block() -> None:
    res = bp.parse_turn("Here goes:\n```python\nprint(apis.supervisor.show_profile())\n```")
    assert isinstance(res, bp.TurnAction)
    assert "show_profile" in res.code
    assert res.is_final is False


def test_parser_accepts_untagged_fence_as_python() -> None:
    res = bp.parse_turn("```\nx = 1\nprint(x)\n```")
    assert isinstance(res, bp.TurnAction)
    assert res.code.strip() == "x = 1\nprint(x)"


def test_parser_zero_blocks_is_format_error() -> None:
    res = bp.parse_turn("I think the answer is probably 42 but I won't write code.")
    assert isinstance(res, bp.BlockFormatError)
    assert res.kind == "no_block"
    assert "EXACTLY ONE" in res.message


def test_parser_multiple_blocks_is_format_error() -> None:
    res = bp.parse_turn("```python\na=1\n```\nand\n```python\nb=2\n```")
    assert isinstance(res, bp.BlockFormatError)
    assert res.kind == "multiple_blocks"
    assert "2 python code blocks" in res.message


def test_parser_empty_block_is_format_error() -> None:
    res = bp.parse_turn("```python\n\n```")
    assert isinstance(res, bp.BlockFormatError)
    assert res.kind == "empty_block"


def test_parser_ignores_non_python_fence_when_counting() -> None:
    # a json fence must NOT be treated as the code block.
    res = bp.parse_turn("```json\n{\"a\":1}\n```\n```python\nprint(1)\n```")
    assert isinstance(res, bp.TurnAction)
    assert res.code.strip() == "print(1)"


def test_parser_detects_final_sentinel_standalone_line() -> None:
    res = bp.parse_turn("```python\nanswer = 81\n```\nFINAL_ANSWER")
    assert isinstance(res, bp.TurnAction)
    assert res.is_final is True


def test_parser_detects_final_sentinel_as_comment_inside_block() -> None:
    res = bp.parse_turn("```python\nanswer = 81\n# FINAL_ANSWER\n```")
    assert isinstance(res, bp.TurnAction)
    assert res.is_final is True


def test_parser_does_not_falsely_detect_sentinel_in_prose() -> None:
    res = bp.parse_turn("```python\nprint('the FINAL_ANSWER will be ready soon')\n```")
    assert isinstance(res, bp.TurnAction)
    assert res.is_final is False


# ==============================================================================================
# block_introspect
# ==============================================================================================
def test_count_api_calls_counts_app_api_and_docs() -> None:
    code = (
        "a = apis.spotify.login(username='u', password='p')\n"
        "b = apis.spotify.show_song(song_id=1)\n"
        "d = apis.api_docs.show_api_descriptions(app_name='spotify')\n"
        "x = len([1,2,3])\n"  # not an apis call
    )
    counts = bi.count_api_calls(code)
    assert counts.api_calls == 3
    assert counts.api_docs_calls == 1


def test_count_api_calls_unparseable_is_zero() -> None:
    counts = bi.count_api_calls("def (:\n  syntactically broken")
    assert counts.api_calls == 0
    assert counts.api_docs_calls == 0


def test_truncate_observation_marks_when_cut() -> None:
    t = bi.truncate_observation("x" * 100, max_chars=20)
    assert t.truncated is True
    assert "truncated" in t.text
    short = bi.truncate_observation("hello", max_chars=20)
    assert short.truncated is False
    assert short.text == "hello"


# ==============================================================================================
# prompt
# ==============================================================================================
def test_prompt_embeds_instruction_and_sentinel() -> None:
    msgs = prompt_mod.build_initial_messages(
        "Count my unique songs.", supervisor_email="boss@example.com"
    )
    # A system message PLUS a user kickoff turn. The kickoff is required, not cosmetic: some
    # chat templates (e.g. Qwen3) cannot generate from a system-only history and only engage
    # native thinking when the last message is a user turn. The system message still carries
    # the task instruction / sentinel / supervisor email.
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user" and msgs[1]["content"] == "Begin."
    sys_text = msgs[0]["content"]
    assert "Count my unique songs." in sys_text
    assert bp.FINAL_ANSWER_SENTINEL in sys_text
    assert "boss@example.com" in sys_text
    assert "apis.api_docs.show_api_doc" in sys_text  # on-demand discovery is advertised


def test_prompt_does_not_dump_all_apis() -> None:
    # The prompt should advertise discovery, not enumerate hundreds of APIs.
    sys_text = prompt_mod.build_system_prompt("do a thing")
    assert sys_text.count("apis.") < 30  # a handful of examples, not ~457 APIs


# ==============================================================================================
# FakeSandbox: an in-memory stand-in for AppWorldSandbox (run_block / finalize)
# ==============================================================================================
class _Obs:
    __slots__ = ("stdout", "error")

    def __init__(self, stdout: str = "", error: str | None = None) -> None:
        self.stdout = stdout
        self.error = error


class _FakeVerdict:
    __slots__ = ("success", "collateral_damage", "passes", "failures")

    def __init__(self, success: bool, collateral: bool = False) -> None:
        self.success = success
        self.collateral_damage = collateral
        self.passes = ("ok",) if success else ()
        self.failures = () if success else ("did not match gold",)


class FakeSandbox:
    """Executes the model's code in a restricted namespace with a stub ``apis``.

    It does NOT need bwrap or appworld: it runs the block via ``exec`` against a tiny in-memory
    ``apis`` object whose methods return canned data, so the scripted solver's real code paths
    (auth, pagination, aggregation, binding ``answer``) all execute and the loop's read-back +
    finalize seam is exercised. ``finalize`` checks the answer against a configured gold value.

    This is a TEST DOUBLE for loop mechanics only — it is explicitly not a security boundary
    (that is the real sandbox's job, covered by the canary suite + acceptance gates).
    """

    def __init__(self, gold_answer: object, instruction: str, supervisor_email: str) -> None:
        self._gold = gold_answer
        self._ns: dict[str, object] = {"apis": _StubApis(instruction, supervisor_email)}
        self.finalized_with: object = None
        self.run_blocks: list[str] = []

    def run_block(self, code: str) -> _Obs:
        self.run_blocks.append(code)
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        try:
            compiled = compile(code, "<fake_block>", "exec")
        except SyntaxError as exc:
            return _Obs("", f"SyntaxError: {exc}")
        try:
            with redirect_stdout(buf):
                exec(compiled, self._ns, self._ns)  # noqa: S102 — test double, not a sandbox.
        except Exception as exc:  # noqa: BLE001
            return _Obs(buf.getvalue(), f"{type(exc).__name__}: {exc}")
        return _Obs(buf.getvalue(), None)

    def finalize(self, answer: object) -> _FakeVerdict:
        self.finalized_with = answer
        return _FakeVerdict(success=(answer == self._gold))

    # context-manager so the same double works through the benchmark entry point.
    def __enter__(self) -> "FakeSandbox":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _StubSpotify:
    """Minimal spotify stub: 2 users' worth of canned songs across three libraries."""

    def __init__(self) -> None:
        # song_id -> (title, genre, play_count)
        self._songs = {
            1: ("Alpha", "R&B", 50),
            2: ("Bravo", "R&B", 90),
            3: ("Charlie", "Rock", 10),
            4: ("Delta", "R&B", 70),
            5: ("Echo", "R&B", 30),
        }
        self._token = "tok-123"

    def login(self, username: str, password: str) -> dict:
        return {"access_token": self._token}

    def show_song_library(self, access_token: str, page_index: int) -> list:
        # one page with songs 1,2 then empty.
        return [{"song_id": 1}, {"song_id": 2}] if page_index == 0 else []

    def show_album_library(self, access_token: str, page_index: int) -> list:
        return [{"album_id": 10, "song_ids": [3]}] if page_index == 0 else []

    def show_playlist_library(self, access_token: str, page_index: int) -> list:
        return [{"playlist_id": 20, "song_ids": [4, 5]}] if page_index == 0 else []

    def show_album(self, album_id: int) -> dict:
        return {"songs": [{"id": 3}]}

    def show_playlist(self, access_token: str, playlist_id: int) -> dict:
        return {"songs": [{"id": 4}, {"id": 5}]}

    def show_song(self, song_id: int) -> dict:
        title, genre, pc = self._songs[song_id]
        return {"title": title, "genre": genre, "play_count": pc}


class _StubSupervisor:
    def __init__(self, instruction: str, email: str) -> None:
        self._instruction = instruction
        self._email = email

    def show_profile(self) -> dict:
        return {"email": "me@example.com"}

    def show_account_passwords(self) -> list:
        return [{"account_name": "spotify", "password": "pw"}]

    def show_active_task(self) -> dict:
        return {"instruction": self._instruction, "supervisor": {"email": self._email}}


class _StubApis:
    def __init__(self, instruction: str, email: str) -> None:
        self.spotify = _StubSpotify()
        self.supervisor = _StubSupervisor(instruction, email)


# ==============================================================================================
# scripted agent through the loop (against the FakeSandbox) — success + diagnostics
# ==============================================================================================
_FAC_INSTR = "How many unique songs are in my library across songs, albums and playlists?"
_50E_INSTR = "What are the titles of the top 3 most played R&B songs in my library?"


def test_loop_scripted_solves_unique_song_count_through_fakesandbox() -> None:
    # gold for the stub: unique song_ids {1,2,3,4,5} = 5.
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="boss@x.com")
    agent = sa.ScriptedSolverAgent("fac291d_1")
    result = run_task(sandbox, agent, "fac291d_1")
    assert result.success is True
    assert result.outcome == TaskOutcome.SUCCESS
    assert sandbox.finalized_with == 5
    d = result.diagnostics
    assert d.blocks_run == 3                 # three solving blocks
    assert d.format_failures == 0
    assert d.syntax_errors == 0
    assert d.runtime_errors == 0
    assert d.cap_exceeded is False
    assert d.total_api_calls > 0             # real apis.* calls were counted
    assert d.api_docs_uses == 0


def test_loop_scripted_solves_topk_genre_titles_through_fakesandbox() -> None:
    # top 3 R&B by play_count: Bravo(90), Delta(70), Alpha(50) -> "Bravo, Delta, Alpha".
    gold = "Bravo, Delta, Alpha"
    sandbox = FakeSandbox(gold_answer=gold, instruction=_50E_INSTR, supervisor_email="b@x.com")
    agent = sa.ScriptedSolverAgent("50e1ac9_1")
    result = run_task(sandbox, agent, "50e1ac9_1")
    assert result.success is True
    assert sandbox.finalized_with == gold
    assert result.diagnostics.blocks_run == 3


def test_loop_records_turn_level_diagnostics() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    result = run_task(sandbox, sa.ScriptedSolverAgent("fac291d_1"), "fac291d_1")
    # one TurnRecord per model turn; all had a block; the last is final.
    assert len(result.diagnostics.turns) == 3
    assert all(t.had_block for t in result.diagnostics.turns)
    assert result.diagnostics.turns[-1].is_final is True
    assert result.diagnostics.total_output_tokens > 0


def test_loop_records_turn_level_server_timings() -> None:
    timings = {"prompt_n": 9, "prompt_ms": 18.0, "predicted_n": 4, "predicted_ms": 8.0}

    class _TimedFinal:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            return ModelResponse(
                "```python\nanswer = 5\n```\nFINAL_ANSWER",
                "stop",
                server_timings={"passes": [timings]},
            )

    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    result = run_task(sandbox, _TimedFinal(), "fac291d_1")

    assert result.success is True
    assert result.diagnostics.turns[0].server_timings == {"passes": [timings]}
    assert result.diagnostics.as_dict()["turns"][0]["server_timings"] == {"passes": [timings]}


# ==============================================================================================
# failure paths
# ==============================================================================================
def test_loop_format_failure_then_corrective_observation_then_recover() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    # one bad (no_block) turn, then solve fac291d.
    agent = sa.BadFormatAgent(mode="no_block", bad_turns=1, recover_blocks=_fac_blocks())
    result = run_task(sandbox, agent, "fac291d_1")
    assert result.diagnostics.format_failures == 1
    assert result.success is True
    # the corrective observation was injected as a user message (so the model could recover).
    # first assistant turn was bad; a user corrective followed before the next assistant turn.
    assert result.diagnostics.turns[0].format_error == "no_block"
    assert result.diagnostics.turns[0].had_block is False


def test_loop_multiple_blocks_is_format_failure() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    agent = sa.BadFormatAgent(mode="multiple_blocks", bad_turns=1, recover_blocks=_fac_blocks())
    result = run_task(sandbox, agent, "fac291d_1")
    assert result.diagnostics.format_failures == 1
    assert result.diagnostics.turns[0].format_error == "multiple_blocks"
    assert result.success is True


def test_loop_cap_exceeded_when_never_finalizes() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    cfg = LoopConfig(max_turns=5)
    result = run_task(sandbox, sa.NeverFinalizeAgent(), "fac291d_1", cfg)
    assert result.success is False
    assert result.outcome == TaskOutcome.CAP_EXCEEDED
    assert result.diagnostics.cap_exceeded is True
    assert result.diagnostics.turns_used == 5
    assert result.diagnostics.blocks_run == 5  # every no-op block ran


def test_loop_runtime_error_is_recorded_and_recoverable() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    class _RaiseThenSolve:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            step = sum(1 for m in messages if m["role"] == "assistant")
            if step == 0:
                return ModelResponse("```python\nraise ValueError('boom')\n```", "stop")
            blocks = _fac_blocks()
            code = blocks[step - 1]
            is_last = (step - 1) == len(blocks) - 1
            body = f"```python\n{code}\n```"
            if is_last:
                body += f"\n{bp.FINAL_ANSWER_SENTINEL}"
            return ModelResponse(body, "stop")

    result = run_task(sandbox, _RaiseThenSolve(), "fac291d_1")
    assert result.diagnostics.runtime_errors == 1
    assert result.diagnostics.turns[0].runtime_error is True
    assert result.success is True  # recovered after the error observation


def test_loop_token_cap_length_finish_is_format_failure() -> None:
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    class _Truncated:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            step = sum(1 for m in messages if m["role"] == "assistant")
            if step == 0:
                return ModelResponse("```python\nprint('cut off here", "length")
            blocks = _fac_blocks()
            code = blocks[step - 1]
            is_last = (step - 1) == len(blocks) - 1
            body = f"```python\n{code}\n```" + (f"\n{bp.FINAL_ANSWER_SENTINEL}" if is_last else "")
            return ModelResponse(body, "stop")

    result = run_task(sandbox, _Truncated(), "fac291d_1")
    assert result.diagnostics.format_failures == 1
    assert result.diagnostics.turns[0].format_error == "length"
    assert result.success is True


def test_loop_final_without_answer_var_nudges_then_recovers() -> None:
    sandbox = FakeSandbox(gold_answer=7, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    class _FinalTooEarly:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            step = sum(1 for m in messages if m["role"] == "assistant")
            if step == 0:
                # signals final but never binds `answer`.
                return ModelResponse("```python\nprint('done?')\n```\nFINAL_ANSWER", "stop")
            # then properly binds and finalizes.
            return ModelResponse("```python\nanswer = 7\n```\nFINAL_ANSWER", "stop")

    result = run_task(sandbox, _FinalTooEarly(), "fac291d_1")
    assert result.success is True
    assert sandbox.finalized_with == 7
    # the premature-final turn counts as a format failure (could not read answer).
    assert result.diagnostics.format_failures == 1


def test_loop_strips_reasoning_only_from_history_and_preserves_raw_turn() -> None:
    sandbox = FakeSandbox(gold_answer=3, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    class _ThinkingThenFinal:
        def __init__(self) -> None:
            self.calls: list[list[ChatMessage]] = []

        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            self.calls.append([dict(m) for m in messages])
            if len(self.calls) == 1:
                return ModelResponse(
                    "<think>hidden chain</think>\n```python\nprint('observed')\n```",
                    "stop",
                    output_tokens=12,
                )
            return ModelResponse("```python\nanswer = 3\n```\nFINAL_ANSWER", "stop")

    agent = _ThinkingThenFinal()
    result = run_task(sandbox, agent, "fac291d_1")

    assert result.success is True
    assert result.diagnostics.turns[0].raw_response_text.startswith("<think>hidden chain</think>")
    second_call_history = agent.calls[1]
    assistant_messages = [m for m in second_call_history if m["role"] == "assistant"]
    assert assistant_messages[0]["content"] == "\n```python\nprint('observed')\n```"
    assert "<think>" not in assistant_messages[0]["content"]


def test_loop_windows_history_deterministically_with_anchors_and_recent_turns() -> None:
    class _LongEpisodeAgent:
        def __init__(self) -> None:
            self.call_histories: list[list[ChatMessage]] = []
            self.step = 0

        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            self.call_histories.append([dict(m) for m in messages])
            self.step += 1
            return ModelResponse(f"```python\nprint('turn-{self.step}')\n```", "stop")

    def run_episode() -> list[list[ChatMessage]]:
        sandbox = FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com")
        agent = _LongEpisodeAgent()
        cfg = LoopConfig(
            max_turns=6,
            context_window=2_500,
            max_output_tokens_per_turn=512,
            max_observation_chars=2_000,
        )
        result = run_task(sandbox, agent, "fac291d_1", cfg)
        assert result.outcome == TaskOutcome.CAP_EXCEEDED
        return agent.call_histories

    first = run_episode()
    second = run_episode()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    final_history = first[-1]
    assert final_history[0]["role"] == "system"
    assert _FAC_INSTR in final_history[0]["content"]
    assert final_history[1] == {"role": "user", "content": "Begin."}
    assert "turn-1" not in json.dumps(final_history)
    assert "turn-5" in json.dumps(final_history)
    assert len(final_history) == 4


def test_loop_classifies_block_wall_timeout_as_infra_without_retry() -> None:
    class _TimeoutSandbox(FakeSandbox):
        def __init__(self) -> None:
            super().__init__(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com")
            self.model_block_attempts = 0

        def run_block(self, code: str) -> _Obs:
            if "show_active_task" not in code:
                self.model_block_attempts += 1
                raise SandboxTimeoutError("block wall-clock safety net fired")
            return super().run_block(code)

    class _OneBlock:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            return ModelResponse("```python\nprint('hang')\n```", "stop")

    sandbox = _TimeoutSandbox()
    result = run_task(sandbox, _OneBlock(), "fac291d_1")

    assert result.outcome == TaskOutcome.HARNESS_ERROR
    assert result.diagnostics.failure_class == FailureClass.INFRA_TIMEOUT
    assert result.diagnostics.success is False
    assert sandbox.model_block_attempts == 1


def test_loop_preserves_finalize_timeout_as_infra_timeout() -> None:
    class _FinalizeTimeoutSandbox(FakeSandbox):
        def finalize(self, answer: object) -> _FakeVerdict:
            raise SandboxTimeoutError("finalize timed out")

    class _FinalAnswer:
        def complete(
            self,
            messages: list[ChatMessage],
            params: GenerationParams,
        ) -> ModelResponse:
            return ModelResponse("```python\nanswer = 1\n```\nFINAL_ANSWER", "stop")

    result = run_task(
        _FinalizeTimeoutSandbox(
            gold_answer=1,
            instruction=_FAC_INSTR,
            supervisor_email="b@x.com",
        ),
        _FinalAnswer(),
        "fac291d_1",
    )

    assert result.outcome == TaskOutcome.HARNESS_ERROR
    assert result.diagnostics.failure_class == FailureClass.INFRA_TIMEOUT
    assert "SandboxTimeoutError" in (result.diagnostics.finalize_error or "")


def test_loop_classifies_model_failure_no_progress_and_harness_error() -> None:
    class _WrongFinal:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            return ModelResponse("```python\nanswer = 999\n```\nFINAL_ANSWER", "stop")

    class _FinalizeCrashSandbox(FakeSandbox):
        def finalize(self, answer: object) -> _FakeVerdict:
            raise RuntimeError("evaluator exploded")

    wrong = run_task(
        FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com"),
        _WrongFinal(),
        "fac291d_1",
    )
    capped = run_task(
        FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com"),
        sa.NeverFinalizeAgent(),
        "fac291d_1",
        LoopConfig(max_turns=1),
    )
    harness = run_task(
        _FinalizeCrashSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com"),
        _WrongFinal(),
        "fac291d_1",
    )

    assert wrong.outcome == TaskOutcome.FAILURE
    assert wrong.diagnostics.failure_class == FailureClass.MODEL_FAILURE
    assert capped.outcome == TaskOutcome.CAP_EXCEEDED
    assert capped.diagnostics.failure_class == FailureClass.MODEL_NO_PROGRESS
    assert harness.outcome == TaskOutcome.HARNESS_ERROR
    assert harness.diagnostics.failure_class == FailureClass.HARNESS_ERROR


def test_sandbox_config_uses_cpu_budget_and_generous_wall_safety_net() -> None:
    cfg = SandboxConfig()
    assert cfg.cpu_seconds == 60
    assert cfg.block_wall_timeout_s >= 300.0
    assert cfg.block_wall_timeout_s > cfg.cpu_seconds
    assert cfg.block_timeout_s == cfg.block_wall_timeout_s


def test_observation_truncation_counts() -> None:
    sandbox = FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    cfg = LoopConfig(max_observation_chars=10)

    class _BigPrint:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            step = sum(1 for m in messages if m["role"] == "assistant")
            if step == 0:
                return ModelResponse("```python\nprint('x' * 500)\n```", "stop")
            return ModelResponse("```python\nanswer = 1\n```\nFINAL_ANSWER", "stop")

    result = run_task(sandbox, _BigPrint(), "fac291d_1", cfg)
    assert result.diagnostics.observation_truncations == 1
    assert result.success is True


# ==============================================================================================
# benchmark aggregate + entry point
# ==============================================================================================
def test_benchmark_entry_point_aggregates_two_tasks() -> None:
    golds = {"fac291d_1": (5, _FAC_INSTR), "50e1ac9_1": ("Bravo, Delta, Alpha", _50E_INSTR)}

    def sandbox_factory(task_id: str) -> FakeSandbox:
        gold, instr = golds[task_id]
        return FakeSandbox(gold_answer=gold, instruction=instr, supervisor_email="b@x.com")

    def model_factory(task_id: str) -> sa.ScriptedSolverAgent:
        return sa.ScriptedSolverAgent(task_id)

    report = bench.run_appworld_c_benchmark(
        task_ids=["fac291d_1", "50e1ac9_1"],
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
    )
    assert report.tasks_total == 2
    assert report.tasks_succeeded == 2
    assert report.agentic_success_rate == 1.0
    assert report.cap_exceeded_rate == 0.0
    assert report.syntax_error_rate == 0.0
    assert report.mean_blocks_run == 3.0
    assert report.outcome_counts["success"] == 2
    # report is JSON-serialisable for the GPU run to persist.
    json.dumps(report.as_dict())


def test_benchmark_isolates_per_task_harness_error() -> None:
    def bad_sandbox_factory(task_id: str):
        raise RuntimeError("sandbox could not start (e.g. bwrap missing)")

    report = bench.run_appworld_c_benchmark(
        task_ids=["fac291d_1"],
        model_factory=lambda t: sa.ScriptedSolverAgent(t),
        sandbox_factory=bad_sandbox_factory,
    )
    assert report.tasks_total == 1
    assert report.harness_error_rate == 1.0
    assert report.results[0].outcome == TaskOutcome.HARNESS_ERROR
    assert "RuntimeError" in (report.results[0].diagnostics.finalize_error or "")


def test_benchmark_adds_infra_rates_and_asr_excluding_infra_without_changing_primary_asr() -> None:
    def diag(
        task_id: str,
        outcome: TaskOutcome,
        success: bool,
        failure_class: FailureClass,
    ) -> TaskRunResult:
        diagnostics = TaskDiagnostics(
            task_id=task_id,
            outcome=outcome,
            success=success,
            collateral_damage=False,
            turns_used=1,
            blocks_run=1,
            format_failures=0,
            syntax_errors=0,
            runtime_errors=0,
            cap_exceeded=(outcome == TaskOutcome.CAP_EXCEEDED),
            total_api_calls=0,
            api_docs_uses=0,
            observation_truncations=0,
            total_output_tokens=1,
            failure_class=failure_class,
        )
        return TaskRunResult(
            task_id=task_id,
            success=success,
            outcome=outcome,
            collateral_damage=False,
            diagnostics=diagnostics,
        )

    report = bench.aggregate(
        [
            diag("success", TaskOutcome.SUCCESS, True, FailureClass.NONE),
            diag("infra-timeout", TaskOutcome.HARNESS_ERROR, False, FailureClass.INFRA_TIMEOUT),
            diag("infra-sandbox", TaskOutcome.HARNESS_ERROR, False, FailureClass.INFRA_SANDBOX),
            diag("model-failure", TaskOutcome.FAILURE, False, FailureClass.MODEL_FAILURE),
            diag("no-progress", TaskOutcome.CAP_EXCEEDED, False, FailureClass.MODEL_NO_PROGRESS),
            diag("harness", TaskOutcome.HARNESS_ERROR, False, FailureClass.HARNESS_ERROR),
        ]
    )

    assert report.agentic_success_rate == pytest.approx(1 / 6)
    assert report.harness_error_rate == pytest.approx(3 / 6)
    assert report.asr_excluding_infra == pytest.approx(1 / 4)
    assert report.infra_timeout_rate == pytest.approx(1 / 6)
    assert report.infra_sandbox_rate == pytest.approx(1 / 6)
    assert report.model_failure_rate == pytest.approx(1 / 6)
    assert report.model_no_progress_rate == pytest.approx(1 / 6)
    assert report.harness_error_subclass_rate == pytest.approx(1 / 6)
    assert report.as_dict()["asr_excluding_infra"] == pytest.approx(1 / 4)


def test_benchmark_classifies_sandbox_setup_error_as_infra_sandbox() -> None:
    def bad_sandbox_factory(task_id: str):
        raise SandboxError("bwrap missing")

    report = bench.run_appworld_c_benchmark(
        task_ids=["fac291d_1"],
        model_factory=lambda t: sa.ScriptedSolverAgent(t),
        sandbox_factory=bad_sandbox_factory,
    )

    assert report.harness_error_rate == 1.0
    assert report.infra_sandbox_rate == 1.0
    assert report.asr_excluding_infra == 0.0
    assert report.results[0].diagnostics.failure_class == FailureClass.INFRA_SANDBOX


def test_benchmark_watchdog_records_infra_timeout_and_continues() -> None:
    release_hung_model = threading.Event()
    cancelled_model = threading.Event()
    forced_cleanup = threading.Event()

    class _BlockingModel:
        def complete(self, messages: list[ChatMessage], params: GenerationParams) -> ModelResponse:
            release_hung_model.wait(timeout=5.0)
            return ModelResponse("```python\nanswer = 5\n```\nFINAL_ANSWER", "stop")

        def cancel(self) -> None:
            cancelled_model.set()
            release_hung_model.set()

    class _KillableSandbox(FakeSandbox):
        def force_kill(self) -> None:
            forced_cleanup.set()

    def sandbox_factory(task_id: str) -> FakeSandbox:
        if task_id == "hang":
            return _KillableSandbox(
                gold_answer=5,
                instruction=_FAC_INSTR,
                supervisor_email="b@x.com",
            )
        return FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    def model_factory(task_id: str):
        if task_id == "hang":
            return _BlockingModel()
        return sa.ScriptedSolverAgent(task_id)

    report = bench.run_appworld_c_benchmark(
        task_ids=["hang", "fac291d_1"],
        model_factory=model_factory,
        sandbox_factory=sandbox_factory,
        config=LoopConfig(per_task_timeout_s=0.05),
    )

    assert forced_cleanup.wait(timeout=1.0)
    assert cancelled_model.wait(timeout=1.0)
    assert report.tasks_total == 2
    assert report.tasks_succeeded == 1
    assert report.infra_timeout_rate == pytest.approx(0.5)
    assert report.results[0].task_id == "hang"
    assert report.results[0].outcome == TaskOutcome.HARNESS_ERROR
    assert report.results[0].diagnostics.failure_class == FailureClass.INFRA_TIMEOUT
    assert report.results[1].task_id == "fac291d_1"
    assert report.results[1].success is True


def test_successful_task_keeps_result_when_teardown_fails_additively() -> None:
    class _TeardownDiagnosticSandbox(FakeSandbox):
        teardown_failure: str | None = None

        def __exit__(self, *exc: object) -> None:
            self.teardown_failure = "SandboxTimeoutError: teardown timed out"

    report = bench.run_appworld_c_benchmark(
        task_ids=["fac291d_1"],
        model_factory=lambda task_id: sa.ScriptedSolverAgent(task_id),
        sandbox_factory=lambda _task_id: _TeardownDiagnosticSandbox(
            gold_answer=5,
            instruction=_FAC_INSTR,
            supervisor_email="b@x.com",
        ),
    )

    assert report.results[0].success is True
    assert report.results[0].diagnostics.teardown_failure_count == 1
    assert "teardown timed out" in (
        report.results[0].diagnostics.teardown_failure_detail or ""
    )
    assert report.teardown_failure_count == 1
    assert report.teardown_failure_rate == 1.0
    assert report.infra_failure_rate == 1.0


def test_terminate_escalates_to_process_group_sigkill(monkeypatch: pytest.MonkeyPatch) -> None:
    killed_groups: list[tuple[int, int]] = []

    class _TermIgnoringProcess:
        pid = 4321

        def __init__(self) -> None:
            self.waits = 0
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            return None

        def wait(self, timeout: float) -> int:
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired(cmd=["env-host"], timeout=timeout)
            return 0

    def fake_getpgid(pid: int) -> int:
        assert pid == 4321
        return 9876

    def fake_killpg(pgid: int, sig: int) -> None:
        killed_groups.append((pgid, sig))

    proc = _TermIgnoringProcess()
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(sandbox_mod.os, "getpgid", fake_getpgid, raising=False)
    monkeypatch.setattr(sandbox_mod.os, "killpg", fake_killpg, raising=False)

    sandbox_mod._terminate(proc)

    assert proc.terminated is True
    assert killed_groups == [(9876, signal.SIGKILL)]


def test_wait_for_socket_times_out_when_stdout_readline_blocks() -> None:
    class _BlockingStdout:
        def readline(self) -> str:
            threading.Event().wait()
            return ""

    class _NeverReadyEnvProc:
        stdout = _BlockingStdout()
        returncode = None

        def poll(self) -> None:
            return None

    sandbox = sandbox_mod.AppWorldSandbox(
        "hang",
        SandboxConfig(ready_timeout_s=0.05),
    )
    sandbox._env_proc = _NeverReadyEnvProc()

    started = time.monotonic()
    with pytest.raises(SandboxError, match="env host did not become READY"):
        sandbox._wait_for_socket()

    assert time.monotonic() - started < 1.0


def test_clean_scripted_run_keeps_primary_score_and_diagnostics_deterministic() -> None:
    def run_once() -> TaskRunResult:
        sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
        return run_task(sandbox, sa.ScriptedSolverAgent("fac291d_1"), "fac291d_1")

    first = run_once()
    second = run_once()
    report = bench.aggregate([first])

    assert [item.value for item in TaskOutcome] == [
        "success",
        "failure",
        "cap_exceeded",
        "no_final_answer",
        "harness_error",
    ]
    assert first.success is True
    assert first.outcome == TaskOutcome.SUCCESS
    assert report.agentic_success_rate == 1.0
    assert report.asr_excluding_infra == 1.0
    assert json.dumps(first.diagnostics.as_dict(), sort_keys=True) == json.dumps(
        second.diagnostics.as_dict(),
        sort_keys=True,
    )


def _fac_blocks() -> tuple[str, ...]:
    """Expose the scripted fac291d block program for the recovery-path agents."""
    return sa._FAC291D_BLOCKS


# ==============================================================================================
# GATE 1 (gauntlet) — harness-block audit + canary-through-loop DRIVER (host-agnostic parts)
# ==============================================================================================
# The audit + the parse-step of the canary driver are pure (no bwrap/appworld/model), so they run
# in CI here. The full 55-canary-through-the-real-sandbox gate is the WSL test
# ``test_appworld_protocol_c_gauntlet.py::test_gate1_all_canaries_blocked_through_the_full_loop``.
sys.path.insert(0, str(_REPO / "cli" / "tools"))


def test_gate1_harness_block_audit_passes_host_agnostic() -> None:
    import appworld_canary_through_loop as ctl

    ok, findings = ctl.audit_harness_blocks()
    assert ok, "harness-block audit FAILED:\n" + "\n".join(findings)
    # No finding may be a FAIL (WARN is tolerated but we expect none here).
    assert not any(f.startswith("FAIL") for f in findings), findings


def test_gate1_run_block_call_args_are_constants_or_parsed_code() -> None:
    """The loop hands run_block ONLY a constant or parse_turn's parsed.code — never a model f-string."""
    import appworld_canary_through_loop as ctl
    from localbench.scoring.agentic_exec import protocol_c_loop as loop

    src = Path(loop.__file__).read_text(encoding="utf-8")
    args = ctl._run_block_call_args(src)
    assert set(args) == {"code", "_READBACK_CODE", "parsed.code"}, args


def test_gate1_canary_driver_goes_through_parse_turn() -> None:
    """The canary driver routes a benign block through parse_turn -> run_block (the loop path)."""
    import appworld_canary_through_loop as ctl

    sandbox = FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    # A benign, well-formed block should reach run_block and return its stdout.
    out = ctl._drive_through_loop_parse(sandbox, "print('hello-canary-driver')")
    assert "hello-canary-driver" in out
    assert sandbox.run_blocks == ["print('hello-canary-driver')"]  # parse_turn extracted the body


def test_gate1_canary_driver_parser_rejection_never_executes() -> None:
    """A turn the loop's parser would REJECT (no fence) never reaches run_block (cannot escape)."""
    import appworld_canary_through_loop as ctl

    sandbox = FakeSandbox(gold_answer=1, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    # Feed RAW code (no fence) the way _drive sees a canary whose own code lacks a fence: the
    # driver wraps it in a fence, so this is actually well-formed. To exercise rejection, give a
    # payload that, once fenced, yields >1 block (a nested fence) — parse_turn rejects it.
    nested = "print('a')\n```\n```python\nprint('b')"
    out = ctl._drive_through_loop_parse(sandbox, nested)
    # parse_turn saw two blocks -> rejected -> synthetic traceback, and NOTHING ran in the sandbox.
    assert "Traceback" in out and "BlockFormatError" in out
    assert sandbox.run_blocks == []  # the jail was never entered for a rejected turn


# ==============================================================================================
# finalization provenance (direct-finalize descriptor + answer hash) in the per-task record
# ==============================================================================================


def test_loop_records_finalization_provenance_when_sandbox_advertises_it() -> None:
    # Given: a sandbox that advertises the direct-finalize descriptor (as the real ones do).
    class _ProvenancedSandbox(FakeSandbox):
        def finalization_provenance(self) -> dict:
            return dict(sandbox_mod.FINALIZATION_PROVENANCE)

    sandbox = _ProvenancedSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    # When: the loop finalizes through it.
    result = run_task(sandbox, sa.ScriptedSolverAgent("fac291d_1"), "fac291d_1")

    # Then: the per-task record carries the descriptor + sha256 of the read-back answer bytes.
    import hashlib

    fin = result.diagnostics.finalization
    assert fin is not None
    assert fin["path"] == "orchestrator-direct-envhost-stdin-v1"
    assert fin["runner_in_verdict_path"] is False
    assert fin["finalize_correlation"] == "finalize_id+pinned_task+one_shot"
    expected = hashlib.sha256(
        json.dumps(5, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()
    assert fin["answer_hash"] == expected
    # And: it survives serialisation into the per-task record dict (funnel run JSON path).
    assert result.diagnostics.as_dict()["finalization"]["answer_hash"] == expected


def test_loop_finalization_provenance_is_none_for_plain_sandboxes() -> None:
    # Given / When: a sandbox with no descriptor (test doubles, hypothetical legacy paths).
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    result = run_task(sandbox, sa.ScriptedSolverAgent("fac291d_1"), "fac291d_1")

    # Then: the field is present-but-null, never fabricated.
    assert result.diagnostics.finalization is None
    assert result.diagnostics.as_dict()["finalization"] is None


# ==============================================================================================
# endpoint transport failures retain the frozen recoverable-turn semantics
# ==============================================================================================


class _DeadEndpointModel:
    """Model client double: every complete() is a client transport error."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: object, params: object) -> ModelResponse:
        self.calls += 1
        return ModelResponse(
            text="", finish_reason="error", output_tokens=0,
            error_detail="http_status=404: File Not Found",
        )


def test_loop_keeps_endpoint_failures_recoverable_through_turn_cap() -> None:
    # Given: a sandbox that bootstraps fine but a model endpoint that never answers.
    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")
    model = _DeadEndpointModel()

    direct_result = run_task(sandbox, model, "fac291d_1")
    assert model.calls == LoopConfig().max_turns
    assert direct_result.outcome == TaskOutcome.CAP_EXCEEDED

    result = bench.run_appworld_c_benchmark(
        ["fac291d_1"],
        model_factory=lambda task_id: _DeadEndpointModel(),
        sandbox_factory=lambda task_id: FakeSandbox(
            gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com"
        ),
    ).results[0]
    assert result.outcome == TaskOutcome.CAP_EXCEEDED


def test_loop_does_not_abort_on_midtask_client_errors() -> None:
    # Given: a model whose FIRST turn succeeds (runs a block), then the endpoint dies.
    class _DiesAfterFirstTurn:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages: object, params: object) -> ModelResponse:
            self.calls += 1
            if self.calls == 1:
                return ModelResponse(text="```python\nprint('warm')\n```", finish_reason="stop")
            return ModelResponse(
                text="", finish_reason="error", output_tokens=0, error_detail="URLError: refused"
            )

    sandbox = FakeSandbox(gold_answer=5, instruction=_FAC_INSTR, supervisor_email="b@x.com")

    # When: running the task to the cap.
    result = run_task(sandbox, _DiesAfterFirstTurn(), "fac291d_1")

    # Then: the documented per-turn degradation holds (no abort — one turn DID succeed), the
    # task ends cap_exceeded, and the client cause is preserved on the degraded turn records.
    assert result.outcome == TaskOutcome.CAP_EXCEEDED
    error_turns = [t for t in result.diagnostics.turns if t.finish_reason == "error"]
    assert error_turns
    assert all(t.error_detail == "URLError: refused" for t in error_turns)
