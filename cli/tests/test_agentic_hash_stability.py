from __future__ import annotations

from localbench.scoring.agentic_exec.config import AgenticExecConfig
from localbench.scoring.agentic_exec.hashing import (
    ScorecardTaskIdentity,
    scorecard_identity_hash,
    transcript_sha256,
)


def test_transcript_hash_is_stable_for_canonical_json() -> None:
    # Given equivalent transcript JSON with different key order.
    first = [{"b": 2, "a": 1.23456789}]
    second = [{"a": 1.23456789, "b": 2}]

    # When hashing transcripts.
    first_hash = transcript_sha256(first)
    second_hash = transcript_sha256(second)

    # Then canonicalization makes the digest stable.
    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_transcript_hash_changes_when_transcript_changes() -> None:
    # Given two different transcripts.
    first = [{"tool": "orders.get_order", "arguments": {"order_id": "o-100"}}]
    second = [{"tool": "orders.get_order", "arguments": {"order_id": "o-101"}}]

    # When hashing them.
    # Then the digest changes with the canonical transcript content.
    assert transcript_sha256(first) != transcript_sha256(second)


def test_scorecard_identity_hash_is_stable_and_budget_sensitive() -> None:
    # Given a scorecard identity payload.
    tasks = (
        ScorecardTaskIdentity(
            task_id="stub_read_order_total",
            family="read_lookup_exact_answer",
            band="appworld_level_1",
        ),
    )
    config = AgenticExecConfig()

    # When hashing equivalent inputs twice.
    first = scorecard_identity_hash(config=config, tasks=tasks)
    second = scorecard_identity_hash(config=config, tasks=tasks)

    # Then the digest is stable and moves when a budget changes.
    assert first == second
    assert len(first) == 64
    assert first != scorecard_identity_hash(
        config=AgenticExecConfig(max_tool_calls=12),
        tasks=tasks,
    )
