# Season-2 (index-v4.0) cutover runbook — 2026-07-13

The ONE sanctioned public re-rank event. Prereqs all met and committed: 18626ae (macro-axis),
3c29436 (editorial/bridge/guards), 8ae6c3e (coverage + composer), fd1fbba (dual-mode web),
e9570a4 (tc_json demotion, scorecard v5), provenance bundle
(docs/foundations/season-2-backfill-provenance-2026-07-13.md).

## Gate status at execution (all verified this session)
- cli suite 1631/0; web vitest 387/0(+1 skip); frozen v1 shas ×3 byte-identical.
- Live-data equivalence: dual-mode web renders current v1 data byte-identically (informational
  drift markers only).
- D1 export taken + restore REHEARSED into scratch sqlite (9 tables, counts match, 3 pending).
- Migration 0014 = single additive CREATE TABLE IF NOT EXISTS (old code indifferent; idempotent).
- Rank stability: 15/15 weight-sensitivity cells identical ranking; 2 independent bootstrap seeds.
- b2a client-compat gate green (rc_n + live 0.3.2) at the deploy tree.

## Sequence
1. **Cutoff timestamp + queue freeze note** — record UTC now; the 3 pending tickets (all
   maintainer-owned, verified in prod D1) are the launch-cohort occupants; positions 4-5 remain
   open per the literal FIFO promise.
2. **Fresh D1 export** (pre-migration): `npx wrangler d1 export localbench_prod --remote --output
   <dated file>`; verify importable (rehearsed).
3. **Apply migration 0014**: `npx wrangler d1 migrations apply localbench_prod --remote`; then
   assert live app still healthy (old code + new schema): GET /api/health + a queue page fetch.
4. **Curation repoint** (maintainer edit, additive):
   - Copy the five `*-s2v5.json` composed records into `runs/bench/season-2-backfill/` (tracked).
   - `web/data_sources.json`: repoint the 3 ranked rows' `file` to the composed records; ADD rows
     for gemma-4-31b-it and qwen3-6-35b-a3b (curated maintainer entries; catalog entries exist).
5. **Board rebuild**: `uv run --project cli localbench board` → new board_v2 (season-2, 5 ranked);
   sha256 board; re-pin `web/components/launch-freeze.ts` boardSha256; board_v1 sha UNCHANGED.
6. **Site data**: `cd web && python build_data.py` (reads new board; dual-mode renders v4).
7. **Full suites once more on the exact deploy tree** (cli pytest + web vitest) — green required
   (b2a pin refresh expected after any cli change; none expected in this sequence).
8. **Commit** the cutover (curation + board artifacts + freeze pin + data).
9. **Deploy**: `cd web && scripts/publish-board.ps1` (chains tests → data → build → deploy →
   live-verify).
10. **Live-verify assertions** (all must hold before ticket resolution):
    a. `/leaderboard` shows exactly 5 ranked rows in order: gemma-4-31b-it 47.38 > qwen3-6-27b
       46.38 > qwopus3-6-27b-v2-mtp 45.12 > gemma-4-12b-it Q4XL 44.01 > qwen3-6-35b-a3b 37.65,
       each with CI bands and season badge index-v4.0.
    b. tool_use axis with facet breakdown visible; call_formatting shown as unweighted diagnostic.
    c. qwopus row shows base_model lineage chip + vs-base delta vs qwen3-6-27b (same season).
    d. Anchors/ladder rows still display season-1 labels + composites (option-d), unranked.
    e. Methodology page: index-v4.0 section, 10/17-7/17 facet table, bridge explanation, backfill
       provenance link.
    f. Cross-season guard: no UI surface compares v3 and v4 composites directly.
    g. Board sha served == LAUNCH_FREEZE pin == committed board file sha.
    h. `/api/health` OK; a fetch-suite + submit dry probe against the live Worker still accepts
       (b2a compat gate already proved both shipped clients).
11. **Ticket resolutions** (authenticated admin endpoint, only after 10 passes):
    - …4a182447 (gemma-31b) → accepted, projection = its published season-2 row.
    - …2b007ff4 (qwen-35b-a3b) → accepted, projection = its published season-2 row.
    - …1bf8b771 (ladder rung) → resolved/superseded (content already published as the landed
      maintainer Q2 rung row; note in status_reason).
12. **Rollback plan** (if any assertion fails): redeploy previous site build (git artifacts);
    board/data revert = git revert of the cutover commit; D1: migration 0014 is additive/inert —
    restore from the step-2 export ONLY if ticket-state writes occurred (they happen last, so
    normally no D1 action needed). Announce nothing.

ANNOUNCE remains the owner's decision (issue #21 timing guidance). The 0.4.0 dogfood canary gate
(next NEW model via public one-line CLI end-to-end) remains the release/announce gate.
