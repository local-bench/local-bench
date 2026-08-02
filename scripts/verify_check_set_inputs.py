# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: cd cli; uv run python ../scripts/verify_check_set_inputs.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "docs" / "v2" / "inputs"
BENCHES = ("bigcodebench_hard", "ifbench", "olymmath_hard", "amo", "tc_json_v1")
CANDIDATES = ("q6k", "udq2", "fusion")
BCB_UNSCOREABLE = frozenset({"bcbh-006", "bcbh-007", "bcbh-014", "bcbh-035", "bcbh-074", "bcbh-096", "bcbh-104"})
INFORMATIVE_COUNTS = {
    "bigcodebench_hard": 38,
    "ifbench": 82,
    "olymmath_hard": 46,
    "amo": 9,
    "tc_json_v1": 23,
}


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def expected_tables(report: str) -> dict[tuple[str, str], tuple[str, ...]]:
    result = {}
    summary = report.split("## Summary report (as printed)\n\n```\n", maxsplit=1)[1].split("\n```", maxsplit=1)[0]
    lines = summary.splitlines()
    for bench in BENCHES:
        header = next((index for index, line in enumerate(lines) if line.startswith(f"### {bench}  ")), None)
        if header is None:
            raise AssertionError(f"missing paired table for {bench}")
        for row in lines[header + 3:header + 6]:
            fields = tuple(part.strip() for part in row.strip("|").split("|"))
            result[(bench, fields[0])] = fields[1:]
    return result


def final_correctness(run: dict, bench: str) -> dict[str, bool]:
    return {
        item["id"]: bool(item.get("correct"))
        for item in run["items"]
        if item.get("bench") == bench
    }


def assert_pinned_hashes(manifest: dict) -> None:
    for bundle, entry in manifest.items():
        root = Path(entry["source_path"])
        for relative_path, expected_hash in entry["sha256"].items():
            actual_hash = sha256(root / relative_path)
            if actual_hash != expected_hash:
                raise AssertionError(f"{bundle}/{relative_path} hash mismatch")


def main() -> None:
    manifest = load_json(INPUTS / "inputs-manifest.json")
    report = (INPUTS / "bundle-mining-results.md").read_text(encoding="utf-8")
    assert_pinned_hashes(manifest)
    expected = expected_tables(report)
    runs = {bundle: load_json(Path(entry["source_path"]) / "localbench-run.json") for bundle, entry in manifest.items()}

    for bench in BENCHES:
        outcomes = {bundle: final_correctness(run, bench) for bundle, run in runs.items()}
        ids = sorted(outcomes["base_q5km"])
        if bench == "bigcodebench_hard":
            ids = [item_id for item_id in ids if item_id not in BCB_UNSCOREABLE]
        n_items = len(ids)
        informative = sum(0 < sum(outcomes[bundle][item_id] for bundle in manifest) < 4 for item_id in ids)
        if informative != INFORMATIVE_COUNTS[bench]:
            raise AssertionError(f"{bench} informative count {informative} != {INFORMATIVE_COUNTS[bench]}")

        base_accuracy = sum(outcomes["base_q5km"][item_id] for item_id in ids) / n_items
        for bundle, run in runs.items():
            accuracy = sum(outcomes[bundle][item_id] for item_id in ids) / n_items
            recorded = run["benches"][bench]["raw_accuracy"]
            if abs(accuracy - recorded) > 1e-9:
                raise AssertionError(f"{bundle}/{bench} accuracy mismatch: {accuracy} != {recorded}")

        for candidate in CANDIDATES:
            candidate_accuracy = sum(outcomes[candidate][item_id] for item_id in ids) / n_items
            drops = sum(outcomes["base_q5km"][item_id] and not outcomes[candidate][item_id] for item_id in ids)
            leaps = sum(not outcomes["base_q5km"][item_id] and outcomes[candidate][item_id] for item_id in ids)
            actual = (
                str(n_items), f"{base_accuracy * 100:.2f}", f"{candidate_accuracy * 100:.2f}",
                f"{(candidate_accuracy - base_accuracy) * 100:+.2f}", str(drops),
                f"{drops / n_items * 100:.2f}", str(leaps), f"{leaps / n_items * 100:.2f}",
                f"{(drops + leaps) / n_items * 100:.2f}",
            )
            if actual != expected[(bench, candidate)]:
                raise AssertionError(f"{bench}/{candidate} paired row differs: {actual} != {expected[(bench, candidate)]}")

    print("PASS: 4 bundles, 5 paired tables, 15 candidate rows, and informative counts verified")


if __name__ == "__main__":
    main()
