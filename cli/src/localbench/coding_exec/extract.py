"""Extract the generated Python from a model response (reasoning-on, instruct lane).

Models reason, then emit a fenced ```python block. We take the LAST fenced code block
(the final answer), preferring an explicit ```python fence. No fence -> no extractable
code -> the task fails as a no-answer (correct: an un-runnable response is wrong).
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def extract_code(response: str | None) -> str | None:
    """Return the generated code from the last (preferably ```python) fenced block."""
    if not response:
        return None
    blocks = [(lang.lower(), body) for lang, body in _FENCE.findall(response)]
    if not blocks:
        return None
    python_blocks = [body for lang, body in blocks if lang in ("python", "py", "python3")]
    chosen = python_blocks[-1] if python_blocks else blocks[-1][1]
    code = chosen.strip("\n")
    return code if code.strip() else None
