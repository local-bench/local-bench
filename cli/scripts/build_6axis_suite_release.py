# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
# --- How to run ---
# uv run --project cli python cli/scripts/build_6axis_suite_release.py
#
# Builds the static suite bundle the live site serves at
# /suites/suite-v1-full-exec-6axis-v1/<file> so `localbench fetch-suite --suite
# suite-v1-full-exec-6axis-v1` actually resolves (the manifest API + suite-catalog already
# declare this suite; the physical dir was never built, so every file 404'd — the R2 break).
#
# The served bundle is the raw suite/v1 itemset dir (11 jsonl + suite.json + itemsets.lock.json
# + 9 templates), byte-identical to the source, so `build_suite_release_manifest(suite/v1,
# "full-exec-6axis-v1")` and the CLI's recompute on the fetched bundle BOTH equal the pinned
# suite_manifest_sha256 (c4098df8… as of the #42 harness). No attribution files are embedded in
# THIS bundle (that would change the pinned sha); attribution for every served itemset is provided
# publicly in the repo-root NOTICE (license-inventory-v1.md is the source of truth) — matching how
# the pinned sha was defined. AppWorld-C (agentic) stays out-of-band by design; no appworld jsonl.
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cli" / "src"))

from localbench.submissions.canon import canonical_json_bytes  # noqa: E402
from localbench.suite_release import build_suite_release_manifest  # noqa: E402

SOURCE = REPO / "suite" / "v1"
TARGET = REPO / "web" / "public" / "suites" / "suite-v1-full-exec-6axis-v1"
PROFILE_ID = "full-exec-6axis-v1"
# Cross-check against the sha pinned in release-pairs.expected.json / foundation.py / suite-catalog.ts.
EXPECTED_SHA = "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468"


def main() -> int:
    parent = TARGET.parent.resolve()
    if TARGET.resolve().parent != parent or TARGET.name != "suite-v1-full-exec-6axis-v1":
        raise SystemExit(f"refusing to replace unexpected path: {TARGET}")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    # copy the raw itemset dir verbatim (no added metadata files -> matches the pinned sha)
    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("suite_release_manifest.json", "__pycache__"))

    manifest = build_suite_release_manifest(TARGET, coverage_profile_id=PROFILE_ID)
    (TARGET / "suite_release_manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")

    sha = manifest["suite_manifest_sha256"]
    files = sorted(f["path"] for f in manifest["files"])
    print(f"suite_manifest_sha256: {sha}")
    print(f"files ({len(files)}): {files}")
    if sha != EXPECTED_SHA:
        raise SystemExit(
            f"MISMATCH: built sha {sha} != pinned {EXPECTED_SHA}. The served bundle must match the "
            "registered release sha or fetch-suite submissions will be rejected. Investigate before committing."
        )
    print("OK bundle matches the pinned release sha; safe to commit + deploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
