# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
# --- How to run ---
# uv run --project cli python cli/scripts/build_6axis_suite_release.py
#
# Builds every static suite bundle the live site serves at /suites/<suite_release_id>/<file>
# so `localbench fetch-suite --suite <id>` actually resolves. The manifest API + suite-catalog
# declare all three release profiles; a declared suite whose physical dir is missing 404s on
# every file (the R2 break for the 6-axis on launch night, then again for the two static
# releases found in the 2026-07-07 user-journey pass).
#
# Each served bundle is the raw suite/v1 itemset dir (11 jsonl + suite.json + itemsets.lock.json
# + 9 templates), byte-identical to the source, so `build_suite_release_manifest(suite/v1,
# <profile>)` and the CLI's recompute on the fetched bundle BOTH equal the pinned
# suite_manifest_sha256 for that profile. The three bundles differ ONLY in their embedded
# suite_release_manifest.json (coverage profile); the itemset files are shared bytes. No
# attribution files are embedded in the bundles (that would change the pinned shas); attribution
# for every served itemset is provided publicly in the repo-root NOTICE (license-inventory-v1.md
# is the source of truth). AppWorld-C (agentic) stays out-of-band by design; no appworld jsonl.
# The two rankable v1 profiles use profile-specific frozen scoring snapshots in suite_release.py;
# the pinned-sha check below refuses replacement if their immutable identity ever drifts.
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cli" / "src"))

from localbench.submissions.canon import canonical_json_bytes  # noqa: E402
from localbench.suite_release import build_suite_release_manifest  # noqa: E402

SOURCE = REPO / "suite" / "v1"
SUITES_ROOT = REPO / "web" / "public" / "suites"

# (suite_release_id, coverage_profile_id, pinned suite_manifest_sha256)
# Pins must match release-pairs.expected.json / foundation.py / suite-catalog.ts.
BUNDLES: tuple[tuple[str, str, str], ...] = (
    (
        "suite-v1-full-exec-6axis-v1",
        "full-exec-6axis-v1",
        "c4098df81440c4489ee8c6d6967f3a5d6f9d6941810779abd135326ad734f468",
    ),
    (
        "suite-v1-static-exec-5axis-v1",
        "static-exec-5axis-v1",
        "4e240f8cffe8826ef1fd723f54b4b789d93990851d838818bce0954a38c61d64",
    ),
    (
        "suite-v1-static-core-diag-v1",
        "static-core-diag-v1",
        "f2f8c9a67df3adea5cec463fc156ccae073ea9deb54d4487d72b9826fe385c69",
    ),
)


def build_bundle(suite_release_id: str, profile_id: str, expected_sha: str) -> None:
    target = SUITES_ROOT / suite_release_id
    if target.resolve().parent != SUITES_ROOT.resolve() or target.name != suite_release_id:
        raise SystemExit(f"refusing to replace unexpected path: {target}")
    if target.exists():
        shutil.rmtree(target)
    # copy the raw itemset dir verbatim (no added metadata files -> matches the pinned sha)
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("suite_release_manifest.json", "__pycache__"))

    manifest = build_suite_release_manifest(target, coverage_profile_id=profile_id)
    (target / "suite_release_manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")

    sha = manifest["suite_manifest_sha256"]
    files = sorted(f["path"] for f in manifest["files"])
    print(f"{suite_release_id}")
    print(f"  suite_manifest_sha256: {sha}")
    print(f"  files: {len(files)}")
    if manifest["suite_release_id"] != suite_release_id:
        raise SystemExit(
            f"MISMATCH: built release id {manifest['suite_release_id']!r} != expected {suite_release_id!r}."
        )
    if sha != expected_sha:
        raise SystemExit(
            f"MISMATCH: built sha {sha} != pinned {expected_sha}. The served bundle must match the "
            "registered release sha or fetch-suite submissions will be rejected. Investigate before committing."
        )
    print("  OK matches the pinned release sha")


def main() -> int:
    for suite_release_id, profile_id, expected_sha in BUNDLES:
        build_bundle(suite_release_id, profile_id, expected_sha)
    print("OK all bundles match their pinned release shas; safe to commit + deploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
