from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from localbench._types import JsonObject
from localbench.scoring.scorecard import scorecard_identity
from localbench.suite_resolver import DEFAULT_SUITE_ID, suite_hash

PUBLIC_BENCHES: Final[tuple[str, ...]] = ("mmlu_pro", "ifbench", "tc_json_v1")

@dataclass(frozen=True, slots=True)
class BundleResult:
    path: Path
    suite_hash: str
    sha256sums_path: Path


def assemble_core_text_v1_bundle(source_suite: Path, out_dir: Path) -> BundleResult:
    stage = out_dir / "_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    source_suite = source_suite.resolve()
    source_manifest = _read_json(source_suite / "suite.json")
    source_lock = _read_json(source_suite / "itemsets.lock.json")
    _write_items(source_suite, stage)
    suite = _public_suite(source_suite, source_manifest)
    lock = _public_lock(source_lock)
    _write_json(stage / "suite.json", suite)
    _write_json(stage / "itemsets.lock.json", lock)
    _write_json(stage / "SCORECARD.json", scorecard_identity())
    _write_release_texts(stage, lock)
    public_hash = suite_hash(stage)
    target = out_dir / public_hash
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(stage), target)
    _write_sha256sums(target)
    return BundleResult(
        path=target,
        suite_hash=public_hash,
        sha256sums_path=target / "SHA256SUMS",
    )


def _public_suite(source_suite: Path, source_manifest: JsonObject) -> JsonObject:
    benches = source_manifest.get("benches")
    if not isinstance(benches, dict):
        benches = {}
    public_benches: JsonObject = {}
    for bench_name in PUBLIC_BENCHES:
        bench = benches.get(bench_name)
        if not isinstance(bench, dict):
            raise ValueError(f"source suite missing bench: {bench_name}")
        public_benches[bench_name] = _public_bench(source_suite, bench)
    return {
        "id": DEFAULT_SUITE_ID,
        "version": DEFAULT_SUITE_ID,
        "base_suite_version": source_manifest.get("version"),
        "headline_only": False,
        "description": "Minimal public bundle: MMLU-Pro 400, IFBench 294, and TC-JSON v1 330. The full repo suite/v1 carries the broader v2.1 modular benchmark set.",
        "benches": public_benches,
        "axes": {
            "knowledge": {"benches": ["mmlu_pro"]},
            "instruction_following": {"benches": ["ifbench"]},
            "tool_calling": {"benches": ["tc_json_v1"]},
            "agentic": {"benches": ["appworld_c"]},
        },
        "license_manifest": {
            "accepted_terms_required": True,
            "files": {
                "mmlu_pro.jsonl": {"license": "MIT", "source": "TIGER-Lab/MMLU-Pro"},
                "ifbench.jsonl": {"license": "ODC-BY-1.0", "source": "allenai/IFBench_test"},
                "tc_json_v1.jsonl": {
                    "license": "Apache-2.0",
                    "source": "BFCL single-turn backbone plus localbench-authored JSON tool-call conformance items",
                },
            },
            "notices": ["NOTICE", "ATTRIBUTION.md", "LICENSES/"],
        },
    }


def _public_bench(source_suite: Path, bench: JsonObject) -> JsonObject:
    public = {
        key: value
        for key, value in bench.items()
        if key in {"chance_correction_baseline", "decoding", "itemsets", "lane_caps"}
    }
    template_name = bench.get("template")
    if not isinstance(template_name, str):
        raise ValueError("source bench is missing template")
    public["template_text"] = (source_suite / template_name).read_text(encoding="utf-8")
    return public


def _public_lock(source_lock: JsonObject) -> JsonObject:
    files = source_lock.get("files")
    if not isinstance(files, dict):
        raise ValueError("source itemsets.lock.json missing files")
    public_files: JsonObject = {}
    for file_name in PUBLIC_BENCHES:
        jsonl_name = f"{file_name}.jsonl"
        entry = files.get(jsonl_name)
        if not isinstance(entry, dict):
            raise ValueError(f"source lock missing {jsonl_name}")
        public_files[jsonl_name] = _public_lock_entry(jsonl_name, entry)
    return {"files": public_files}


def _public_lock_entry(file_name: str, entry: JsonObject) -> JsonObject:
    copied = dict(entry)
    if file_name == "mmlu_pro.jsonl":
        copied["license"] = "MIT"
    if file_name == "ifbench.jsonl":
        copied["license"] = "ODC-BY-1.0"
        copied["license_note"] = (
            "Dataset terms per v1 distribution plan: ODC-BY-1.0, Ai2 Responsible "
            "Use Guidelines, and third-party generated-output caveat."
        )
    if file_name == "tc_json_v1.jsonl":
        copied["license"] = "Apache-2.0"
    return copied


def _write_items(source_suite: Path, stage: Path) -> None:
    for bench_name in PUBLIC_BENCHES:
        file_name = f"{bench_name}.jsonl"
        shutil.copyfile(source_suite / file_name, stage / file_name)


def _write_release_texts(stage: Path, lock: JsonObject) -> None:
    licenses = stage / "LICENSES"
    licenses.mkdir()
    (licenses / "MMLU-Pro-MIT").write_text(_data_license_text("MIT.txt"), encoding="utf-8")
    (licenses / "IFBench-ODC-BY-1.0").write_text(
        _ifbench_odc_license_text(),
        encoding="utf-8",
    )
    (licenses / "IFEval-Apache-2.0").write_text(_apache_license_text(), encoding="utf-8")
    (licenses / "BFCL-Apache-2.0").write_text(_apache_license_text(), encoding="utf-8")
    (stage / "NOTICE").write_text(_notice_text(), encoding="utf-8")
    (stage / "ATTRIBUTION.md").write_text(_attribution_text(), encoding="utf-8")
    (stage / "SOURCE_REVISIONS.md").write_text(_source_revisions(lock), encoding="utf-8")
    (stage / "CHANGES.md").write_text(_changes_text(), encoding="utf-8")


def _write_sha256sums(bundle_dir: Path) -> None:
    rows: list[str] = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        relative = path.relative_to(bundle_dir).as_posix()
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
    (bundle_dir / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _notice_text() -> str:
    return """local-bench minimal public suite

This bundle redistributes the minimal public item sets:
- MMLU-Pro by TIGER-Lab, dataset license MIT.
- IFBench_test by AllenAI/Ai2, dataset license ODC-BY-1.0.
- TC-JSON v1, a local-bench-authored JSON tool-calling bench with a
  BFCL-derived single-turn backbone, distributed under Apache-2.0.

The local-bench scorer also includes IFEval-derived verifier code under
Apache-2.0; that code license is included for scorer provenance.

IFBench caveat: the upstream dataset card states that use should follow Ai2's
Responsible Use Guidelines and that the dataset includes output data generated
from third-party models subject to separate terms.
"""


def _attribution_text() -> str:
    return """# Attribution

## MMLU-Pro

Source dataset: `TIGER-Lab/MMLU-Pro`.
Source revision: `b189ec765aa7ed75c8acfea42df31fdae71f97be`.
License: MIT.

## IFBench

Source dataset: `allenai/IFBench_test`.
Source revision: `2e8a48de45ff3bf41242f927254ca81b59ca3ae2`.
Dataset license: ODC-BY-1.0.
Verifier-code provenance: AllenAI IFBench code is Apache-2.0; local-bench also
reuses IFEval-style Apache-2.0 verifier patterns for scorer compatibility.

## TC-JSON v1

Source dataset: BFCL single-turn backbone plus localbench-authored JSON tool-call conformance items.
Source revision: local suite/v1 tc_json_v1.
License: Apache-2.0.
"""


def _source_revisions(lock: JsonObject) -> str:
    files = lock.get("files")
    lines = ["# Source Revisions", ""]
    if isinstance(files, dict):
        for file_name, entry in sorted(files.items()):
            if isinstance(file_name, str) and isinstance(entry, dict):
                lines.append(f"## {file_name}")
                lines.append(f"- source_dataset: {entry.get('source_dataset')}")
                lines.append(f"- source_revision: {entry.get('source_revision')}")
                lines.append(f"- sha256: {entry.get('sha256')}")
                lines.append("")
    return "\n".join(lines)


def _changes_text() -> str:
    return """# Changes

- This is a sampled/subsetted public bundle derived from local-bench suite/v1.
- It contains the minimal public benches: MMLU-Pro, IFBench, and TC-JSON v1.
- AMO, OlymMATH, SuperGPQA, BFCL multi-turn, LiveCodeBench, RULER, and BigCodeBench are
  excluded from this public v1 bundle.
- Scoring is local-bench's own chance-corrected, scorecard-bound composite.
"""


def _apache_license_text() -> str:
    root_license = Path(__file__).resolve().parents[3] / "LICENSES" / "Apache-2.0.txt"
    if root_license.exists():
        return root_license.read_text(encoding="utf-8")
    return "Apache License 2.0\nhttps://www.apache.org/licenses/LICENSE-2.0\n"


def _ifbench_odc_license_text() -> str:
    return (
        "IFBench dataset notice\n\n"
        "Source dataset: allenai/IFBench_test.\n"
        "Dataset license: ODC-BY-1.0.\n"
        "Additional upstream caveats: intended for research and educational use "
        "in accordance with Ai2 Responsible Use Guidelines; may include output "
        "data generated from third-party models subject to separate terms.\n\n"
        + _data_license_text("ODC-BY-1.0.txt")
    )


def _data_license_text(name: str) -> str:
    path = Path(__file__).resolve().parent / "data" / "licenses" / name
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
