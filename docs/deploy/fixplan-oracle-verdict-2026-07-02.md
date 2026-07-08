# Fix-plan oracle red-team + Claude code-verification — 2026-07-02

> **⚠️ CORRECTION + SUPERSESSION (2026-07-02, later the same day):** Verdict #5 and priority #3
> below misidentify the released suite. The site-released, publishable suite is
> **`suite-v1-partial-text-code-4axis-v1`** (manifest `b3fc4019…`, includes lcb) — the ONLY entry
> in `foundation.py:_SITE_RELEASED_SUITES` and the only `web/public/suites/` dir with a
> `suite_release_manifest.json`. `core-text-v1` has **no published release manifest** and is
> explicitly non-publishable (`foundation.py:58-68`); fetching it would still trip
> `suite.not_site_released`. Row 1 targets the 4-axis release (0.50 weight, incl. coding).
> The live plan is now **`plan-ranked-row-2026-07-02.md`** (owner-decided: ranked-row-first,
> unpublished capped-thinking canary, WSL2 lane).

Red-team of the 5-problem fix plan surfaced by the first orchestrated Gemma-12B run
(`runs/bench/gemma-12b-qat-q4xl-standard-2026-07-01/`). Oracle = GPT-5.5 Pro Extended,
browser/OAuth engine, 3 files attached (briefing + canary findings + `serving/bench.py`),
session `local-bench-fixplan`. Every load-bearing claim below was then VERIFIED against the
code (not relayed). **Nothing committed/redeployed. board_v1 frozen.**

## Headline correction (found by verifying, would have been missed by relaying)
The two "broken" axes are **one serving artifact, not the causes oracle or I guessed.** Raw
per-item outputs show a reasoning-channel prefix `<|channel>thought\n<channel|>` on **100% of
responses across all 4 benches** (400/400 mmlu, 294/294 ifbench, 330/330 tc_json, 129/129 lcb).
The model's real answers are correct underneath it (e.g. tc_json emitted exact valid envelopes).

- **Cause (verified):** strict argv `serving/llama_cpp.py:91-95` = `--jinja --reasoning off
  --reasoning-format none` → the model's channel scaffolding is not parsed/stripped → leaks inline.
- **tc_json_v1 0%** — strict "trimmed text is exactly one JSON object, full-string parse" dies on
  the prefix (`failure_kind: invalid_json`). NOT a routing bug: the plaintext template WAS applied
  and the conformance scorer DID run. NOT native-tools (see #1).
- **lcb 5.4%** — `literal_eval`/JSON parse dies on the prefix. lcb is **exec-free by design**
  (`scorers/lcb.py` = LiveCodeBench output-prediction, "Do not run code"). A Linux sandbox would
  NOT have fixed it.
- **ifbench 28.6% is DEPRESSED, not clean** — a `<|channel>thought…` preamble violates
  format/first-line instruction constraints. Re-measure on a clean run before trusting the number.
- **mmlu_pro 72.2% is robust** — its extractor scans for `Answer:` anywhere, so it survived.

## Per-problem verdict (oracle) — all confirmed against code
1. **tc_json** — oracle: do NOT fix via native `tools`/`tool_choice`/grammar; it's a **frozen
   plaintext-JSON-only contract** (`SPEC-tc-json-bench.md:7`: "NO native tools=/tool_choice, no
   grammar-constrained decoding, no backend tool parser"). CONFIRMED. My "native tools" fix would
   have silently redefined the benchmark. (The real cause is the channel leak above.)
2. **coding/agentic** — oracle: lcb is exec-free (CONFIRMED); agentic (AppWorld) genuinely needs
   Linux/bwrap. Env-splitting OK for partial/community evidence but the highest-trust canonical
   runner should be Linux/containerized; Windows-native = a lower/explicit text-axis tier.
3. **GGUF identity** — CONFIRMED: `manifest.py:20-23` requires `model.tokenizer_digest` +
   `model.chat_template_digest`; `ManifestContext` only has `tokenizer_file`/`chat_template_file`
   Paths (`:60-61`); `_model_identity` hashes files (`:202-203`) → GGUF yields null. Refine my fix
   with explicit digest fields + **source labels** (`gguf.embedded`|`external.file`|
   `server.override`); if `--chat-template-file` overrides, hash the override. Keep
   `gguf_metadata_sha256` as an audit hash only — not the tokenizer/template identity.
4. **Bug 2 finalize 500** — isolation strong; my D1 hypothesis plausible but narrow. Better than
   "deploy+tail": structured `console.error` (name/message/stack, no secrets), boundary
   breadcrumbs, source maps, reproduce under `wrangler pages dev` w/ local D1, and run the exact
   `markPendingVerification` UPDATE against fresh / old-0001-then-0002 / remote schemas. D1 candidates:
   column/CHECK/NOT-NULL mismatch after 0001→0002, idempotency conflict on `raw_bundle_sha256`,
   bind count/`undefined` bind. Also fix the latent migration (fresh-DB rebuild still broken).
5. **suite not released** — CONFIRMED: released `core-text-v1` ships only mmlu_pro + ifbench +
   tc_json_v1 (+ AppWorld membership), **no lcb** (`data/suites/core-text-v1/suite.json`). Fetching
   it gives a 3-runnable-axis partial (**0.40 weight**), not a full row. Don't rerun suite/v1 and
   expect the site to accept it.

## Verified priority order → first publishable PARTIAL row
0. **Kill the channel leak** (cheapest, highest-leverage; rescues tc_json + lcb, lifts ifbench).
   Explicit non-`auto` reasoning setting (`validate_strict_argv_supported` forbids `auto`);
   inspect ~10 raw outputs; 20-item tc_json+ifbench GPU mini-run — **ASK-FIRST**.
1. Model-identity plumbing (code-only, no GPU).
2. Bug 2 finalize + latent migration (code + private redeploy w/ Michael review).
3. Row scope → fetch core-text-v1 → tiny e2e dry-run (5–10 items/axis) → canary submit → confirm
   `pending_verification` → full core-text-v1 run → submit. Row 1 = 3 axes, `headline_complete=false`.
4. Parallel (not row-1-blocking): Linux/containerized runner for AppWorld + coding-exec module →
   full ranked v2.1 headline row.

Raw oracle transcript: session `local-bench-fixplan` (browser). This doc is the reviewed synthesis.
