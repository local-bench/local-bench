# Frontend design state: deeper-budgets T7

## Current Objective

Expose the 32k operating-point transition honestly across board selection, comparison, and row presentation while keeping valid 8k history visible.

## Locked Decisions

- Root `DESIGN.md` remains the visual contract; preserve the neon-on-graphite operational UI.
- `generic_think_tags_32768_v1` is Current. Existing valid profiles are Legacy, not invalid and not superseded.
- Board notice copy is owner-pinned verbatim and appears only after a 32k row exists.
- Cross-profile scores are not compute-matched; selection and deltas must never imply otherwise.
- React dev-tool installers are skipped because they write outside the repository, contrary to the owner constraint.

## Source Inputs

- `docs/superpowers/plans/2026-07-31-deeper-budgets-migration.md`, T7
- `DESIGN.md`
- `.superpowers/sdd/2026-07-31-deeper-budgets-migration/task-7-brief.md`

## Design Brief

The audience is a benchmark reader comparing dense tabular evidence. Preserve scan speed and numerical hierarchy. Use a clear notice plus text-bearing Current/Legacy badges so operating-point state does not depend on color.

## Inclusive Personas

- Keyboard/screen-reader reader: can identify each row's operating point and full profile identity without hover.
- Low-vision reader at 200% zoom: notice and summary wrap without clipping or horizontal-page overflow.
- Methodology-conscious reader: cannot mistake legacy-versus-current score movement for a performance delta or rank change.

## Adaptive Preferences

No new motion. Preserve focus behavior, semantic headings/notices, contrast, natural wrapping, and the existing horizontally scrolling dense table.

## Verification Matrix

- Complete: focused Vitest covers notice, badges, profile-aware family/model/Pareto selection, digest-gated deltas, static projection, and supersession (75/75).
- Complete: full Vitest (707 passed, 1 pending), typecheck, and production build.
- Root-owned downstream gate: browser captures at 375, 768, and 1280 px with 8k-only and mixed 8k/32k data states.
- Root-owned downstream gate: keyboard/accessibility, heuristic, and persona walkthroughs on the same build.
- Root-owned downstream gate: independent visual-QA review. The T7 executor intentionally did not run browser visual QA under the owner split.

## Design Debt Register

None accepted.

## Evidence Index

- `.omo/evidence/t7-red-vitest-final.json`: initial transition RED, 11 intended failures.
- `.omo/evidence/t7-red-static-representative.json`: static family/model representative RED, 1 intended failure.
- `.omo/evidence/t7-focused-vitest-final.json`: final focused GREEN, 75/75.
- `.omo/evidence/t7-full-web-vitest-clean.json`: clean full web GREEN, 707 passed, 1 pending.
- `.omo/evidence/t7-full-cli.xml`: full CLI gate, 2220 passed with only the owner-exempt signed-contract drift wall failing.
- `.omo/evidence/t7-verification-summary.md`: exact scenarios, invocations, observables, and artifact mapping.
