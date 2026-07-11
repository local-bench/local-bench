"""Build and sign the canonical C0 agentic execution contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from localbench.scoring.agentic_exec import task_pool
from localbench.scoring.agentic_exec.execution_contract import (
    extract_contract_payload,
    write_signed_contract,
)
from localbench.scoring.agentic_exec.wsl_worker import collect_identity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appworld-root", required=True, type=Path)
    parser.add_argument("--task-ids-from", required=True, type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    task_ids = _task_ids(args.task_ids_from)
    identity = collect_identity(str(args.appworld_root))
    semantic_contents = task_pool.load_semantic_task_contents(task_ids, root=args.appworld_root)
    payload = extract_contract_payload(
        ordered_task_ids=task_ids,
        semantic_task_contents=semantic_contents,
        appworld_identity={
            "appworld_version": identity["appworld_version"],
            "python_version": identity["python_version"],
            "env_pins": identity["env_pins"],
        },
        sandbox_identity={
            "bubblewrap_sha256": identity["bwrap_sha256"],
            "bubblewrap_version": identity["bwrap_version"],
            "appworld_root_filesystem": identity["appworld_root_filesystem"],
            "worker_content_sha256": identity["worker_content_sha256"],
        },
    )
    write_signed_contract(args.out, payload, args.signing_key)
    return 0


def _task_ids(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    subset = document.get("subset") if isinstance(document, dict) else None
    task_ids = subset.get("task_ids") if isinstance(subset, dict) else None
    if not isinstance(task_ids, list) or not all(isinstance(item, str) for item in task_ids):
        raise ValueError(f"{path} does not contain subset.task_ids")
    return task_ids


if __name__ == "__main__":
    raise SystemExit(main())
