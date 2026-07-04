# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
# --- How to run ---
# uv run python scripts/build_5axis_suite_release.py
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from localbench._types import JsonObject, JsonValue
from localbench.submissions.canon import canonical_json_bytes, sha256_file
from localbench.suite_release import build_suite_release_manifest

ROOT = Path(__file__).resolve().parents[2]
SUITE_PARENT = ROOT / "web" / "public" / "suites"
SOURCE_SUITE = SUITE_PARENT / "suite-v1-partial-text-code-4axis-v1"
TARGET_SUITE = SUITE_PARENT / "suite-v1-text-code-agentic-5axis-v1"
PROFILE_ID = "text-code-agentic-5axis-v1"


@dataclass(frozen=True, slots=True)
class SuiteReleaseBuildError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def main() -> None:
    _reset_target_suite()
    shutil.copytree(SOURCE_SUITE, TARGET_SUITE, ignore=shutil.ignore_patterns("suite_release_manifest.json"))
    _write_suite_json()
    _write_release_notes()
    _write_sha256sums()
    manifest = build_suite_release_manifest(TARGET_SUITE, coverage_profile_id=PROFILE_ID)
    _write_json(TARGET_SUITE / "suite_release_manifest.json", manifest)
    print(manifest["suite_manifest_sha256"])


def _reset_target_suite() -> None:
    parent = SUITE_PARENT.resolve()
    target = TARGET_SUITE.resolve()
    if target.parent != parent or target.name != "suite-v1-text-code-agentic-5axis-v1":
        raise SuiteReleaseBuildError(f"refusing to replace unexpected path: {target}")
    if TARGET_SUITE.exists():
        shutil.rmtree(TARGET_SUITE)


def _write_suite_json() -> None:
    suite = _read_json(SOURCE_SUITE / "suite.json")
    axes = _object(suite["axes"])
    axes["agentic"] = {"benches": ["appworld_c"]}
    suite["axes"] = axes
    suite["description"] = (
        "Public 5-axis text+code+agentic release for local-bench: MMLU-Pro, IFBench, "
        "TC-JSON v1, LiveCodeBench output prediction, and out-of-band AppWorld-C."
    )
    suite["id"] = "suite-v1-text-code-agentic-5axis-v1"
    _write_json(TARGET_SUITE / "suite.json", suite)


def _write_release_notes() -> None:
    (TARGET_SUITE / "CHANGES.md").write_text(
        "\n".join(
            [
                "# Changes",
                "",
                "## suite-v1-text-code-agentic-5axis-v1",
                "- Coverage profile: text-code-agentic-5axis-v1 = mmlu_pro + ifbench + tc_json_v1 + lcb + appworld_c.",
                "- Adds the agentic axis through out-of-band appworld_c; no appworld_c jsonl is served in this suite.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (TARGET_SUITE / "NOTICE").write_text(
        "\n".join(
            [
                "local-bench text-code-agentic-5axis-v1 public suite",
                "",
                "This release extends the 4-axis text+code release with agentic axis membership for appworld_c.",
                "AppWorld-C is out-of-band and is not redistributed as a jsonl itemset in this directory.",
                "",
                "LiveCodeBench notice: lcb.jsonl is derived from livecodebench/test_generation with dataset license metadata CC-BY-4.0, but source problem statements originate from LeetCode. Until that source-site serving question is fully closed, this release flags lcb.jsonl in suite_release_manifest.json and carries this NOTICE.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def _write_sha256sums() -> None:
    rows = []
    for path in sorted(TARGET_SUITE.rglob("*"), key=lambda item: item.relative_to(TARGET_SUITE).as_posix()):
        if not path.is_file() or path.name in {"SHA256SUMS", "suite_release_manifest.json"}:
            continue
        rows.append(f"{sha256_file(path)}  {path.relative_to(TARGET_SUITE).as_posix()}")
    (TARGET_SUITE / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")


def _read_json(path: Path) -> JsonObject:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SuiteReleaseBuildError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: JsonObject) -> None:
    path.write_bytes(canonical_json_bytes(data) + b"\n")


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise SuiteReleaseBuildError("expected JSON object")
    return dict(value)


if __name__ == "__main__":
    main()
