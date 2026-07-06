"""Build a synthetic pending-run for the BigCodeBench ground-truth check.

Feeds the upstream canonical solutions (fetched at the exact pinned dataset revision our
frozen items record) through the PRODUCTION artifact path — extraction, sanitization,
assembly — and emits a run record whose coding artifacts are all pending. Executing it with
`localbench code --pending-run` in the hardened sandbox must pass ~everything; a broad
failure means the harness, image, or assembly is wrong, and NOTHING may re-run against the
suite until it is understood. Also cross-checks that each frozen item's test is byte-identical
to upstream at the pinned revision (provenance proof).

Usage (from repo root, needs the hf extra for huggingface_hub):
  uv run --project cli --extra hf python scripts/build_groundtruth_run.py \
      --out runs/groundtruth/bcb-groundtruth.pending.json
  # then execute it (WSL, rootless docker):
  #   localbench code --pending-run runs/groundtruth/bcb-groundtruth.pending.json \
  #       --suite-dir suite/v1 --image bigcodebench/bigcodebench-evaluate@sha256:<pinned>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cli" / "src"))

from huggingface_hub import hf_hub_download  # noqa: E402

from localbench.coding_exec.artifacts import code_artifact_for_generation  # noqa: E402

SUITE_FILE = REPO / "suite" / "v1" / "bigcodebench_hard.jsonl"


def load_suite_items() -> list[dict]:
    return [json.loads(line) for line in SUITE_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_upstream(revision: str, split: str) -> dict[str, dict]:
    # The dataset ships one parquet per version tag (data/v0.1.4-00000-of-00001.parquet).
    path = hf_hub_download(
        repo_id="bigcode/bigcodebench-hard",
        repo_type="dataset",
        revision=revision,
        filename=f"data/{split}-00000-of-00001.parquet",
    )
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = table.to_pylist()
    return {row["task_id"]: row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    items = load_suite_items()
    revision = items[0]["source_revision"]
    split = items[0]["source_split"]
    upstream = load_upstream(revision, split)

    run_items = []
    mismatches = 0
    for source_item in items:
        row = upstream.get(source_item["source_id"])
        if row is None:
            print(f"FAIL no upstream row for {source_item['source_id']}")
            mismatches += 1
            continue
        ours = hashlib.sha256(source_item["test"].encode("utf-8")).hexdigest()
        theirs = hashlib.sha256(row["test"].encode("utf-8")).hexdigest()
        if ours != theirs:
            print(f"FAIL test mismatch vs upstream for {source_item['id']} ({source_item['source_id']})")
            mismatches += 1
            continue
        solution = row.get("canonical_solution") or ""
        # BigCodeBench canonical solutions are bodies that complete code_prompt; the runnable
        # ground truth is code_prompt + canonical_solution, fed through the production
        # extractor as a fenced block exactly like a model reply.
        program = f"{row.get('code_prompt', '')}{solution}"
        response_text = f"```python\n{program}\n```"
        benchmark_item = {"messages": [{"role": "user", "content": source_item.get("instruct_prompt", "")}]}
        artifact = code_artifact_for_generation(source_item, benchmark_item, {"response_text": response_text})
        if artifact["sanitized_code"] is None:
            print(f"FAIL extraction returned no code for {source_item['id']}")
            mismatches += 1
            continue
        run_items.append(
            {
                "id": source_item["id"],
                "bench": "bigcodebench_hard",
                "code_artifact": artifact,
            }
        )

    if mismatches:
        print(f"{mismatches} provenance/extraction failures — NOT writing a run file")
        return 1

    run = {
        "schema": "localbench-groundtruth-pending-v1",
        "purpose": "bigcodebench ground-truth check: canonical solutions must pass in the sandbox",
        "items": run_items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(run, indent=1), encoding="utf-8")
    print(f"OK wrote {len(run_items)} pending ground-truth items -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
