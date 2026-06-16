<task>
Finish the local-bench Phase-3 site work on branch `site-overhaul`: (1) fix the VRAM-fit logic to be
KV-cache / context / overhead aware, (2) bring the finder-era design to the MODEL pages with a
"which quant should I run?" decision matrix, (3) add a `/compare` model x quant diff page. You implement;
Claude reviews.
</task>

<context>
Read: docs/foundations/website-design-v2.md (approved design — model-page matrix + compare are specced).
Current code: web/lib/rig-match.ts (fit logic + VRAM_TIERS), web/components/rig-match-finder.tsx,
web/components/quality-bars.tsx + web/lib/quality-bars.ts, web/app/model/[slug]/page.tsx (model page to
upgrade), web/components/model-scatter.tsx, web/lib/data.ts, web/lib/schemas.ts, web/lib/format.ts,
web/build_data*.py, web/components/app-shell.tsx (nav), web/tailwind.config.ts (tokens).
Demo data: 7 local demo models (Qwen3-32B, Llama-3.3-70B, Gemma-3-27B, Mistral-Small-24B, Phi-4-14B,
Llama-3.1-405B, DeepSeek-V3-671B) x quant ladders, all demo:true. 4 API anchors = ceiling.
</context>

<deliverables>
1. VRAM-fit fix (web/lib/rig-match.ts + demo data): a model whose WEIGHTS are N GB does NOT fit an N GB
   card. Account for KV cache + context + activations + CUDA/runtime overhead:
   - effective_required_gb = weights (vramFootprintGb) + kv_cache_gb + overhead_gb, and this must be
     <= selected VRAM (replace the current weights-only `vramFootprintGb > vramGb` check).
   - kv_cache_gb: estimate from a reference context length (default ~8K, with a small context selector
     8K/32K/128K is a nice touch). Either add a per-run kv estimate to the demo data or compute a simple,
     clearly-documented heuristic proportional to model size x context. overhead_gb: fixed ~1.5 GB.
   - Make the assumption VISIBLE in the finder UI: e.g. "fits at ~8K ctx · ~X GB reserved", and if a
     context selector is added, recompute fit live.
   - Pick demo numbers so the behaviour is visibly correct: e.g. a 405B Q3 (~180 GB weights) should NOT
     fit 192 GB once headroom is added. Update/extend the rig-match tests for the new fit math.
2. Model page (web/app/model/[slug]/page.tsx) — finder-era design:
   - Hero: a "Which quant should I run?" DECISION MATRIX — one row per quant: quality +/- CI, delta vs
     FP16, VRAM (effective, with the new fit model), which VRAM tier it fits, tok/s; flag the Pareto
     sweet-spot. Render a COVERAGE CARD when a quant or the FP16 baseline is missing (never a broken hero).
   - Keep the per-axis profile + runs table; ensure they use the data-driven axis-config + tokens + fonts;
     DEMO badge where demo:true.
3. /compare page (web/app/compare/page.tsx): head-to-head model x quant diff — pick two configs, show
   side-by-side composite, per-axis deltas, VRAM delta, tok/s delta, and which wins each axis. Link it
   from the top nav (app-shell) and from model pages.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY; never main. Do NOT change real run data or the CLI / scoring core. Demo data additive.
- Reuse tailwind tokens, next/font fonts, axis-config, badges, and the quality-bars/scatter components;
  match the dark design system. Accessible + responsive.
</constraints>

<verification_loop>
- npm run typecheck clean; npm test green (add tests for the new fit math + any new pure logic);
  npm run build green; npm run e2e (home) green.
- Confirm renders: the finder now reserves headroom (a ~180 GB model does NOT fit 192 GB); the model page
  leads with the quant decision matrix + sweet-spot + coverage cards; /compare diffs two configs and is
  linked from the nav.
- Commit per coherent step on site-overhaul with clear messages; never leave the tree broken.
</verification_loop>

<output_contract>
Return: files changed; the exact VRAM-fit formula + the kv-cache/overhead assumptions; how the model-page
matrix + /compare render; test results (typecheck/test/build/e2e). Note anything deferred.
</output_contract>
