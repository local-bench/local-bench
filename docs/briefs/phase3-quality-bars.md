<task>
Improve the local-bench HOME finder area on branch `site-overhaul`: (1) REPLACE the quality-vs-VRAM
scatter with a new "Ranked Quality Bars" chart (Artificial-Analysis-Intelligence-Index style, adapted
to our DARK theme), (2) extend the finder's VRAM tiers up to 512 GB, (3) add two huge demo models so
the large tiers populate. You implement; Claude reviews.
</task>

<context>
Read first: docs/foundations/website-design-v2.md. Current code to work with:
- web/components/quality-vram-scatter.tsx (the scatter to replace on home)
- web/components/rig-match-finder.tsx, web/lib/rig-match.ts (VRAM_TIERS lives here)
- web/app/page.tsx (home; leads with RigMatchFinder, then the scatter)
- web/app/model/[slug]/page.tsx + web/components/model-scatter.tsx (the MODEL page may also use a scatter)
- web/build_data_demo.py, web/data_sources.json, web/lib/data.ts, web/lib/format.ts, web/tailwind.config.ts
The home page must keep the RigMatchFinder and REPLACE the scatter below it with the new bar chart.
</context>

<deliverables>
1. New component web/components/quality-bars.tsx — "Ranked Quality Bars", AA-Intelligence-Index styling
   in our DARK theme:
   - Horizontal bars, ALL models sorted by composite quality DESCENDING.
   - Frontier ANCHORS at the TOP using the amber `bench-anchor` token, each tagged "frontier"; then a
     thin "frontier line" separator; then LOCAL models below using the teal `bench-accent` token.
   - Each bar row: model label (left, truncating gracefully), the bar (length proportional to score on a
     fixed 0-100 scale), the numeric score at the bar end, and a small right tag with VRAM for LOCAL
     models (anchors are API -> no VRAM tag). DEMO models get the existing DemoBadge.
   - For each LOCAL model show ONE representative bar (its best/headline quant), with the quant noted —
     do NOT explode every quant into its own bar here (that belongs on the model page).
   - Use tailwind tokens only (NO hardcoded hex). Faint gridlines/baseline. Accessible (role="img" +
     descriptive aria-label, plus a visually-hidden data list fallback is welcome). Responsive: bars fill
     container width; degrade cleanly on narrow screens.
2. Wire it into web/app/page.tsx in place of the scatter. If quality-vram-scatter.tsx is no longer used
   ANYWHERE, remove it; if the MODEL page still uses a scatter, leave that usage intact and only swap the
   HOME usage. Do not break the model page.
3. Extend VRAM_TIERS in web/lib/rig-match.ts to: 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512
   (keep default 24).
4. Add two HUGE demo models (demo:true) to the generator + data so big tiers populate; numbers on the
   SAME 0-100 quality scale as the existing demo models, degrading monotonically with quant:
   - Llama-3.1-405B: FP16 ~810GB/~82, Q8 ~405GB, Q5_K_M ~290GB, Q4_K_M ~230GB/~78, Q3_K_M ~180GB/~75; tok/s very low (~5-15).
   - DeepSeek-V3-671B: FP16 ~1340GB/~84, Q8 ~670GB, Q5_K_M ~470GB, Q4_K_M ~380GB/~80, Q3_K_M ~300GB/~77; tok/s low (~8-20).
   Regenerate web/public/data. Keep the 4 real anchors and the real Qwen 9B unchanged.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY; never main. Do NOT change real run data or the CLI/scoring core. Demo data additive.
- Reuse tailwind tokens, next/font fonts, badges, axis-config; match the dark design system.
- Keep the existing RigMatchFinder + bounty + leaderboard table intact.
</constraints>

<verification_loop>
- npm run typecheck clean; npm test green (keep rig-match tests passing; add/update tests if you add
  data or sort logic); npm run build green.
- Confirm the home render: finder at top; below it the ranked quality bars (anchors amber on top,
  frontier line, locals teal with scores + VRAM tags + DEMO badges); the VRAM dropdown now goes to 512;
  selecting 192 shows a 405B (Q3) row, 384/512 show the bigger options.
- Commit per coherent step on site-overhaul with clear messages; never leave the tree broken.
</verification_loop>

<output_contract>
Return: files changed; how the bar chart sorts and separates anchors vs locals and computes bar length;
the two new demo models' sample VRAM/quality/tok-s; whether you removed or kept the scatter (and why);
test results (typecheck/test/build). Note remaining Phase-3 work: model-page quant-decision matrix; /compare.
</output_contract>
