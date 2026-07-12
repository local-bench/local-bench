from __future__ import annotations

from typing import Final

from localbench.scorers.bfcl_multi_turn._prompt import build_bfcl_multi_turn_prompt
from localbench.scorers.bfcl_multi_turn._types import FailureKind
from localbench.scorers.bfcl_multi_turn.scorer import score_bfcl_multi_turn

BFCL_MULTI_TURN_BENCHES: Final = frozenset(
    {
        "bfcl_multi_turn",
        "bfcl_multi_turn_base",
        "bfcl_multi_turn_long_context",
    }
)

__all__ = [
    "BFCL_MULTI_TURN_BENCHES",
    "FailureKind",
    "build_bfcl_multi_turn_prompt",
    "score_bfcl_multi_turn",
]
