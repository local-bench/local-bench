# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# ─── How to run ───
# uv run --project cli python cli/tests/agentic_journal_process_worker.py JOURNAL PHASE IDENTITY_JSON

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from localbench.scoring.agentic_exec.task_journal import (
    AgenticResumeIdentity,
    TaskAttemptKey,
    TaskJournal,
)
from localbench.scoring.agentic_exec.task_journal_format import encode_frame
from localbench.submissions.canon import canonical_json_hash


def _accepted_payload(key: TaskAttemptKey) -> dict[str, object]:
    accepted: dict[str, object] = {
        "result": {
            "task_id": key.task_id,
            "success": True,
            "outcome": "success",
            "collateral_damage": False,
        },
        "diagnostics": {
            "task_id": key.task_id,
            "outcome": "success",
            "success": True,
            "fixture_origin": "DERIVED: crash framing does not execute live WSL",
        },
        "attestation": None,
        "identity": {"task_id": key.task_id, "run_index": key.run_index},
        "attempt_number": key.attempt_number,
    }
    return {**accepted, "payload_sha256": canonical_json_hash(accepted)}


def _commit(journal: TaskJournal, run_index: int) -> None:
    key = TaskAttemptKey("a30375d_1", run_index, 1)
    journal.append_attempt_started(
        key,
        contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
        identity_ref="a" * 64,
    )
    journal.append_result_committed(
        key,
        result={
            "task_id": key.task_id,
            "success": True,
            "outcome": "success",
            "collateral_damage": False,
        },
        diagnostics={
            "task_id": key.task_id,
            "outcome": "success",
            "success": True,
            "fixture_origin": "DERIVED: crash framing does not execute live WSL",
        },
        attestation=None,
    )


def main() -> None:
    path = Path(sys.argv[1])
    phase = sys.argv[2]
    identity = AgenticResumeIdentity(**json.loads(sys.argv[3]))
    journal = TaskJournal.open(path, identity)
    first = TaskAttemptKey("a30375d_1", 1, 1)
    if phase in {"before_model_call", "mid_turn", "after_verdict"}:
        journal.append_attempt_started(
            first,
            contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
            identity_ref="a" * 64,
        )
    elif phase == "during_commit":
        journal.append_attempt_started(
            first,
            contract_id="agentic-execution-contract-aw013p1-pypi28113a7a-v3",
            identity_ref="a" * 64,
        )
        document = {
            "schema": journal.schema_id,
            "version": 1,
            "sequence": 2,
            "previous_sha256": journal.records[-1].payload_sha256,
            "record_type": "attempt_result_committed",
            "payload": {"envelope": _accepted_payload(first)},
        }
        frame = encode_frame(document)
        journal._handle.write(frame[: len(frame) // 2])
        journal._handle.flush()
        os.fsync(journal._handle.fileno())
    elif phase == "after_commit":
        _commit(journal, 1)
    elif phase == "between_run_1_run_2":
        _commit(journal, 1)
        journal.append_run_boundary(1)
    elif phase in {"before_third_run_decision", "after_third_run_decision"}:
        _commit(journal, 1)
        journal.append_run_boundary(1)
        _commit(journal, 2)
        journal.append_run_boundary(2)
        if phase == "after_third_run_decision":
            journal.append_third_run_decision(
                trigger_value=7.0,
                threshold_pp=5.0,
                decision=True,
                evidence={"asr_series": [0.50, 0.57]},
            )
    else:
        raise RuntimeError(f"unknown crash phase: {phase}")
    print("ready", flush=True)
    time.sleep(300)


if __name__ == "__main__":
    main()
