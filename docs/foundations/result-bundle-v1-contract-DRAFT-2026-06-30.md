# result_bundle_v1 — contract proposal (DRAFT, 2026-06-30)

> **⚠️ SUPERSEDED 2026-06-30 by the oracle red-team.** This draft proposed *adopt the schema
> as-is* with a two-tier (T1/T2) accept. GPT-5.5 Pro's red-team (transcript in the session;
> recorded in memory `project-local-bench-site-submission-plan`) instead requires: **split into
> THREE contracts** — `result_bundle_v1` (pure measurement/audit), `submission_envelope_v1`
> (ticket/auth/upload, moved OUT of the bundle), `accepted_result_projection_v1` (verifier-derived
> public board fields) — and **change the schema before freezing** (collapse the dual schema id;
> move trust/submission fields out; scoped score fields instead of bare `composite`; rename
> `integrity.canonical`→`integrity.publishable`+blocking_reasons; add suite-release-manifest
> identity + a `manifest.provenance` block; require sampler pin + model/runtime identity for
> publishable; sanitize `output_path`). The T1/T2 idea survives as `integrity.publishable`. Treat
> the field inventory below as raw input to the new three-contract spec, not the contract itself.
>
> **STATUS (original): DRAFT PROPOSAL — NOT FROZEN.** See
> `docs/deploy/submission-slice-design-brief-2026-06-30.md` (red-team brief) and
> `docs/deploy/suite-alignment-finding-2026-06-29.md` (coverage problem).

## Proposal in one line

**Adopt the schema the runner already emits (`localbench.run.v1`) as `result_bundle_v1`** — the
pilot (`runs/campaigns/wave0-gemma-12b-q4xl-cal-20260629/localbench-run.json`) validated it on a
real ~13h run. Do **not** invent a new schema. Define a two-tier acceptance (valid vs canonical)
keyed off the schema's own `manifest.integrity` self-audit. The architectural questions around it
(verification execution, bundle-vs-projection split, D1 schema, suite canonicalization, trust
labels, headline-coverage policy) are **explicitly deferred to the red-team** — this contract
fixes only the *bundle shape*, not the pipeline around it.

## Why adopt-as-is

- It is the golden fixture (plan's golden-fixture-first principle): we are freezing what a real
  result *is*, observed, not guessed.
- It is already comprehensive and — crucially — **self-auditing**: `manifest.integrity.canonical`
  + `manifest.integrity.missing_fields` tell us exactly the gap between a calibration bundle and a
  publishable one. The contract can lean on that rather than re-deriving it.
- It already carries the submission hooks (`submission_ticket_id`, `server_nonce`, `issued_at`),
  partial-coverage honesty (`headline_complete`, `axis_status`), and conservative trust labelling
  (`trust_tier`) — so the slice extends it rather than reshaping it.

## Two-tier acceptance

| Tier | Definition | Use |
|---|---|---|
| **T1 — valid bundle** | All structural fields present + parseable; scorer ran; `conformance` computed. `manifest.integrity.canonical` MAY be false. | Accepted into the submission pipeline; may appear only as **non-final / calibration**, never as a ranked published row. |
| **T2 — canonical / publishable** | T1 **and** `manifest.integrity.canonical == true` (i.e. `missing_fields == []`) **and** sampler pinned (see §Delta). | Eligible to be **published** as a board row. |

The pilot bundle is **T1** today (`integrity.canonical: false`). This is the right gate: the
pipeline can be exercised end-to-end with a T1 bundle (plan step 4) while publishing waits for T2.

## Required field inventory (top-level)

All present in the pilot bundle unless marked. `R`=required for T1, `P`=additionally required/asserted for T2.

- `schema` = `localbench-run-v0`, `schema_version` = `localbench.run.v1`  — **R** (version pin)
- `submission_ticket_id`, `server_nonce`, `issued_at` — **R-nullable** (null for local; populated by the slice on submission — exact semantics = red-team Q2)
- `run_started_at`, `run_finished_at`, `source`, `tier` — **R**
- `model{name, file_sha256, tokenizer_digest, chat_template_digest}` — **R** name; **P** the three digests (null in pilot)
- `manifest{...}` — **R** (see below)
- `axis_status{axes{<axis>:{status, reason, detail}}}` — **R** (drives partial-coverage display)
- `headline_complete` (bool) — **R**
- `trust_tier`, `serving_verification_level` — **R** (conservative label; pilot=`external-endpoint`)
- `benches{<bench>:...}`, `composite` (float), `conformance{...}` — **R**
- `items[]{id,bench,response_text,extracted,correct,finish_reason,latency_seconds,started_at,finished_at,attempts,usage,error,reasoning_text}` — **R** (complete artifact; Gate A item 4)
- `totals{n_items,n_errors,prompt_tokens,completion_tokens,total_tokens,wall_time_seconds,completion_tokens_per_second}` — **R**
- `warnings[]` — **R** (records *why* an axis was skipped; pilot logged the appworld absence here)
- `output_path` — **R** (local; redact/strip for public artifact — Gate A item 12)

### manifest sub-blocks
- `suite{suite_id, suite_version, suite_hash, source, tier, item_set_hashes{}, lane, caps{}, accepted_suite_terms, license_manifest}` — **R**. (suite_hash canonicalization across the 3 observed hashes = red-team Q7.)
- `scorecard{scorecard_version, registry_digest, reasoning_registry_digest, reasoning_registry_entry_id, scorer_versions{}, ci_method, scorecard_id, registry[]}` — **R** (provenance + determinism anchors; Gate A items 3,7).
- `endpoint{kind, runtime_reported_model, api_provider, provider, divergence_notes}` — **R**.
- `model{family, quant_label, file_name, file_size_bytes, file_sha256, format, tokenizer_digest, chat_template_digest}` — **R** structure; **P** all values non-null.
- `runtime{name, version, kv_cache_quant, ctx_len_configured, parallel_slots, build_flags}` — **R** structure; **P** all values non-null.
- `hardware{gpus[]{name,vram_mb,driver}, cpu, ram_gb, os}` — **R**; **P** ram_gb + a CUDA/runtime-version field (currently absent).
- `sampling{temperature, top_p, top_k, min_p, seed, thinking_mode, by_bench{}, reasoning_registry_entry_id}` — **R**; **P** see Delta (top_k + seed must be pinned).
- `execution{client_version, concurrency, started_at, finished_at, wall_clock_s, measured_tok_s{}, per_item_timing}` — **R**.
- `rendered_prompt_sample{item_id, messages}` — **R** (prompt-template fidelity; Gate A item 5).
- `integrity{canonical, missing_fields[]}` — **R**. **This field is the T1→T2 gate.**

## The publishable delta (T2 requirements) — sourced from the bundle's own `integrity.missing_fields`

The pilot's `integrity.canonical:false` because these are unpopulated; the runner must fill them
before a publishable (T2) wave:

1. **Model identity hashes** — `model.file_sha256`, `tokenizer_digest`, `chat_template_digest`,
   `file_name`, `file_size_bytes`, `quant_label`, `format`, `family`. (Runner hashes the GGUF +
   tokenizer + chat template.) Gate A item 2.
2. **Runtime metadata** — `runtime.name/version/kv_cache_quant/ctx_len_configured/parallel_slots/
   build_flags` (capture from llama-server `/props` or launch flags). Plus `hardware.ram_gb` and a
   CUDA/runtime version. Gate A item 2.
3. **Sampler pin** — `sampling.top_k` and `sampling.seed` are null; `temperature=0` is NOT
   guaranteed-greedy in llama.cpp. **Pin `top_k=1` + an explicit seed** for any T2 wave. This is
   the known lane-spec defect (build-order item #1 in `submission-verification-design.md`) and the
   bundle confirms it is still unpinned. Gate A item 1.

When (1)+(2) are populated the runner should set `integrity.canonical=true` and `missing_fields=[]`;
(3) is a lane-config change, not just a capture gap — it changes the numbers, so a T2 row needs a
**re-run** under the pinned lane, not a re-stamp of the calibration bundle.

## What this contract deliberately does NOT decide (→ red-team)

These are the submission-slice *architecture*, out of scope for the bundle-shape contract:
- Verification execution model — where authoritative rescoring runs (Python scorer vs Workers
  Queue consumer); whether v0 is trusted-submitter-signs vs full rescore (brief Q4).
- Bundle vs public projection — upload the full 20MB bundle to R2 vs a hashed full-bundle + a small
  `accepted_result_projection` for the board (brief Q3).
- D1 index-row schema (brief Q8); suite_hash canonicalization (Q7); trust-label vocabulary (Q —
  Gate B `community re-scored`/`spot-reproduced`).
- Headline-coverage policy — publish the labelled 4-axis partial (composite 0.7473,
  `headline_complete:false`) vs block until agentic runs (brief Q5).
- Suite-distribution — does the site serve a headline-reproducing suite (add lcb + agentic) or is
  `core-text-v1` a deliberate subset (brief Q6).
- Sequencing — calibration bundle as submission #0 vs wait for the T2 `top_k=1` re-run (brief Q9).

## Open risk this draft itself carries
Freezing the bundle shape before the red-team rules on the bundle-vs-projection split (Q3) and the
verifier model (Q4) is a mild fossilization risk — if the verifier needs a different canonical
serialization (e.g. a separate hashed file set for tamper-evidence, Gate A item 10), the T2
definition here may need a companion "release manifest" file rather than a single JSON. Flagged for
the red-team; not resolved here.
