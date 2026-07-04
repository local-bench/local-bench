# v1 expanded-scope plan (oracle-reviewed, 2026-06-23)

## LAUNCH SEQUENCING — COMBINED v1+v2 (Michael, 2026-06-23) — SUPERSEDES "ship v1 first"
Michael: do NOT ship publicly until v2 (community submissions) is sorted, implemented, AND QA'd.
ONE combined launch of the COMPLETE product (run -> submit -> verify -> on the board), not a v1
read-only board followed by a v2 fast-follow. Consequences:
- No imminent deploy. The "Cloudflare creds in the AM" ask is DEFERRED until the whole product is
  built + QA'd (creds then cover site + wheel + suite + the v2 R2/Workers backend in one go).
- The functional-distribution decision (v1-distribution-plan.md) is now unambiguously right: it IS
  v2's foundation, so we build it ONCE, cleanly, with no v1->v2 migration seams. The
  v2-execution-plan "Phase 0 overlaps v1, rest is post-launch" framing is moot — there is no
  separate v1 launch.
- Build sequence to the single launch: complete the board (gemma -> 3 families -> agentic full
  coverage) || the distribution layer || the full v2 stack (verify -> ingest -> board-merge ->
  spot-reproduction -> sentinel) -> END-TO-END QA -> one public launch.
- Timeline: realistically ~1-2 months (solo maintainer, one serial GPU, agentic full-coverage is
  the GPU pole, v2 has real depth, plus end-to-end QA). No rush pressure — build deliberately.
- OPEN LEVER: the v2 completion BAR for launch — honest MVP loop (run->submit->verify->merge->
  display + sampled spot-reproduction) vs full anti-gaming hardening (automated SPRT + large
  sentinel banks). Recommended read: launch on the honest loop + core verification + sampled
  reproduction; deepest hardening = post-launch v2.1. Confirm with Michael when scoping v2.
- RISK on record (flagged, not a course-change): a long pre-launch build = no public presence or
  early feedback + board data can drift (models keep shipping). Mitigate: pin exact upstream
  revisions; optional private beta.

Source: GPT-5.5 Pro (oracle) consult `localbench-expanded-scope-sequencing`, red-teaming
Michael's decision to add the agentic axis + a few more model families to v1. This is the
binding plan for the expanded v1. Full transcript: oracle session of the same slug + the run
output. Weighed + adopted by the CLI orchestrator.

## The ship shape (decision) — SHIP COMPLETE (Michael, 2026-06-23)
**Michael's directive: ship v1 COMPLETE, not partial; rollout timing extends as needed.** So
agentic is FULLY MEASURED across EVERY v1 ranked system before launch (full 96-task coverage, not
a token anchor panel), and launch gates on that completeness. We are no longer time-boxed to
"days" — we take the time to do the agentic/AppWorld wiring correctly (exactly what the oracle
wanted: do not rush AppWorld).

- **Headline label stays "Intelligence Index"** (Michael's call) + a prominent scope banner.
- **Agentic is measured for ALL v1 systems** (Qwen ladder + gemma + the 3 families) at the
  96-task panel. Because coverage is now complete and we will have >=8 systems with both Core
  Text + Agentic measured, the coverage + non-redundancy gates ARE now reachable.
- **Composite inclusion is GATE-DEPENDENT — decided by the data, not forced:**
  - If agentic passes discrimination + non-saturation + stability + non-redundancy + full
    coverage -> PROMOTE into a 3-axis composite: Knowledge 0.40 / Instruction 0.40 / Agentic 0.20
    (NOT equal thirds at n=96), with an index version bump + changelog entry.
  - If it fails a gate (e.g. saturated or non-discriminating) -> ship as a FULLY-POPULATED,
    clearly-labelled candidate column (weight 0). Still "complete" (measured everywhere), just not
    folded into the headline because the data says it should not be. This keeps us honest.
- **Hard correctness rule preserved:** an axis never enters the ranked composite unless EVERY
  ranked row has it measured under the frozen scorecard (no missingness bias).
- **Critical-path consequence:** the agentic AppWorld wiring + the 96-task coverage run are now
  LAUNCH GATES (not a fast-follow). The GPU queue + AppWorld install/verify/freeze/feasibility
  below are the long pole; deploy waits for them + the full credibility layer.

## Model scope (decision): +3 family representatives, single quant each
Value is in MORE FAMILIES, not more quants (Qwen already told the quant story; Q4 plateau).
One canonical quant per added family (Q4_K_M or nearest stable llama.cpp quant that fits 32GB).
Treat every row as a model SYSTEM (base + quant + runtime + template + reasoning mode + cap +
extractor). Hard cap: 3 new families (4 only if everything else is green).

GPU-priority order for the additions (Core Text capped-thinking, conformance slice then full):
1. **Nemotron 3 Nano 30B-A3B** (Q4-ish) — NVIDIA, agentic/reasoning positioning, small-active
   MoE practical on 32GB. Must be the local GGUF system, not NIM/API. (registry: nemotron)
2. **DeepSeek-R1-Distill-Qwen-32B** (Q4-ish) — known reasoning lineage, consumer-GPU size class.
   Label "R1-Distill-Qwen", not a clean independent family. (registry: r1)
3. **Granite** best native-thinking entry that passes conformance (likely small/mid). Breadth +
   openness signal (Apache-2.0). If only 8B, call it a "small-family anchor". (registry: granite)
4. OPTIONAL **Magistral Small 24B** (Mistral reasoning) — only if the reasoning-registry entry is
   clean + the conformance slice passes WITHOUT bespoke fixes. (registry: NOT yet supported)

Do NOT: build full ladders for the new families; chase giant MoE (GLM-5.2, Kimi) for the 32GB
local headline lane (runtime/offload/thinking-control risk turns a clean board into a
runtime-exception board).

## GPU queue (serial, one 5090)
1. Finish gemma-4-31B Q4 capped-thinking rerun. If conformance fails -> mark gemma pending; do
   NOT tune for a better number.
2. While real AppWorld wiring is not ready: run Core Text conformance/full for the new families
   in the order above.
3. As soon as real AppWorld smoke is ready: PREEMPT after the current job, run the 12-task smoke
   on one weak + one strong local model (earliest detector of JSON-format / per-turn-token /
   tool-call-budget / state-reset / adapter failures).
4. If smoke fails (bad adapter/protocol): STOP scored agentic; fix only on train/dev; bump the
   scorecard hash; never reuse observed test failures.
5. If smoke passes: 36-lite (determinism + failure-mode distribution; NOT public ranking).
6. 96-task candidate for a BOUNDED anchor panel only (weak 7-9B, mid 14-17B, Qwen3.6-27B Q4,
   gemma Q4 if it passes). NOT every Qwen quant.
7. Freeze board_v1.json from the scorer. Site renders only.

## CPU/dev tracks to run concurrently while the GPU is busy
- Site/methodology: scope banner ("Core Text Index v1 + AppWorld-lite JSON candidate axis"),
  candidate-axis explainer, tie language, "no LLM judge != complete coverage". (site agent)
- AppWorld real env: clean Python 3.11 env (SEPARATE from the pinned 3.14), pin package
  version/commit, `appworld install`, `appworld download data`, `APPWORLD_ROOT` OUTSIDE the repo
  and outside any path the model/tool layer can read, hash the data tree, record dataset IDs.
- AppWorld verify: `appworld verify tests` + `appworld verify tasks` in the exact harness env.
  A stub test suite is no longer evidence.
- Adapter freeze BEFORE any scored subset: schema, tool namespace, API-doc exposure, retry,
  timeouts, max turns/tool-calls, final-answer handling, failure categories, observation
  canonicalization, transcript hashing.
- Manifest: iterate protocol on train/dev ONLY; select the test subset deterministically from
  task IDs (no inspecting task text / ground-truth / eval reports / failures).
- Model prep: download + hash GGUFs, model-system IDs, registry entries, CPU parser/template
  smoke.

## Agentic display + gates (for when data lands)
- Display: `ASR 42% [33, 52] n=96`, integer %, **Wilson** CI (n=96 = min defensible; n=36 too
  wide for ranking). NOTE: agentic ASR uses Wilson CI; the headline composite uses bootstrap
  percentile — do not cross them.
- Promotion gates (all required): validity (`appworld verify` green + scripted non-LLM agent
  proves state reset/eval + adapter audit >=95% agreement + zero ground-truth exposure +
  no post-test changes); discrimination (>=20pp top-weak, top lower-bound > weak upper-bound by
  5pp, family/band separation); non-saturation (fail if top-3 >85% / strongest <15% / >25%
  solved-by-all / >35% solved-by-none / invalid-JSON >15% for strong models / cap-hits explain
  >10% of strong-model failures); stability (repeat 96, <=2 flips or <=3pp); non-redundancy
  (>=8 systems, Spearman vs Core Text not ~perfect); coverage (every ranked row measured).

## AppWorld traps — do NOT cut even under time pressure
- Real install + verify before any GPU scoring. Keep `APPWORLD_ROOT` outside repo + agent reach.
- It is a STRICT JSON tool-call protocol, not code-as-action: name it "AppWorld-lite JSON
  tool-call axis", never "AppWorld score". Not comparable to the official AppWorld leaderboard.
- Prove JSON feasibility (min tool-calls on scripted real dev tasks) BEFORE freezing the 96-task
  manifest. Many tasks may need >11 tool-calls under one-call-per-turn; if gold paths exceed the
  cap, raise the cap / pick fitting tasks / add a bounded batch action (= new scorecard id).
  Never let infeasible tasks create fake model failures.
- Do NOT iterate on test failures; do NOT publish protected task material / raw transcripts /
  decrypted bundles / API-doc dumps / eval traces / ground truth (AppWorld has a public/protected
  split + encrypted-redistribution rules). Publish hashes, aggregate scores, family/band labels,
  diagnostics.
- Fresh world per task; one model loaded at a time; no shared servers/state; no parallel tasks
  on one server; `PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C.UTF-8`; plain-text JSON (no
  grammar-constrained decoding in the scored lane — invalid JSON IS part of the measured system).

## Public honesty framing (v1)
- Scope banner (front page, not buried): "Local Intelligence Index v1 - Core Text: MMLU-Pro 400 +
  IFBench 294, 50/50, capped-thinking lane, RTX 5090 32GB. Candidate axes shown separately,
  weight 0 unless promoted in a versioned formula."
- "Judge-free" line: "objective/programmatic/exact scoring only - removes LLM-judge subjectivity,
  but does NOT make the benchmark complete, contamination-proof, or immune to harness artifacts."
- Agentic disclaimer: "Agentic Exec v0 is an AppWorld-substrate, local-bench JSON tool-call
  protocol; not AppWorld code-as-action; not directly comparable to the official AppWorld board."
- Pre-register the family-addition rule + list SKIPPED families with reasons (avoids
  cherry-picking optics).
- Reproducibility claim = "artifact-level reproducibility" (immutable board JSON/CSV, manifest +
  suite + prompt/extractor/registry hashes, transcript/result hashes, exact formula) — NOT
  "fully open reproducibility" while the repo is private.
- Three visible axis categories: Ranked Index domains (Knowledge + Instruction) / Candidate
  measured axes (Agentic, weight 0) / Deferred axes (Math, Coding, Long-Context). A candidate
  column NEVER affects sort, rank, tie language, or index version unless promoted.
- Overall positioning: "single-GPU, judge-free, reproducible local systems board" — NOT "the
  open-weight intelligence leaderboard".

## v2 forward-compat — apply DURING the board-build review (from the v2 plan, 2026-06-23)
Full plan: `docs/foundations/v2-execution-plan.md`. Recommended v2 intake = **Option A**: a signed
run-artifact upload to a Cloudflare Worker + R2, server-side re-score authoritative (holds the
owner's anonymity by construction; public-GitHub-PR intake is RULED OUT — re-leaks identity).
Bake these into v1 NOW so v2 adds rows instead of migrating schemas:
1. **Run-JSON/transcript = the future submission bundle.** Keep `schema_version` explicit +
   checked; preserve the per-item `reasoning_text` (separate channel) + `finish_reason` +
   `extracted` + `correct` + `usage`. Do NOT drop the reasoning-channel separation —
   `lane_conformance.py` distinguishes leaked-into-`response_text` from clean `reasoning_text`,
   and v2 re-scores from these items.
2. **board_v1.json = the single scoring spine.** Site stays a PURE renderer (zero score math in
   web/). Make `index_version` a real monotonic bumpable field. Add a per-row `source` field
   (constant "project-anchor" for all v1 rows) so v2 submission rows are the same shape — relay to
   the site agent to mirror it in `IndexModelSchema`. Factor the board generator's anonymity
   scrub as a REUSABLE function (v2 runs the identical scrub over submitter metadata — a submitter
   run JSON also carries `C:\Users\<them>\...` `output_path`).
3. **Lane sampler + artifact identity.** Pin `top_k=1` (single-sampler) in the suite + verify a
   byte-for-byte NO-OP vs existing numbers before v2 (may already be validated — confirm the
   earlier top_k no-op check). Give the CLI a path to populate `model.file_sha256` / tokenizer /
   chat-template digests (today `"UNHASHED"`/`"unknown"`, `integrity.canonical=false`) — required
   for the future "spot-reproduced" trust tier.
4. **Trust vocabulary: NEVER a blanket "verified".** If any v1 UI/label says "verified", rename to
   "project anchor" now (renaming a public trust label post-launch is a credibility cost). Relay
   to the site agent.

## Board build status (2026-06-23) — VERIFIED, with follow-ups
Codex built the `localbench board` generator: `cli/src/localbench/scoring/board*.py` (+5 modules)
+ tests; additive cli.py subcommand; `axes.py` untouched (only the deferral comment). Independent
review: bootstrap-percentile CIs (correct), hashes match the methodology agent's, honest null
sampling pins, gemma graceful-skip, **parity vs web index = zero divergence**, anonymity test
passes. Artifact: `cli/runs/board/board_v1.json` + `.manifest.json`, board_sha256
`04dbff65…1eb44a`. (Pytest independent re-run pending confirmation of 695 passed.) NOT committed
yet — the working tree has unrelated pre-existing uncommitted work; commit the board as a
deliberate, scoped change later, not a 1am sweep.

Follow-ups before the board is launch-final:
1. **Per-quant / per-run detail.** board_v1.json currently emits INDEX rows only (the Qwen quant
   ladder is collapsed to its best run = Q6_K, n_runs 5). The per-quant ladder (the Q4-plateau
   story) + per-model run detail are still assembled by `build_data.py`. Confirm whether
   build_data.py RECOMPUTES composite/CI there (= score math in web, breaks "pure renderer") or
   only reads canonical run-JSON scores. For full pure-renderer, extend the generator to also emit
   per-run/per-quant scores (ModelRunSchema shape). Resolve in the relay with the site agent.
2. **Apply the v2 forward-compat items above** in the next board pass: per-row `source`
   ("project-anchor"); monotonic `index_version`; confirm the anonymity scrub is a REUSABLE
   function (v2 needs it for submitter metadata).
3. **Index-row quant selection.** Board headlines the BEST quant (Q6_K 75.25). Decide best-quant
   vs recommended/plateau-quant (Q4_K_M 74.9) for the index row. best-run matches current
   index.json (parity passed) — keep unless we add a "recommended quant" concept.
4. **Site relay packet to assemble:** board_v1.json schema + sample + compute boundary (+ resolve
   #1) + release manifest (board_sha256); the reasoning-activation map (from
   reasoning_registry.py); CLI flag-stability confirm (cli.py); invalid/format/truncation field
   names (present per-axis: leaked_reasoning_rate, truncation_rate, no_final_answer_rate, n_errors,
   n_no_answer, termination_rate, conditional_accuracy); tie rule = overlapping 95% CIs; the
   "verified"->"project anchor" rename.
