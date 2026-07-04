# Wave 5 — board regen with the ranked row + leaderboard provenance rendering

Date: 2026-07-04. Author: Claude (manager). Implementer: Codex (gpt-5.5 xhigh).
Prereqs of record: Wave 2 (dc43f4f — origin threading, attestations, static
composite; board_scoring/board_types got additive row fields), Wave 3 (043effa),
methodology page (15209fe), submit page (ed1803d). Read
`docs/benchmark-build/wave2-provenance-attestation-spec-2026-07-04.md` AS-BUILT
for the exact additive field names.

## 0. Context and hard constraints

The first ranked 5-axis row exists as a local run and as an accepted-hidden
server submission. The public leaderboard must render it — with honest
provenance labels — before the public flip. This wave regenerates board data
and updates the site rendering. It does NOT publish anything (the site stays
private-gated; the server row stays hidden).

Hard constraints (binding):
- **Scope: `web/` + THIS spec file's AS-BUILT + read-only use of the `localbench`
  CLI (`uv run localbench board ...` from `cli/`). NO changes to `cli/src/**`,
  `cli/tests/**`, `cli/pyproject.toml`, `docs/**` (other than this spec).**
- `cli/runs/board/board_v1.json` is FROZEN: git hash must stay
  `3d058e6074bd781cc488c03255904b5f9599e37e`. Never write board_v1.json; the
  regenerated artifact is board_v2 (`localbench board` already defaults to a v2
  out path — see `cli/src/localbench/scoring/board_support.py`).
- No secrets in code/tests/logs. No network calls in tests.
- Do NOT git commit; leave the tree for manager review.
- Honesty rule: never fabricate provenance. The ranked row's agentic verdicts
  predate per-verdict signing and are attested via the GRANDFATHER mechanism
  (bundle sha `f815ebbb78516cbdd27b379a87c9fc34fd172692ee4e4e2ce047c5c02c846f85`
  in `GRANDFATHERED_ATTESTED_BUNDLE_SHA256S`, projection.py). If the board build
  cannot derive "attested" for this row through a legitimate path, label it via
  an explicit, documented board-source annotation — never by inventing
  attestation records.

## W5.1 Regenerate board data including the ranked row

- The ranked run: `runs/bench/ranked-5axis-capped-2026-07-03/localbench-run.json`
  (campaign.json beside it). 5-axis, capped-thinking, standard tier, composite
  ≈ 40.26%, agentic ≈ 5.2%.
- Reconcile how `localbench board` selects runs (`board_sources.json` /
  `DEFAULT_RUNS_DIR` in board_support.py) and produce a board_v2 output that
  includes the ranked row alongside the existing rows. If the sources mechanism
  needs the run copied/referenced into the expected location, do that WITHOUT
  touching board_v1.json or existing frozen artifacts; prefer configuration
  (sources file) over copying when supported.
- The row must carry the Wave-2 additive fields (origin="project_anchor",
  agentic provenance per the honesty rule above, composite_full,
  composite_static, static_index_version) — these are emitted by
  board_scoring.py as of Wave 2; verify they populate for this run.
- Then rebuild the site data (`python web/build_data.py` or the repo's actual
  wiring — reconcile `web/build_data*.py` + `data_sources.json`) so
  `web/public/data/**` carries the new board. Document the exact commands run
  in the AS-BUILT.

## W5.2 Leaderboard rendering (web/)

- Main table ranks index-v2.1 rows by composite_full. Rows with only the four
  static axes rank in a clearly separated static-composite section (or visually
  distinct grouping) by composite_static, labeled `static-suite-v1`, explicitly
  "not score-comparable" with the main index (methodology page wording is the
  reference). Rows with fewer axes stay unranked/per-axis (existing behavior).
- Every row shows two labels (chip/badge style consistent with the existing
  design system):
  - Trust: "project anchor" vs "community" (from origin / trust_label).
  - Agentic provenance (5-axis rows only): "attested" vs "self-reported".
    The grandfathered anchor row renders "attested" — the methodology page
    already carries the grandfather footnote; link the chip to /methodology.
- `submitter_display_name`, when present on a community row, renders as
  "submitted by <name>" (plain text, no links — the name is already
  URL-rejected server-side, but render defensively anyway).
- The ranked Gemma row is the proof case: after W5.1 + W5.2 it renders on the
  main table with "project anchor" + "attested".
- Zod schemas in web/lib validating board/index data: add the new fields
  (tolerant of absence for legacy rows — old rows without origin/provenance
  must still render, label omitted).

## W5.3 LAUNCH_FREEZE refresh

- `web/components/launch-freeze.tsx` (or wherever LAUNCH_FREEZE lives) is
  stale: asOfDate 2026-06-23, boardSha256 ec940cad…, 4-axis item hashes.
- Refresh to the regenerated reality: asOfDate 2026-07-04, boardSha256 =
  sha256 of the NEW board artifact the site actually serves (compute it, do
  not invent), item-set hashes for the 5-axis release
  (suite-v1-text-code-agentic-5axis-v1 — read them from the release's
  itemsets.lock.json / suite_release_manifest.json), scorecard version from
  the run's scorecard identity.
- The determinism wording and any "frozen as of" copy must remain TRUE
  statements about the new snapshot.

## W5.4 Tests + verification

- `npm run typecheck`, `npm test` (vitest), `npm run build` all green from web/.
- Add/extend vitest coverage: schema accepts rows with and without the new
  fields; provenance chip renders "attested"/"self-reported"/absent correctly;
  display-name renders as text (no anchor tag) — component-level tests
  following the repo's existing test style.
- Confirm `git hash-object cli/runs/board/board_v1.json` unchanged and NOTHING
  under cli/ is modified (`git status` must show web/ + this spec only).

## W5.5 Out of scope
- No publish-state changes (server row stays hidden; site stays private).
- No cli/ source changes. If board_scoring lacks something needed, STOP and
  write the gap into the AS-BUILT instead of patching cli/.
- No deploy (manager handles push + smoke).

## AS-BUILT (implementer appends)
Files touched, exact commands run for W5.1, deviations + reasons, test
summary lines, board_v1 hash output, and the new boardSha256.
