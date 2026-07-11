"""Context-local selection for successor and immutable legacy execution contracts."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from localbench.scoring.agentic_exec.execution_contract import CONTRACT_ID

_ACTIVE_CONTRACT: ContextVar[tuple[Path | None, str] | None] = ContextVar(
    "localbench_active_execution_contract", default=None
)


def active_execution_contract(path: Path | None) -> tuple[Path | None, str]:
    active = _ACTIVE_CONTRACT.get() if path is None else None
    return active if active is not None else (path, CONTRACT_ID)


@contextmanager
def execution_contract_scope(
    path: Path | None, *, expected_contract_id: str
) -> Iterator[None]:
    """Select one signed contract for every nested scored-execution choke point."""
    token = _ACTIVE_CONTRACT.set((path, expected_contract_id))
    try:
        yield
    finally:
        _ACTIVE_CONTRACT.reset(token)
