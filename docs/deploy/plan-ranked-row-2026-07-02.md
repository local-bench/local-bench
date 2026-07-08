# Plan: first RANKED row — decided 2026-07-02 (owner-interviewed)

Supersedes the priority list in `fixplan-oracle-verdict-2026-07-02.md` (which also contains a
suite-target error — see the correction banner there). Decisions below were made by Michael in a
structured interview (grill-me) after a full-repo comprehensive review (Claude Fable, 4 review
agents + first-hand verification; 994 tests green at review time).

## Definition of done (owner decision)
**The suite is not "complete" until agentic runs and a full 5-axis RANKED row lands. Public flip
only after that.** Board debuts with a ranked Local Intelligence Index row, not a partial.

Staging: while the Linux/agentic lane is built, a 4-axis bundle goes through the FULL submission
pipeline as a canary — **verified + accepted, publication HELD** (publish_state stays unpublished).
The ranked run then travels an already-proven path.

## Row-1 facts (corrected)
- **Released suite = `suite-v1-partial-text-code-4axis-v1`** (manifest sha `b3fc4019…`), the ONLY
  entry in `foundation.py:_SITE_RELEASED_SUITES` and the only dir under `web/public/suites/` with a
  `suite_release_manifest.json`. It includes lcb (coding). `core-text-v1` has NO release manifest
  and is not publishable — the old fix-plan's "fetch core-text-v1" step would still trip
  `suite.not_site_released`.
- **Lane = capped-thinking** for both the canary and the ranked row (`LANE_SCOPE = "capped-thinking"`,
  `board_support.py:24`; ranked gate `board_scoring.py:437`). Canary ≈ 13h overnight.
- **Score yardstick** (2026-06-30 calibration pilot, LM Studio, capped-thinking, clean outputs):
  ifbench ~0.687, tc_json ~0.736, lcb ~0.853, mmlu_pro ~0.745cc. The leak-fixed orchestrated canary
  should land near these; large deltas ⇒ remaining serving artifact.
- Model: `unsloth/gemma-4-12B-it-qat-GGUF` UD-Q4_K_XL (file_sha256 `cc9ff072…`), llama.cpp b9852
  (`fd1a05791`), RTX 5090.

## Priority order
0. **Kill the channel leak — empirically.** Probe b9852 reasoning configs per lane
   (answer-only: `--reasoning off` + budget-0/format variants; capped-thinking: `--reasoning on
   --reasoning-budget 8192` + a format that PARSES Gemma's channel). Pin an explicit value if one
   works. If only `auto` (detect-from-pinned-template) works: the no-`auto` strict-argv rule gets a
   **documented, oracle-gated exception** (argv records auto; provenance records chat_template_digest
   + the RESOLVED parser). Then a ~20-item tc_json+ifbench mini-run to confirm clean outputs.
   **Plus, regardless: unify the 3 reasoning-leak vocabularies** (`_reasoning.py` strip,
   `lane_conformance.has_leaked_reasoning` — currently misses the `<|channel>` family entirely —
   and per-lane scorecard `leak_regexes`) so the conformance gate catches any future leak instead of
   letting a corrupted run rank as headline-comparable.
1. **Model-identity plumbing** (code-only): pass `artifact.tokenizer_digest`/`chat_template_digest`
   (already computed, `model_artifact.py:83-84`) through `build_orchestrate_config` →
   `OrchestrateConfig` → `ManifestContext` → `manifest._model_identity` (prefer embedded digest,
   keep file-hash fallback; source labels `gguf.embedded|external.file|server.override`). Also:
   the `process.py:41-55` orphan window (Popen→assign_process failure leaves an untorn-down server)
   and `_bench` exit-code mapping (UnsafeResume/CheckpointCorruption currently collapse to
   internal-bug).
2. **Submission pipeline**: Bug-2 root cause (structured console.error in the finalize catch,
   `wrangler pages dev` + local D1, exact `markPendingVerification` UPDATE vs fresh / 0001→0002 /
   remote-mirror schemas — leading hypothesis: remote-D1 schema/CHECK drift surfacing as a
   mis-parsed SyntaxError); **0003 migration** (drop-first recreate; fresh-DB rebuild is currently
   broken); **split-brain routes** (`GET /api/submissions/{id}` + `GET /api/admin/submissions` still
   query 0001 columns → broken on the live DB; rewire to the 0002 store); enforce bundle
   `suite_release_id` == ticket expected at finalize.
3. **Canary through the site**: serve the 4-axis release from the API catalog (or its static
   manifest path) → `fetch-suite` from the live-private site (bypass) → tiny e2e dry-run → full
   capped-thinking run (**ASK FIRST**) → submit → verify → accept → **HOLD publication**.
4. **Linux lane (critical path)**: WSL2 on this box. Topology design → **oracle red-team first**
   (Linux llama.cpp build in WSL vs WSL client → Windows-hosted endpoint; how ONE campaign carries
   appworld_c out-of-band + 4 http axes; Linux teardown pgroup; 5-axis coverage profile /
   suite-release story). Then env setup (bwrap + appworld venv + `APPWORLD_ROOT` — command in
   `test_appworld_sandbox_acceptance.py` docstring), acceptance tests green, Codex builds, agentic
   shakeout, then the **RANKED 5-axis capped-thinking run (ASK FIRST) → publish. Done.**
5. **Hygiene** (non-blocking): refresh `live-state.md` (its "secrets missing" claim is contradicted
   by the 07-01 canary — admin auth + R2 PUT work; deployment IDs stale), fix `launch-smoke.ps1`
   (hardcoded IDs, unconditional secret-WARNs), retire dead legacy web submission handlers,
   `cli/uv.lock` track-or-ignore, `source_tag` regex (version stdout carries `9852` without the
   `b` prefix), public-flip P1 items (preview-env hardening confirm, adversarial submission tests,
   D1 backup).

## Progress log

- **2026-07-02 (late)** — P0 done (leak fix `2f008bc` + vocab unification `ca6187e`); P1 done
  (`7bd4da1`); P2 local half done (`31e8d04`; remote legs await wrangler re-auth); P3 pull-leg
  proven (site fetch-suite, hash-verified). **NEW ROOT CAUSE found past the leak fix:** the first
  capped-thinking mini-run deflated (ifbench 10%) because `bench` never wired
  `--reasoning-activation`/`--hf-model-id` — the two-pass forcer silently ran QWEN machinery
  (ChatML render, `</think>` stops) against Gemma; manifest honestly recorded
  `qwen_thinking_native_v1`. NOT a server-budget issue (forcing runs on raw `/completions`,
  server reasoning flags inert there; pinned argv unchanged). Fixed fail-closed per
  `docs/foundations/bench-reasoning-activation-spec-2026-07-02.md`: bench flags (required for
  capped-thinking, rejected otherwise) + publishable guards (registry entry must exist,
  model_family must match `entry.model_match`, hf_model_id required). Validation mini-run
  (10-item ifbench+tc_json, gemma4 activation): ifbench 10/10, tc_json 9/10, **20/20 per-item
  verdict agreement with the June-29/30 pilot on identical items**, zero leaks/truncation,
  registry entry `gemma4_thinking_native_v1` recorded. Canary (P3, ASK FIRST) is now unblocked;
  its command MUST include `--reasoning-activation gemma4 --hf-model-id unsloth/gemma-4-12b-it`.

## Operating protocols (owner-confirmed 2026-07-02)
- **GPU**: mini-runs ≤30 min (probes, serve-smokes, 20-item runs) = standing grant, announced
  before firing. Full runs (13h canary, agentic campaigns, ranked run) = explicit ask each time.
- **Commits**: reviewed work commits at milestones (board_v1 byte-identity checked every commit).
- **Deploys**: private-mode redeploys to `deploy/main` allowed as needed, each announced + followed
  by `launch-smoke -ExpectedMode Private` + alias-leak check. `LOCALBENCH_SITE_PRIVATE` stays `1`.
  **Public flip is exclusively Michael's call.**
- Division of labour unchanged: Codex (GPT-5.5 xhigh) implements; Claude manages/reviews/tests;
  oracle red-teams key architecture (browser engine only). board_v1 frozen `3d058e60`.
