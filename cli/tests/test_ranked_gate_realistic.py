"""Regression tests for the two v3 ranked-gate bugs the first real 6-axis run exposed
(2026-07-06). Both were hidden because the board fixtures use synthetic data that never
exercised _ranked_v3 with REALISTIC agentic (no per-item token budget) or AST-rejected
coding items. These tests use realistic shapes so the bugs cannot regress.
"""
from __future__ import annotations

from localbench.orchestrate import _budget_audit
from localbench.scoring.board_scoring import _coding_item_trustworthy


def _static_item(bench: str, *, max_tokens: int | None, total: int) -> dict:
    return {
        "bench": bench,
        "id": f"{bench}-1",
        "max_tokens": max_tokens,
        "generated_tokens": {"total": total},
    }


def _agentic_item() -> dict:
    # Real appworld_c items carry no single per-item token budget (multi-turn).
    return {"bench": "appworld_c", "id": "scenario1_1", "max_tokens": None, "generated_tokens": None}


def test_budget_audit_excludes_agentic_items() -> None:
    # A run whose only "unverified" items are agentic must still audit as exact: agentic tasks
    # are multi-turn and not part of the per-item token-budget audit.
    items = [
        _static_item("mmlu_pro", max_tokens=16384, total=100),
        _static_item("bigcodebench_hard", max_tokens=16384, total=5000),
        *[_agentic_item() for _ in range(3)],
    ]
    audit = _budget_audit(items)
    assert audit["status"] == "exact"
    assert audit["excluded_agentic_items"] == 3
    assert audit["unverified_items"] == 0
    assert "appworld_c" not in audit["per_bench"]  # agentic is not budget-audited


def test_budget_audit_still_flags_static_item_without_max_tokens() -> None:
    # Guard against over-broadening: a BUDGET-BEARING (static) item missing its budget is a real
    # anomaly and must remain "unverified" — the fix only excuses the agentic axis.
    items = [
        _static_item("mmlu_pro", max_tokens=16384, total=100),
        {"bench": "ifbench", "id": "ifbench-1", "max_tokens": None, "generated_tokens": None},
    ]
    audit = _budget_audit(items)
    assert audit["status"] == "unverified"
    assert audit["unverified_items"] == 1


def test_budget_audit_flags_real_breach() -> None:
    items = [_static_item("mmlu_pro", max_tokens=100, total=200)]
    assert _budget_audit(items)["status"] == "breached"


def test_coding_item_trustworthy_verifier_executed() -> None:
    item = {"correct": True, "code_artifact": {"verdict_source": "verifier", "verdict": {"passed": True}}}
    assert _coding_item_trustworthy(item) is True


def test_coding_item_trustworthy_ast_rejected_is_verified_fail() -> None:
    # A deterministically AST-rejected item never reaches the sandbox; it is a trustworthy FAIL.
    item = {
        "correct": False,
        "failure_kind": "coding_ast_rejected",
        "code_artifact": {
            "verdict_source": None,
            "verdict": None,
            "conformance_status": {"status": "failed", "failure": "coding_ast_rejected"},
        },
    }
    assert _coding_item_trustworthy(item) is True


def test_coding_item_trustworthy_no_code_is_verified_fail() -> None:
    item = {
        "correct": False,
        "code_artifact": {"verdict_source": None, "extraction_status": {"status": "no_code", "failure": "empty"}},
    }
    assert _coding_item_trustworthy(item) is True


def test_coding_item_trustworthy_rejects_silent_gap() -> None:
    # No verifier verdict AND no deterministic disposition = a silent gap; must NOT be trusted,
    # even though it is a fail. (This is the anti-loophole guard.)
    item = {"correct": False, "code_artifact": {"verdict_source": None}}
    assert _coding_item_trustworthy(item) is False


def test_coding_item_trustworthy_rejects_unexecuted_nonfail() -> None:
    # An item claiming correct without a verifier verdict must never be trusted.
    item = {
        "correct": True,
        "code_artifact": {"verdict_source": None, "conformance_status": {"failure": "coding_ast_rejected"}},
    }
    assert _coding_item_trustworthy(item) is False


def test_coding_item_trustworthy_rejects_non_dict_artifact() -> None:
    assert _coding_item_trustworthy({"correct": False, "code_artifact": None}) is False
