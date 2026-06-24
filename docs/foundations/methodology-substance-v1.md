# local-bench v1 — Methodology & Limitations (substance copy)

*Source copy for the public methodology/limitations page. Every technical claim below is verified
against the code in `cli/src/localbench/` and the frozen `suite/v1/suite.json` as of the
`forge-overhaul` branch. Where a claim could not be verified, it is marked `[UNVERIFIED: …]`.*

*Canonical specs this aligns with (do not contradict):
`docs/foundations/methodology-lock/METHODOLOGY-v1.2-LOCKED.md` and `docs/REPRODUCE.md`.*

---

## 1. Scoring formula

**What the Index is.** The front-page number is the **Local Intelligence Index
(`v1 · Core Text (Knowledge + Instruction)`)** — a composite of exactly **two** validated,
judge-free domains, measured on the **capped-thinking** lane:

- **Knowledge** — benchmark `mmlu_pro` (MMLU-Pro), composite weight **0.5**
- **Instruction-Following** — benchmark `ifbench` (IFBench), composite weight **0.5**

These two weights are the only non-zero composite weights in the system. They live in exactly one
place — the code registry `localbench.scoring.axes.AXES` — and everything else (the runtime
composite, the web build, the suite-membership drift test) derives from it. The registry enforces
at import that the headline weights sum to 1.0 and that no non-headline axis carries weight.

**The formula (verified in `localbench._scoring.composite`).** The composite is computed in two
stages:

1. **Pool benches into a domain (item-weighted).** Each domain's score is the item-count-weighted
   mean of its member benches' chance-corrected scores. In v1 each headline domain has a single
   bench, so this stage is a pass-through for the headline; it exists so a multi-bench axis (e.g.
   the candidate Math axis = `olymmath_hard` + `amo`) pools at the item level into one axis share
   rather than counting as two.
2. **Combine the headline domains by weight, normalized over the headline domains present.**

   ```
   Index = ( Σ_d  weight[d] · score[d] )  /  ( Σ_d  weight[d] )
           over headline domains d present in the run
   ```

   With both headline domains present and equal weights, this reduces to the **simple average of
   the chance-corrected Knowledge and Instruction scores**:

   ```
   Index = 0.5 · Knowledge_corrected + 0.5 · Instruction_corrected
   ```

Candidate axes (Math, Long-Context) and experimental axes (Agentic, Coding) carry weight **0.0**,
so a present-but-unvalidated axis is measured and displayed but never enters the Index. An unknown
domain defaults to weight 0.0 (never 1.0), so it can never silently dominate; a run with no
headline axis scores 0.0. A run missing one headline axis normalizes over the present headline
axis and is flagged **partial** (not comparable to a full headline run).

**Per-domain scoring is exact / programmatic — no model in the loop.**

- **Knowledge (MMLU-Pro)** is **exact-match** multiple-choice. The model's final answer letter is
  extracted programmatically (`localbench.scorers.mcq`): a hardened marker-anchored parser
  (`final answer: X` / `answer: X`, `\boxed{X}`, a bold letter only if it *ends* the response, a
  bare letter on its own line) with deliberate ambiguity handling — "A or B" adjacent alternations
  and terminal comma-lists ("answer: A, B") are treated as **no answer**, and a bold letter
  mid-reasoning is rejected. Correct iff the extracted letter equals the gold letter.
- **Instruction-Following (IFBench)** is **programmatic constraint-checking**
  (`localbench.scorers.ifbench`). Each item carries a list of machine-checkable instruction IDs
  (e.g. word/sentence counts, format, keyword constraints); each is verified by code. The item
  scores correct (`strict`) iff **every** instruction is satisfied. A check that raises is counted
  as a failure (fail-closed), and an empty response fails all checks.

**Raw vs corrected scores.** Each bench reports both a **raw accuracy** and a **chance-corrected**
score. Chance correction is the standard signed transform (`localbench.scoring.signed_score`):

```
corrected = (raw − chance) / (1 − chance)
```

The **composite is built from the chance-corrected scores.** The per-bench chance baselines are
pinned in `suite/v1/suite.json`:

- **MMLU-Pro** baseline **0.10918253968253969** (the mean of 1/n_options over the actual emitted
  v1 item set — MMLU-Pro items have up to 10 options, so chance ≈ 10.9%, not a flat 25%).
- **IFBench** baseline **0.0** (open-ended constraint satisfaction has no guess rate; raw =
  corrected).

The signed transform is used for inference and CIs without clamping; a separate cosmetic
`display_clamp` to [0, 1] exists for display only.

**Confidence intervals — bootstrap, not Wilson, for the headline.** Every displayed score carries
a CI. The headline CIs are produced by a **seeded, stratified, non-parametric percentile
bootstrap** over items (`localbench.scoring.bootstrap`); this is the `ci_method` recorded in every
run's scorecard: **`stratified-nonparametric-bootstrap-percentile`**. Items are stratified (e.g.
MMLU-Pro by subject) and resampled within strata; the composite CI is a nested item bootstrap that
re-pools and re-weights on every draw. Percentiles are the 2.5th and 97.5th (a 95% interval), seed
0 by default, 10,000 iterations by default. Bootstrap (rather than a closed-form binomial interval)
is used deliberately because suite items are not iid (subject/source clustering).

*A Wilson score interval does exist in the code, but it is used only by the candidate-axis
**discrimination gate** (`localbench.probe.gates`: the floor→frontier spread CI and upper-bound
parse/failure rates that decide whether a candidate axis may ever be promoted) and by the
experimental agentic-success-rate path — **not** by the headline composite. The headline number is
bootstrapped.*

---

## 2. Capping / failure policy (the capped-thinking lane in plain English)

The single headline lane is **capped-thinking**: reasoning is **on**, but the model's thinking is
held to a fixed budget so the score reflects a real, bounded operating point rather than unlimited
"think forever" compute. The locked parameters (METHODOLOGY-v1.2 §1, enforced in code):

- **Native thinking ON.** The model reasons in its own native thinking format (e.g. Qwen3's
  `<think>…</think>`, Gemma's thought channel). No "answer-only" suppression; this is how a real
  local user runs a reasoning model.
- **8192-token thinking budget.** The think budget is **8192 tokens**
  (`CAPPED_THINKING_THINK_BUDGET` in `localbench.budget_forcing`; also pinned per-bench-resolvable
  via the suite `lane_caps`, defaulting to 8192).
- **`max_tokens` ceiling 16384.** Every v1 bench pins `max_tokens: 16384` in `suite/v1/suite.json`
  as a runaway bound (a safety ceiling, not a fairness lever). (Exception: the candidate
  `ruler_32k` long-context bench uses `max_tokens: 4096`; it is weight-0 and not in the headline.)
- **Force-close, then answer (two-pass budget forcing).** vLLM has no native reasoning-budget, and
  small Qwen3 models were observed thinking *past* the cap without ever emitting `</think>` — the
  reasoning parser then returns empty content **and** empty reasoning, i.e. no answer. local-bench
  enforces the budget with **s1-style two-pass forcing** on the raw `/v1/completions` endpoint
  (`localbench.budget_forcing`):
  - **Pass 1 (think):** generate up to `think_budget` (8192) tokens with `stop=["</think>"]`. If the
    model closes thinking within budget, `finish_reason == "stop"`; if it hits the budget, it is
    **force-closed** (`finish_reason == "length"`, marked `thinking_forced`).
  - **Pass 2 (answer):** re-prompt with the thinking text plus a forced `</think>`, and generate the
    answer with `stop` on the model's end-of-turn token (e.g. `<|im_end|>`).
  - **Fail-closed answer budget.** The answer pass gets `max(max_tokens − think_budget, 1024)`
    tokens — i.e. whatever is left under the 16384 ceiling after the think budget, but **never fewer
    than 1024** so a budget-exhausting think pass can't leave zero room to answer
    (`answer_budget_for`).
  - Any reasoning the model re-opens during the answer pass is detected and **scrubbed** from the
    scored answer text (`_split_reopened_reasoning`); only the post-reasoning answer is scored.

  (On the Anthropic API path used for frontier anchors, the budget is enforced natively rather than
  by two-pass forcing.)

**What counts as a FAILED item, and how failures score.** Failure handling is split between the
**scorer** (does this item score correct?) and the **lane-conformance gate** (is this whole run
even comparable on the headline lane?).

At the item level (`localbench._scoring`):

- **Truncated / no final answer → wrong.** An item is scored correct only if the scorer says
  correct **and** `finish_reason != "length"`. A response cut off at the cap cannot score correct,
  even if a stray correct-looking token appears in the truncated text.
- **No answer extractable → wrong.** If extraction returns nothing (MCQ letter not found, etc.) the
  item is wrong, not skipped.
- **Math fail-closed on truncation.** For the (candidate) math benches, the weak "last number
  anywhere in the text" fallback is **disabled** when `finish_reason == "length"`, so a model that
  hits the cap mid-derivation is not credited because its last scratch number happened to match the
  gold (`extract_math_answer(allow_bare_number_fallback=False)`).
- Errored items (transport/HTTP failures) are recorded as errors and excluded from accuracy rates;
  they are an availability problem, not a wrong answer.

At the run level, the **lane-conformance gate** (`localbench.lane_conformance`) classifies each
bench — and the run takes the **worst** bench's status, so a single corrupted bench cannot be
diluted by the rest:

- **Leaked reasoning into the scored answer** (the endpoint did not separate `reasoning_content`
  from `content`, so `<think>`/`<thinking>`/`<thought>`/etc. markers appear in the scored text):
  **nonconformant at ≥2% of items, diagnostic-only at ≥25%.** This is the most corrupting failure
  because IFBench (half the headline) scores the final answer text, so leaked chain-of-thought
  measures the wrong thing.
- **No distinct final answer** (empty content, or the parser's reasoning-only fallback where the
  "answer" is actually raw chain-of-thought): **nonconformant at ≥10%, diagnostic-only at ≥25%.**
- **Truncation (answers cut at the cap):** in a normal (non-forced) run, **nonconformant at ≥10%.**
  Under budget-forcing (the local capped-thinking path), an answer-pass cap hit is the **model
  failing to terminate** (degenerate looping / genuine non-termination) — it is **scored as a model
  failure (wrong) and surfaced as a visible `answer_cap_hit_rate` diagnostic, but does not exclude
  the run from the headline** (oracle red-team 2026-06-20, "option A"). Leaked-reasoning,
  no-final-answer, and single-pass truncation remain hard gates regardless.

Only a **headline-comparable** run feeds the public Index; nonconformant or diagnostic-only runs
are excluded from the ranked headline. As a defensive invariant, the orchestrator audits for any
cap-hit item that nonetheless scored correct and emits a loud `SCORER-GATE BUG` warning if the
strict completion gate ever fails to apply uniformly.

---

## 3. Run manifest — what is pinned for reproducibility

Every run writes a self-describing record. Two distinct identities are pinned: the **suite**
(which questions) and the **scorecard** (how they were scored). Both must match for two numbers to
be comparable.

**Pinned and recorded:**

- **Decoding: temperature 0 (greedy), deterministic.** Every v1 bench pins `temperature: 0` in
  `suite/v1/suite.json`; the runner forwards the suite's `decoding` block verbatim as the per-item
  sampling params. The manifest records the common `temperature`, and also fields for `top_p`,
  `top_k`, `min_p`, and `seed` — **but the v1 suite does not set top_p / top_k / min_p / seed**, so
  those manifest fields record as `null` (the server's own defaults apply, and at temperature 0 the
  decode is greedy regardless). [UNVERIFIED: whether any sampler beyond `temperature: 0` is pinned
  for the headline — per `suite/v1/suite.json` and `_suite._decoding`, it is not; only temperature
  is pinned, so "greedy via temp 0" is the accurate claim, "top_k pinned" is not.]
- **Suite identity = the sha256-hashed item sets.** Per-bench item-set hashes come from
  `suite/v1/itemsets.lock.json` and are recorded under `suite.item_set_hashes`. The headline item
  sets and their pinned hashes:
  - `mmlu_pro` — **400 items**, sha256 `129b8d9726eab3676ca30d58fac23af4e07407eb537b9bfa10d4d24434b26ba4`
  - `ifbench` — **294 items**, sha256 `40dc0b3e14270d61e9deae13f30f70f04d1d65a304340a7b6fe29cf4a5c51257`

  (METHODOLOGY-v1.2 / REPRODUCE.md describe suite identity as "the sha256-hashed `suite.json`".)
- **Scorecard identity (`localbench.scoring.scorecard`).** A `scorecard_id` (sha256) freezes *how*
  the run was scored, so a later registry edit cannot silently re-score history. It hashes:
  - `scorecard_version` — currently **`scorecard-v1.3`**
  - `registry_digest` — sha256 over **every** field of every axis in `AXES` (weights, roles, bench
    membership, web keys); current value
    `d40e0ccec4d2d144dae386c3a7cc1fef7c638865accbcda4ded93d592528efed`
  - `scorer_versions` — a per-bench scorer+extractor version map (every headline/candidate/exec/
    legacy bench is `"1"` in v1); bumped manually when a scorer's logic changes
  - `ci_method` — **`stratified-nonparametric-bootstrap-percentile`**
  - `reasoning_registry_digest` + `reasoning_registry_entry_id` — the frozen native-thinking
    operating mode (see below); current registry digest
    `5b5f952c2237e3dbc9be7650c3c30defd46961e9d4298861dc1aeb4cf607c91f`

  The full registry payload and reasoning registry are embedded in the manifest so an old run stays
  reproducible under its own recorded scorecard even after the live registry changes.
- **Reasoning-registry / lane metadata.** The capped-thinking operating mode is itself a frozen,
  hashed identity (`localbench.reasoning_registry`): the activation method, the parser's
  reasoning-close tag, the **8192** think budget, the `max(max_tokens − think_budget, 1024)` answer
  budget, the `answer_stop` tokens, and forced-close formatting — per model family (e.g.
  `qwen_thinking_native_v1`, `gemma4_thinking_native_v1`). The run manifest records `suite.lane`,
  `suite.caps.thinking_budget`, the `reasoning_registry_entry_id`, and `reasoning_effort`.

**Recorded best-effort, honestly marked NOT canonical.** When serving a generic OpenAI-compatible
local endpoint, the runtime cannot always self-report weights and build details. The manifest is
explicitly stamped `integrity.canonical = false` with an itemized `missing_fields` list, and these
fields come back as placeholders unless a richer provider fills them:

- `model.file_sha256` = **`"UNHASHED"`**, `model.family` / `quant_label` / `file_name` /
  `file_size_bytes` / `format` = `null`, `tokenizer_digest` = `"unknown"`,
  `chat_template_digest` = `"endpoint-applied-unknown"`
- `runtime.name` / `version` / `ctx_len_configured` / `parallel_slots` / `build_flags` = `null`,
  `runtime.kv_cache_quant` = `"unknown"`
- `endpoint.runtime_reported_model` = whatever the endpoint's `/models` returns (best-effort)
- `hardware` = best-effort `nvidia-smi` GPU name/VRAM/driver, OS string, CPU; `ram_gb` = `null`

In short: the **scorecard, lane, suite hashes, and temperature** are hard-pinned; the **model file
hash, quant label, runtime, KV-cache quant, and context length are NOT auto-captured** for a plain
local endpoint and are surfaced as explicit gaps rather than invented. A run is therefore honestly
self-describing about what it does and does not know. [UNVERIFIED: which serving runtime, quant, KV
type, and context length were used for any *specific published row* — those are operator-supplied/
catalog metadata outside this manifest, not auto-captured by the run itself.]

---

## 4. "No LLM judge"

**Nothing here is graded by a model.** Both headline domains are scored by deterministic,
programmatic code:

- **MMLU-Pro** — exact-match on the extracted multiple-choice letter against a known gold key.
- **IFBench** — each instruction is a machine-checkable rule (counts, formats, keywords, casing,
  …) verified in code; the item passes only if all rules pass.

There is **no model-as-judge, no rubric scored by an LLM, and no preference model** anywhere in the
headline pipeline. This is the point of "judge-free": the score is a function of the model's text
and a fixed answer key / rule set, so it is fully reproducible and cannot drift with a grader
model's mood, version, or prompt. The chance baseline, the bootstrap, and the conformance gate are
all deterministic given the items and the seed.

**The honest caveat: objective ≠ complete.** Programmatic, objective scoring buys reproducibility,
not coverage. It only measures what can be checked exactly:

- It rewards getting the **right letter** and **obeying explicit, checkable constraints**. It does
  **not** judge reasoning quality, helpfulness, factual nuance beyond the key, writing quality,
  calibration, or whether a "correct" answer was reached for the right reasons.
- Exact-match and rule-checkers have their own edge cases (an unusual but valid answer phrasing, a
  constraint a human would read more leniently). We mitigate the worst of these (ambiguity →
  no-answer, fail-closed on truncation) but do not claim the extractor is perfect.
- A high objective score on these two domains is **not** a claim of general capability. The
  product framing is deliberately narrow: *"local quality vs frontier, on the tasks you can
  actually run"* — Knowledge and Instruction-Following, not "intelligence" writ large. See §6.

---

## 5. Rerun / replication policy

**When a row may be re-run.** A published row is re-run **only** for a process/integrity reason,
never to chase a higher number:

- **Infrastructure failure** — the endpoint, network, or harness failed (errored items, a crashed
  server, a transport fault).
- **Corrupted or non-conformant output** — the run tripped the lane-conformance gate
  (leaked reasoning, no-final-answer, single-pass truncation) and is not headline-comparable.
- **Wrong model / config** — the served model, quant, lane, thinking budget, or decoding did not
  match what the row claims, or the run was on the wrong suite version.
- **Failed conformance / integrity gate** — any gate that marks the run nonconformant or
  diagnostic-only.

**What is explicitly NOT a reason to re-run:** disliking the score. There is no "best of N", no
re-roll for a better composite, and no cherry-picking among repeats. Decoding is temperature-0
(greedy/deterministic), so an honest re-run of the same config and suite should reproduce the same
items and substantially the same score; a *materially different* score on a faithful re-run is
itself a signal to investigate (config drift), not an opportunity to keep the luckier number.

**How a third party reproduces a row** (full detail in `docs/REPRODUCE.md`):

1. Install the CLI (`pip install -e cli`) and serve the model on any OpenAI-compatible endpoint
   (llama.cpp `llama-server`, vLLM, Ollama, LM Studio, …), configured for the locked lane:
   reasoning-on, server reasoning-budget **8192**, `max_tokens` ceiling **16384**, **f16 KV** (no
   KV quant), **≥64k** context.
2. Run the frozen suite, **explicitly selecting the headline lane and the full tier**:

   ```
   localbench run --endpoint <url> --model <name> --lane capped-thinking --tier standard --out runs/my-run.json
   ```

   (Note: the CLI defaults to `--lane answer-only` and `--tier quick`; the headline requires
   `--lane capped-thinking --tier standard`, as documented in REPRODUCE.md. `--max-items N` takes a
   deterministic first-N slice per bench so paired runs see identical items.)
3. The harness pulls the sha256-pinned item sets, drives the endpoint, **server-scores every
   response programmatically**, writes the manifest (with the `scorecard_id` and item-set hashes),
   and saves the run JSON. Identical suite version + identical scorecard ⇒ comparable numbers.

Frontier "vs GPT-5.5 / Opus / Gemini" **anchors are cost-gated and run separately**; they are not
part of the local reproduction. Scores are comparable **only within a suite version** (the
sha256-hashed `suite/v1/suite.json`).

---

## 6. What the Index does NOT measure

This is the honest-limits section. The v1 Local Intelligence Index is a deliberately narrow,
reproducible floor — useful for "local quality vs frontier on checkable text tasks", and explicitly
**not** a general intelligence score.

- **Only two domains.** v1 composites **Knowledge (MMLU-Pro)** and **Instruction-Following
  (IFBench)** and nothing else. It is not a broad capability average, and we do not claim it is.
  The Knowledge / Instruction profile is shown beside the composite precisely so a single number
  is never read as "overall intelligence". (An arithmetic mean can hide a single-axis collapse, so
  the **weakest headline axis is reported next to the composite.**)
- **Capable candidate/experimental axes are measured but weight 0 — by design.** Math
  (`olymmath_hard` + `amo`) and Long-Context (`ruler_32k`) are **candidates**; Agentic
  (`bfcl` + `bfcl_multi_turn`) and the static Coding proxy (`lcb`, LiveCodeBench output-prediction)
  are **experimental**. They are run and displayed, but carry composite weight **0.0** and **do not
  affect the Index** until they pass a pre-registered **discrimination gate** (they must separate
  local models with a CI-bound spread; `localbench.probe.gates` / `discrimination.py`). Nothing
  widens the headline without that evidence. The experimental coding/agentic proxies in particular
  are known to be saturated/gameable and will **never** be promoted as-is.
- **No code *generation* in the headline.** The credible coding axis is execution-based
  (BigCodeBench-Hard via `localbench code`, run in a sandboxed Docker container on the user's own
  machine). It is a **separate opt-in exec lane with its own score**, a candidate, and is **never**
  pooled into the Core Text Index. The static `lcb` proxy measures code *reasoning*, not
  *generation*, and is experimental.
- **One lane only: capped-thinking.** The Index reflects reasoning-on with an **8192-token** think
  budget under a **16384** ceiling. It does not characterize answer-only behaviour, unlimited
  "think-as-long-as-you-want" behaviour, or very-verbose R1-class models that might want a larger
  budget (a 4k/8k/12k/16k budget-sweep validation is specced but deferred). Answer-only and
  api-uncapped are secondary views and are **never merged into the headline**.
- **One GPU / one regime.** The whole project targets **local models on a single consumer GPU**
  (the reference rig is an RTX 5090, 32 GB). It is **not** a datacenter, multi-GPU, or
  unbounded-context benchmark. Quantization, KV type, and context window are operating constraints
  of that regime.
- **No multi-turn or agentic behaviour in the composite.** No multi-turn conversation, tool-use,
  or long-horizon agent tasks contribute to the Index in v1 (the agentic proxies are experimental,
  weight 0; an execution-based agentic axis is built but not yet wired into the suite).
- **No long-context in the composite yet.** Long-Context (`ruler_32k`) is a candidate at weight 0;
  its local discrimination is unconfirmed pending a GPU validation run.
- **No human evaluation.** Scoring is fully automated and objective. There is no human-preference
  rating, no Elo-from-votes, and no qualitative review feeding the number.
- **No safety, refusal, or alignment scoring**, and **no multilingual coverage.** The suite is
  English text tasks; it says nothing about refusal behaviour, jailbreak resistance, toxicity, bias,
  or non-English performance.
- **Replication is the trust model, not "verification".** We do **not** claim runs are "verified"
  (a model proxied to a frontier API could defeat transcript verification). Trust comes from a
  third party **re-running** the frozen suite and getting the same number; a "replicated" badge
  requires multiple independent accounts/hardware, which is a separate estimand from a single run's
  bootstrap CI.
- **The CIs answer a narrow question.** The headline bootstrap CI is a **within-suite item-sampling**
  interval — sensitivity to which fixed suite items were drawn, **not** run-to-run decoding variance
  (temp-0 is deterministic) and **not** a universal-capability/generalization claim. Run-to-run
  repeatability needs repeated runs; cross-item generalization is a separate, wider CI; universal
  claims are not made from these item counts.
- **Quantization is reported as a secondary, honest finding — not the headline.** With reasoning on,
  quant costs **VRAM and speed**, shifts the output **distribution** (KLD drift), and does not cost
  task accuracy until a low-bit cliff; "accuracy can mask drift" is the claim, **not** "reasoning
  recovered it" (that causal claim is unproven). KLD is **drift from full precision — lower is more
  faithful, not a task score** — and is never part of the Index.

**In one line:** the v1 Index is a reproducible, judge-free measurement of how close a local model
gets to the frontier on **two** checkable text domains, on **one** consumer-GPU/capped-thinking
regime — and that is all it claims to be.
