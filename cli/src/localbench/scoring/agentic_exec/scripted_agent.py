"""Deterministic, NON-LLM agents implementing the ``ModelClient`` contract.

These hand-written policies emit valid Protocol C turns (one fenced ```python block each) so
the loop mechanics + diagnostics can be exercised end-to-end with NO model and NO GPU. They
are the test analogue of a real chat-completions client: same interface
(:meth:`ModelClient.complete`), swapped implementation.

Policies provided:
  * :class:`ScriptedSolverAgent` — solves real dev tasks (``fac291d_1``, ``50e1ac9_1``)
    through the loop by walking a fixed list of code blocks, then binding ``answer`` and
    emitting ``FINAL_ANSWER``. It detects WHICH task from the instruction text in the system
    prompt (proving the loop passes the instruction through), and advances by counting its own
    prior turns in the history (so it is a pure function of the history — deterministic).
  * :class:`BadFormatAgent` — emits malformed turns (no block / two blocks) to test the
    format-failure -> corrective-observation path, optionally recovering afterwards.
  * :class:`NeverFinalizeAgent` — emits valid no-op blocks forever to test ``cap_exceeded``.

Pure / import-safe: imports only the model-client contract + block fence/sentinel constants.
"""

from __future__ import annotations

from localbench._types import ChatMessage
from localbench.scoring.agentic_exec.block_parser import FINAL_ANSWER_SENTINEL
from localbench.scoring.agentic_exec.model_client import (
    GenerationParams,
    ModelResponse,
)


def _fence(code: str) -> str:
    """Wrap code in a single python fence (a well-formed Protocol C turn body)."""
    return f"```python\n{code}\n```"


def _final(code: str) -> str:
    """A final turn: the code block (binding ``answer``) plus the sentinel on its own line."""
    return _fence(code) + f"\n{FINAL_ANSWER_SENTINEL}"


def _count_assistant_turns(messages: list[ChatMessage]) -> int:
    """How many assistant turns are already in the history (0 on the first call)."""
    return sum(1 for m in messages if m["role"] == "assistant")


def _system_text(messages: list[ChatMessage]) -> str:
    for m in messages:
        if m["role"] == "system":
            return m["content"]
    return ""


# ----------------------------------------------------------------------------------------------
# Code blocks per task. These mirror the agent-reachable gold paths proven by the scripted-solve
# tool (auth via supervisor passwords + spotify.login; genre/top_k parsed from the instruction;
# full pagination). They are written as multi-line program text the loop sends to run_block.
# ----------------------------------------------------------------------------------------------

# fac291d_1: count UNIQUE songs across the user's song/album/playlist libraries.
_FAC291D_BLOCKS: tuple[str, ...] = (
    # turn 1: authenticate and peek the song-library page shape.
    "prof = apis.supervisor.show_profile()\n"
    "pwds = apis.supervisor.show_account_passwords()\n"
    "spw = next(p['password'] for p in pwds if p['account_name'] == 'spotify')\n"
    "token = apis.spotify.login(username=prof['email'], password=spw)['access_token']\n"
    "page0 = apis.spotify.show_song_library(access_token=token, page_index=0)\n"
    "print('auth ok; first page len', len(page0))",
    # turn 2: sweep the song library for direct song_ids.
    "song_ids = set()\n"
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_song_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    song_ids |= {s['song_id'] for s in pg}\n"
    "    pi += 1\n"
    "print('after song lib', len(song_ids))",
    # turn 3: add album + playlist library song_ids and compute the count into `answer`.
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_album_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    for al in pg:\n"
    "        song_ids |= set(al['song_ids'])\n"
    "    pi += 1\n"
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_playlist_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    for pl in pg:\n"
    "        song_ids |= set(pl['song_ids'])\n"
    "    pi += 1\n"
    "answer = len(song_ids)\n"
    "print('final unique', answer)",
)

# 50e1ac9_1: top-K most played <genre> song titles across song/album/playlist libraries.
_50E1AC9_BLOCKS: tuple[str, ...] = (
    # turn 1: auth + parse genre/top_k from the instruction (NOT from gold files).
    "prof = apis.supervisor.show_profile()\n"
    "pwds = apis.supervisor.show_account_passwords()\n"
    "spw = next(p['password'] for p in pwds if p['account_name'] == 'spotify')\n"
    "token = apis.spotify.login(username=prof['email'], password=spw)['access_token']\n"
    "task = apis.supervisor.show_active_task()\n"
    "instr = task['instruction'].lower()\n"
    "import re as _re\n"
    "m = _re.search(r'top (\\d+)', instr)\n"
    "top_k = int(m.group(1)) if m else 4\n"
    "genre = 'R&B' if 'r&b' in instr else None\n"
    "print('auth ok; top_k', top_k, 'genre', genre)",
    # turn 2: collect candidate song_ids from all three libraries.
    "song_ids = []\n"
    "seen = set()\n"
    "def _add(sid):\n"
    "    if sid not in seen:\n"
    "        seen.add(sid); song_ids.append(sid)\n"
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_song_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    for s in pg:\n"
    "        _add(s['song_id'])\n"
    "    pi += 1\n"
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_album_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    for al in pg:\n"
    "        info = apis.spotify.show_album(album_id=al['album_id'])\n"
    "        for so in info['songs']:\n"
    "            _add(so['id'])\n"
    "    pi += 1\n"
    "pi = 0\n"
    "while True:\n"
    "    pg = apis.spotify.show_playlist_library(access_token=token, page_index=pi)\n"
    "    if not pg:\n"
    "        break\n"
    "    for pl in pg:\n"
    "        info = apis.spotify.show_playlist(access_token=token, playlist_id=pl['playlist_id'])\n"
    "        for so in info['songs']:\n"
    "            _add(so['id'])\n"
    "    pi += 1\n"
    "print('candidate songs', len(song_ids))",
    # turn 3: per-song genre/play_count, filter, sort desc, top_k, join titles into `answer`.
    "title_to_count = {}\n"
    "for sid in song_ids:\n"
    "    s = apis.spotify.show_song(song_id=sid)\n"
    "    if s.get('genre') == genre:\n"
    "        title_to_count[s['title']] = s['play_count']\n"
    "ranked = sorted(title_to_count.items(), key=lambda x: x[1], reverse=True)[:top_k]\n"
    "answer = ', '.join(t for t, _ in ranked)\n"
    "print('built answer:', answer)",
)

# Map a task to its block program. Selection is by task_id (the agent is constructed per task)
# with an instruction-text fallback so the policy still works if only the prompt is available.
_TASK_BLOCKS: dict[str, tuple[str, ...]] = {
    "fac291d_1": _FAC291D_BLOCKS,
    "50e1ac9_1": _50E1AC9_BLOCKS,
}


class ScriptedSolverAgent:
    """A deterministic agent that solves a known dev task through the Protocol C loop.

    Constructed with the ``task_id`` so the benchmark's ``model_factory`` can build the right
    policy per task. On each ``complete`` it returns the next code block; the last block binds
    ``answer`` and the turn carries the ``FINAL_ANSWER`` sentinel.
    """

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id

    def _blocks(self, messages: list[ChatMessage]) -> tuple[str, ...]:
        if self._task_id in _TASK_BLOCKS:
            return _TASK_BLOCKS[self._task_id]
        # Fallback: infer from the instruction embedded in the system prompt.
        sys_text = _system_text(messages).lower()
        if "most played" in sys_text or "top " in sys_text:
            return _50E1AC9_BLOCKS
        return _FAC291D_BLOCKS

    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        blocks = self._blocks(messages)
        step = _count_assistant_turns(messages)  # 0-based index of the turn we're producing
        if step >= len(blocks):
            # Defensive: if asked for more turns than we have blocks, re-emit the final block.
            step = len(blocks) - 1
        code = blocks[step]
        is_last = step == len(blocks) - 1
        text = _final(code) if is_last else _fence(code)
        return ModelResponse(text=text, finish_reason="stop")


class BadFormatAgent:
    """Emits malformed turns to exercise the format-failure -> corrective path.

    ``mode``:
      * ``"no_block"``        — reply with prose only (no code block), forever or until recover.
      * ``"multiple_blocks"`` — reply with two python blocks.
    If ``recover_with`` is given, AFTER ``bad_turns`` malformed turns the agent emits that final
    solving sequence so a test can assert the loop recovers post-correction.
    """

    def __init__(
        self,
        mode: str = "no_block",
        bad_turns: int = 1,
        recover_blocks: tuple[str, ...] | None = None,
    ) -> None:
        self._mode = mode
        self._bad_turns = bad_turns
        self._recover_blocks = recover_blocks or ()

    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        step = _count_assistant_turns(messages)
        if step < self._bad_turns:
            if self._mode == "multiple_blocks":
                text = _fence("print('a')") + "\n" + _fence("print('b')")
            else:  # no_block
                text = "I will now think about the task, but here is no code block at all."
            return ModelResponse(text=text, finish_reason="stop")
        # recovery phase (optional)
        rec_index = step - self._bad_turns
        if rec_index < len(self._recover_blocks):
            code = self._recover_blocks[rec_index]
            is_last = rec_index == len(self._recover_blocks) - 1
            return ModelResponse(
                text=_final(code) if is_last else _fence(code), finish_reason="stop"
            )
        # nothing left to do; emit a harmless block (keeps the loop progressing in tests).
        return ModelResponse(text=_fence("print('idle')"), finish_reason="stop")


class NeverFinalizeAgent:
    """Emits a valid no-op block every turn and never finalizes — to test ``cap_exceeded``."""

    def complete(
        self, messages: list[ChatMessage], params: GenerationParams
    ) -> ModelResponse:
        step = _count_assistant_turns(messages)
        return ModelResponse(text=_fence(f"print('still working, turn {step + 1}')"),
                             finish_reason="stop")
