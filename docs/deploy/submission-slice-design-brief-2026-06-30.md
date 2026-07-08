# Submission-slice design brief — for GPT-5.5 Pro red-team (2026-06-30)

You are red-teaming the **design** of the first end-to-end submission slice for **local-bench**,
a public benchmark for *local* LLMs (run on your own GPU). This is a pre-implementation
architecture review. Be adversarial: attack the design, find what will fossilize wrong, name
the smallest correct slice. Do not write code — critique the plan and propose the design.

## 1. What local-bench is, and the goal

local-bench ranks local models on a **Local Intelligence Index** (5 headline axes, canonical
weights from `cli/src/localbench/scoring/axes.py`, which is the single source of truth):

- **Agentic** (`appworld_c`) **0.50**
- Knowledge (`mmlu_pro`) 0.15
- Instruction-Following (`ifbench`) 0.15
- Tool-calling (`tc_json_v1`) 0.10
- Coding (`lcb`) 0.10
- (Math, Long-Context = candidate axes, weight 0.0)

The site is live on Cloudflare Pages (`local-bench.ai`) but **private-gated** (503 to the public
via `LOCALBENCH_SITE_PRIVATE=1`). Backing infra exists: **D1** (`localbench_prod`), **R2**
(`localbench-submissions` + `localbench-public-artifacts`), a verification **Queue**
(`localbench-verification`). Three secrets (`ADMIN_API_SECRET`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`) are deliberately UNSET — the submission/admin backend is non-functional
until the owner mints R2 creds and flips them.

**The goal (owner's intent):** dogfood the *real* user path so the first published benchmarks
travel it, exactly as an external local user would: **pull the suite from the site → run locally
against the model → submit the result bundle back through the site → verify → publish to the
board.** The owner (Michael) is user #0 / trusted submitter. We explicitly do NOT want a
local-only shortcut for the first published row.

**The agreed 4-step plan:** (1) local calibration pilot first [DONE — see §3], (2) freeze the
`result_bundle_v1` contract from the pilot bundle, (3) **build a thin end-to-end submission slice
— happy path only, one model, no multi-user/trust-tier machinery yet** [THIS is what you are
red-teaming], (4) resubmit the pilot through the slice = submission #1 + first board row.

**The named risk:** *schema fossilization* — building the full pipeline before seeing one real
result bakes the wrong bundle/D1/board schema in (expensive to undo). Mitigation was to run the
pilot first and freeze the contract before building the slice. We now have the pilot bundle.

## 2. Hard constraints

- `cli/runs/board/board_v1.json` is FROZEN (byte-identical, never modified).
- Nothing is pushed to the public site repo without explicit owner say-so.
- The 3 secrets stay unset until the owner mints least-privilege R2 creds for go-live.
- Confidentiality: local-bench is the owner's own non-client project (fine to reason about).
- Division of labour: Codex (GPT-5.5) implements; Claude orchestrates/reviews/tests. You are the
  architecture red-team, not the implementer.

## 3. The golden-fixture result bundle (the pilot, just completed)

A ~13h calibration run of Gemma 4 12B QAT (UD-Q4_K_XL) on an RTX 5090, plain llama.cpp
`llama-server` OpenAI-compatible endpoint, `lane=capped-thinking` (s1-style think-budget
forcing), `tier=standard`. `state=complete exit_code 0`, 1153/1153 items, **zero infra errors**.

Per-axis (raw_accuracy): knowledge 0.7725 (chance-corrected 0.7446), instruction 0.6871,
tool_calling 0.7364, coding 0.8527. Partial `composite` = **0.7473** (chance-corrected,
weight-renormalized over the 4 *measured* axes only). `headline_complete: false`.

**The bundle (`localbench-run.json`, schema `localbench.run.v1`) top-level keys:**

```
schema: localbench-run-v0 ; schema_version: localbench.run.v1
submission_ticket_id: null ; server_nonce: null ; issued_at: null   # reserved submission hooks
run_started_at / run_finished_at ; source: localbench-cli ; tier: standard ; account: null
model: {name, file_sha256:null, tokenizer_digest:null, chat_template_digest:null}
manifest: {schema_version, suite, scorecard, endpoint, model, runtime, hardware, sampling,
           execution, rendered_prompt_sample, integrity}
axis_status: {schema_version, axes{<axis>: {status: measured|not_measured, reason, detail}}}
headline_complete: false
trust_tier: external-endpoint ; serving_verification_level: external-endpoint
benches: {mmlu_pro, ifbench, tc_json_v1, lcb}
composite: 0.7473
conformance: {status: "headline-comparable", n_scored, worst_bench, reasons, per_bench{
              <bench>: {status, n_scored, truncation_rate, leaked_reasoning_rate,
                        no_final_answer_rate, reasons, forced:true}}}
items: [1153 x {id, bench, response_text, extracted, correct, finish_reason, latency_seconds,
        started_at, finished_at, attempts, usage, error, reasoning_text}]
totals: {n_items, n_errors, prompt_tokens, completion_tokens, total_tokens, wall_time_seconds,
         completion_tokens_per_second}
warnings: ["appworld sandbox unavailable: appworld package not importable; ..."]
output_path
```

Key manifest sub-blocks:
- `manifest.suite`: {suite_id: "core-text-v1", suite_version: "suite-v1", suite_hash:
  "e9db1528…", source: "suite-dir", tier, item_set_hashes{4 jsonl}, lane: "capped-thinking",
  caps{max_tokens_mcq:16384, max_tokens_math:0, thinking_budget:8192}, accepted_suite_terms,
  license_manifest}.
- `manifest.scorecard`: {scorecard_version: "scorecard-v2.1", registry_digest,
  reasoning_registry_digest, reasoning_registry_entry_id: "gemma4_thinking_native_v1",
  scorer_versions{14 benches}, ci_method: "stratified-nonparametric-bootstrap-percentile",
  scorecard_id: "30d33810…", registry[full axis registry w/ weights]}.
- `manifest.sampling`: {temperature:0, top_p:null, **top_k:null**, min_p:null, **seed:null**,
  thinking_mode, by_bench{...}, reasoning_registry_entry_id}.
- `manifest.runtime`: {name:null, version:null, kv_cache_quant:"unknown", ctx_len_configured:null,
  parallel_slots:null, build_flags:null}.  ← all unpopulated
- `manifest.hardware`: {gpus:[{name:"RTX 5090", vram_mb:32607, driver:"596.36"}], cpu, ram_gb:null,
  os:"Windows-11-…"}.
- `manifest.execution`: {client_version:"localbench 0.1.0", concurrency:1, started/finished,
  wall_clock_s:46611, measured_tok_s, per_item_timing}.
- `manifest.rendered_prompt_sample`: {item_id, messages}  ← prompt-template fidelity sample.
- **`manifest.integrity`: {canonical: FALSE, missing_fields: [model.family, model.quant_label,
  model.file_name, model.file_size_bytes, model.file_sha256, model.format, model.tokenizer_digest,
  model.chat_template_digest, runtime.name, runtime.version, runtime.kv_cache_quant,
  runtime.ctx_len_configured, runtime.parallel_slots]}.**  ← the bundle self-audits its own
  publish-readiness and enumerates exactly what is unpopulated.

`axis_status` records agentic as `not_measured / sandbox_unavailable` ("appworld package not
importable; APPWORLD_ROOT not set; bubblewrap (bwrap) not found"); math + long_context
`not_measured / not_run`. `conformance` is `headline-comparable` for all 4 measured benches, with
`forced: true` and documented answer-cap-hit rates (4–7%), leaked_reasoning_rate 0 everywhere.

**Observation:** the bundle is ~90% of a `result_bundle_v1` contract already, *and it self-reports
`canonical:false` plus the exact delta to publishable.* So "freeze the contract" looks like:
adopt `localbench.run.v1` as `result_bundle_v1`; define the canonical-publishable delta =
`integrity.missing_fields` + a real sampler pin; make the runner populate them.

## 4. The suite-alignment problem (critical, must shape the slice)

Three different "suites" with different axis-coverage and different hashes are in play:

| Artifact | Axes runnable on a plain endpoint | Missing | Composite weight |
|---|---|---|---|
| Canonical headline (`axes.py`) | knowledge, instruction, tool_calling, coding, **agentic** | — | 1.00 |
| **Pilot** (`suite/v1` dir, standard+capped-thinking) | knowledge, instruction, tool_calling, coding | **agentic** | 0.50 |
| **Site bundle `core-text-v1`** ("pull from site") | knowledge, instruction, tool_calling | **coding(lcb)** + agentic† | 0.40 |

† `core-text-v1` ships only mmlu_pro/ifbench/tc_json_v1; declares agentic(`appworld_c`) membership
"only when localbench is installed with the appworld extra"; agentic needs a sandbox env
(`scoring/agentic_exec/`, bubblewrap), not a plain endpoint. It ships NO `lcb`.

So: "pull suite from site → run → board" currently yields a **3-axis / 0.40-weight** result; the
pilot adds coding but not agentic; the **agentic axis (0.50 — half the index)** is reachable
through neither path without the appworld extra + env. Three+ suite_hashes observed
(`6b7b80de` recorded in notes / `e9db1528` pilot-effective / `c1ee1d99` released core-text-v1).
There is also an apparent membership divergence: `suite/v1/suite.json` maps agentic =
[bfcl, bfcl_multi_turn] while `axes.py` maps agentic = [appworld_c].

## 5. Acceptance gates already written (summarize, then critique)

Gate A (publish-gate, all P0): lane/sampler frozen (no ambiguous temperature=0-only unless
labelled non-final); complete model-system identity (file sha256, quant, tokenizer/chat-template
hash, runtime/engine/build, GPU/driver/CUDA/OS); runner+scorer provenance pinned (repo commit,
dirty-tree, scorecard_id, suite_hash, extractor version); complete artifact bundle reproducible
offline with no site/D1 contact; prompt-template fidelity; explicit invalid/refusal/truncation
accounting; scorer determinism (byte-identical rescore); reproducibility from artifacts;
statistical sufficiency visible (per-axis n + CIs, not files=11); tamper-evidence (release
manifest hashing every file; board row carries bundle+scorecard hashes); no unrecorded manual
path; redaction/license pass (no local usernames/Windows paths/secrets in public artifacts).

Gate B (pipeline-unblock): first bundle validates under the future submission-bundle validator;
validator emits a deterministic accepted-result projection containing every public-board field;
D1 = index rows pointing to immutable bundle hashes (D1 is NOT scoring truth); trust labels frozen
conservative (`community re-scored`, `spot-reproduced`, never `verified`); format represents both
`origin: project_anchor` and `origin: community_submission`; same scorer path for both; bridge
test with no D1 reproduces the public board row from `validate-submission-bundle` + `rescore-bundle`.

## 6. Questions to red-team (be specific and adversarial)

1. **Smallest correct slice.** What is the minimal happy-path slice that genuinely exercises
   pull→run→submit→verify→publish without baking in wrong schema? What must be real now vs deferred?
2. **Submission protocol.** Ticket/nonce flow (`submission_ticket_id`/`server_nonce`/`issued_at`
   are reserved in the bundle): who issues, what does it bind, replay/idempotency, what stops a
   forged/edited bundle? Is a ticket even needed for user #0, or does it fossilize a wrong model?
3. **Bundle vs projection.** The full bundle is 20MB (1153 transcripts incl `reasoning_text`).
   Upload the whole thing to R2? Define a separate immutable full-bundle (hashed) vs a public
   "accepted_result_projection" for the board? What's the boundary?
4. **Verification on Cloudflare.** The verifier must rescore from the bundle deterministically
   ("same scorer path", "byte-identical rescore"). But the scorer is Python (`localbench.scoring`)
   and the Queue consumer is a Workers runtime. Where does authoritative rescoring actually run?
   Does this force a Python verifier service, or a re-run, or trusted-submitter-signs-it for v0?
5. **The headline/coverage problem.** Agentic (0.50) is unmeasurable on a plain endpoint. For the
   FIRST board row, is the right move (a) publish a clearly-labelled 4-axis partial
   (`headline_complete:false`, composite 0.7473, agentic="not measured"), (b) block publishing
   until agentic runs, or (c) something else? How do you show partial coverage on a public board
   without enabling misleading rank comparisons against a future full-5-axis row?
6. **Suite distribution.** For honest "pull-from-site" dogfooding, must the site serve a suite
   that reproduces the headline (add lcb + a runnable agentic path), or is `core-text-v1` a
   deliberate headline-*subset* public bundle? If the pilot ran `suite/v1` but the site serves
   `core-text-v1`, did we even dogfood the real pull path? Reconcile.
7. **Canonical suite_hash.** Which of the 3+ hashes is the one a verifier recomputes and a board
   row pins? How should suite identity be canonicalized so submitter and verifier agree?
8. **D1 schema.** Concretely, what are the index-row columns (pointers to immutable bundle hashes)
   for v0, designed so the multi-user/trust-tier system later extends rather than rewrites them?
9. **Sequencing vs the lane defect.** `top_k`/`seed` are null (temperature=0 ≠ guaranteed greedy
   in llama.cpp). Should submission #1 wait for a `top_k=1`+seed re-run (a true publishable wave),
   or is the calibration bundle acceptable as a clearly-labelled submission #0 to exercise the
   pipeline? Which order minimizes fossilization + rework?
10. **What will bite us later?** Name the one or two design choices in this slice most likely to
    be regretted when the real multi-user / community-submission / trust-tier system is built, and
    how to hedge them now cheaply.

Please give: (a) a recommended minimal slice design (component by component), (b) the explicit
`result_bundle_v1` freeze recommendation (adopt-as-is vs change-first), (c) your answer to the
headline-coverage and suite-distribution decisions, (d) the top fossilization risks and hedges,
(e) a recommended build order for Codex.
