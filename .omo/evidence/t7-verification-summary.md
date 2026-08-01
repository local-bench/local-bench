# T7 verification summary

## Transition RED

- Scenario: exact notice, Current/Legacy summaries, current-first family/best/Pareto selection, complete semantic-digest gating, and non-supersession policy before implementation.
- Invocation: `cd web; npm test -- --run tests/model-variant-community-row.test.tsx tests/unified-leaderboard.test.tsx tests/best-variant.test.ts tests/vs-base.test.ts tests/compare.test.ts tests/community-live-board-schema-consistency.test.ts --reporter=json --outputFile=../.omo/evidence/t7-red-vitest-final.json`.
- Binary observable: exit nonzero; 62 tests, 51 passed, 11 intended failures. The valid 32k-to-8k non-supersession assertion already passed.
- Artifact: `.omo/evidence/t7-red-vitest-final.json`.

- Scenario: static model representative chooses the current profile even when a legacy run scores higher.
- Invocation: `cd web; npm test -- --run tests/build-data-display-security.test.ts --reporter=json --outputFile=../.omo/evidence/t7-red-static-representative.json`.
- Binary observable: exit nonzero; 8 tests, 7 passed, 1 intended failure (`profile-head__legacy` observed instead of `profile-head__current`).
- Artifact: `.omo/evidence/t7-red-static-representative.json`.

## Focused transition GREEN

- Scenario: exact notice hidden/shown gate; v2/rich-v1/id-only badges; current-first family/model selection; independent Pareto cohorts; equal-complete digest allowance; unequal/missing digest suppression across compare, quant, and lineage; static projection; no 32k supersession of valid 8k; no cross-profile rank-change copy.
- Invocation: `cd web; npm test -- --run tests/model-variant-community-row.test.tsx tests/unified-leaderboard.test.tsx tests/best-variant.test.ts tests/vs-base.test.ts tests/compare.test.ts tests/quant-decision.test.ts tests/community-live-board-schema-consistency.test.ts tests/build-data-display-security.test.ts --reporter=json --outputFile=C:/Users/Michael/local-bench/.omo/evidence/t7-focused-vitest-final.json`.
- Binary observable: exit 0; 17 suites, 75 tests, 75 passed, 0 failed.
- Artifact: `.omo/evidence/t7-focused-vitest-final.json`.

## Static checks

- Scenario: changed TypeScript surfaces compile under the repository's strict configuration.
- Invocation: `cd web; npm run typecheck`.
- Binary observable: exit 0; `tsc --noEmit` emitted no diagnostics.
- Artifact: this verified command record plus `.omo/evidence/t7-focused-vitest-final.json` (runtime compilation of the focused changed surfaces).

- Scenario: the production Next application compiles and statically generates all routes with the additive profile shape.
- Invocation: `cd web; npm run build`.
- Binary observable: exit 0; compile and TypeScript passed; 244/244 static pages generated.
- Artifact: this verified command record and the generated `web/.next/BUILD_ID` build artifact.

## Full regression gates

- Scenario: one clean, non-overlapping full web regression run after all implementation changes.
- Invocation: `cd web; npm test -- --reporter=json --outputFile=C:/Users/Michael/local-bench/.omo/evidence/t7-full-web-vitest-clean.json`.
- Binary observable: exit 0; 249 files passed; 707 tests passed, 1 pending, 0 failed.
- Artifact: `.omo/evidence/t7-full-web-vitest-clean.json`.

- Scenario: full CLI regression at T7 without modifying the frozen signed contract.
- Invocation: `cd cli; uv run pytest -q --junitxml=../.omo/evidence/t7-full-cli.xml`.
- Binary observable: exit 1; 2220 passed, 17 skipped, 4 xfailed, and exactly 1 failure: `tests/test_execution_contract_release_gate.py::test_live_covered_behavior_matches_baked_signed_contract`, the owner-exempt signed-contract drift wall.
- Artifact: `.omo/evidence/t7-full-cli.xml`.

## Scope and accessibility handoff

- `git diff --check` exited 0.
- No React dev-tool installer, publish, push, deploy, agentic ceremony, suite-byte mutation, or `runs/` mutation was performed.
- Browser visual QA is root-owned per the explicit task split; no executor visual-QA claim is made here.
