"""Parse one assistant turn under Protocol C: exactly ONE python code block per turn.

Protocol C (LOCKED design): the model emits EXACTLY ONE fenced ``python`` code block per
turn; the harness runs that block via the sandbox and feeds back the captured stdout. This
module turns raw assistant text into either:

  * a :class:`TurnAction` carrying the single extracted code block (and whether the model
    signalled a final answer), or
  * a :class:`BlockFormatError` describing the formatting violation (0 or >1 blocks, empty
    block) together with a corrective message the loop feeds back as the next observation.

Final-answer mechanism (harness-detected, model-safe):
  ``complete_task`` is harness-owned and the sandbox forbids the model calling it. So the
  model signals "this is my final answer" by binding a variable named ``answer`` in its
  code block AND emitting a sentinel line ``FINAL_ANSWER`` on its own line (outside the
  fence, or as a trailing marker). The harness runs the block (so ``answer`` is bound in
  the persistent namespace), reads ``answer`` back out, and calls ``sandbox.finalize``.
  We accept the sentinel either as a standalone line or as ``# FINAL_ANSWER`` so models
  that keep all prose inside comments still finalize.

Pure / import-safe: no AppWorld, no sandbox, no model — just text in, structured out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The sentinel the model emits to tell the harness "finalize with my `answer` variable".
# Matched on a line of its own (optionally as a comment, optionally trailing whitespace).
FINAL_ANSWER_SENTINEL = "FINAL_ANSWER"

# A fenced code block whose info-string is python (``python`` / ``py``) OR bare ``` ``` ```.
# We capture the body. ``re.DOTALL`` so the body may span lines; non-greedy so we get each
# block separately when counting. Info string is case-insensitive and tolerates whitespace.
_FENCE_RE = re.compile(
    r"```[ \t]*(?P<lang>[A-Za-z0-9_+-]*)[ \t]*\r?\n(?P<body>.*?)\r?\n?```",
    re.DOTALL,
)

# Languages we treat as a runnable python block. A fence with no info string counts too
# (many models drop the ``python`` tag); a fence tagged with a different language (``json``,
# ``bash``) does NOT count as the code block and is ignored for extraction.
_PYTHON_LANGS = frozenset({"", "python", "py", "python3"})


@dataclass(frozen=True, slots=True)
class TurnAction:
    """The single code block extracted from a well-formed assistant turn."""

    code: str
    is_final: bool


@dataclass(frozen=True, slots=True)
class BlockFormatError:
    """A formatting violation in the assistant turn, with a corrective observation.

    ``kind`` is a stable machine label for diagnostics; ``message`` is the human/agent-facing
    corrective text the loop appends as the next observation so the model can self-repair.
    """

    kind: str  # "no_block" | "multiple_blocks" | "empty_block"
    message: str


# Result of parsing one turn: either an action or a format error (never both).
ParseResult = TurnAction | BlockFormatError


def _iter_python_blocks(text: str) -> list[str]:
    """Return the bodies of all fenced blocks whose language is python-ish (or untagged)."""
    blocks: list[str] = []
    for m in _FENCE_RE.finditer(text):
        lang = (m.group("lang") or "").lower()
        if lang in _PYTHON_LANGS:
            blocks.append(m.group("body"))
    return blocks


def _has_final_sentinel(text: str, code: str) -> bool:
    """True if the final-answer sentinel appears as its own (optionally commented) line.

    Checked across the WHOLE assistant message (so a model may place the sentinel outside
    the fence) and also inside the extracted ``code`` (so a model may keep it as a trailing
    ``# FINAL_ANSWER`` comment). Must be a standalone token on its line to avoid matching it
    inside unrelated prose.
    """
    pattern = re.compile(
        rf"^[ \t]*#?[ \t]*{re.escape(FINAL_ANSWER_SENTINEL)}[ \t]*$",
        re.MULTILINE,
    )
    return bool(pattern.search(text) or pattern.search(code))


def parse_turn(assistant_text: str) -> ParseResult:
    """Parse one Protocol C assistant turn into an action or a corrective format error."""
    blocks = _iter_python_blocks(assistant_text)

    if len(blocks) == 0:
        return BlockFormatError(
            kind="no_block",
            message=(
                "FORMAT ERROR: your message contained no ```python code block. Reply with "
                "EXACTLY ONE fenced python code block, e.g.\n```python\n"
                "result = apis.supervisor.show_active_task()\nprint(result)\n```\n"
                "Write only that one block this turn."
            ),
        )
    if len(blocks) > 1:
        return BlockFormatError(
            kind="multiple_blocks",
            message=(
                f"FORMAT ERROR: your message contained {len(blocks)} python code blocks. "
                "Reply with EXACTLY ONE ```python code block per turn. Combine your code "
                "into a single block, print what you need to observe, and continue next turn."
            ),
        )

    code = blocks[0]
    if not code.strip():
        return BlockFormatError(
            kind="empty_block",
            message=(
                "FORMAT ERROR: your ```python code block was empty. Put runnable Python "
                "inside the block (call an api and print the result)."
            ),
        )

    return TurnAction(code=code, is_final=_has_final_sentinel(assistant_text, code))
