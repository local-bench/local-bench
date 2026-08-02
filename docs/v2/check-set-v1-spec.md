# check-set-v1 — manifest, statistics, and calibration specification

**Status: rev 3.1 — FINAL (oracle gate 1: LOCK-WITH-CHANGES, session `lb-checkset-gate1`, 2026-08-02; every ruling adopted verbatim below; no further gate required). Rev 3.1 is a pre-data factual amendment of the math source only — see §9. This document's sha256 is embedded in the manifest as the pre-registration anchor. Post-lock changes of any kind = check-set edition bump.**

Measured inputs: paired per-item statistics mined from the four same-profile v1 bundles (base Q5_K_M vs Q6_K / UD-Q2_K_XL / Qwopus-fusion; manifests verified identical; recomputed accuracies match recorded aggregates to 1e-9).

## 1. Purpose and claim discipline

`localbench check <file>` measures how a local artifact relates to its family's **pinned local reference** on a fixed item set, plus how it runs (perf microbenchmark). It never produces an absolute cross-family intelligence claim by itself; the landing Local Check Index ranks best-variant-per-family on this same fixed ruler and says so. AA numbers are external family context only. Claim template: "Reference-faithful to <reference edition> on check-set-v1 under <execution edition>. The AA score was not measured for this artifact."

## 2. Modules and item selection (quotas locked; global "60/40" language deleted per gate 1)

| # | Module | Scored | Locked selection |
|---|---|---|---|
| 1 | knowledge | 198 | GPQA Diamond complete (HF `Idavidrein/gpqa`, diamond, revision-pinned, canary stripped+logged; choices shuffled, seed 20260802) |
| 2 | coding | 96 | BCB-hard usable pool 141 (ids `bcbh-006/007/014/035/074/096/104` excluded as sandbox-unscoreable): **all 38 informative + 58 from the complement**, cost-aware |
| 3 | instruction | 120 | IFBench pool 294: **72 informative + 48 complement**, stratified by frozen primary stratum |
| 4 | math | 60 | **30 legacy-informative (olymmath 46-pool + amo 9-pool, cost-aware) + 30 model-blind AIME-band** from the pinned upstream OlymMATH `en-easy` config, revision `2c6532ea2cf929ac1c421532af5951553eaee727` (rev 3.1 correction — see §9). Math is published as a **coarse regression / failure-detection axis**, not a fine-resolution axis. |
| 5 | tools-single | 54 | **all 30 `fresh_common_tools` + all 23 informative bfcl_backbone + 1 preselected complement item** (lowest item-id multi-tool bfcl item not otherwise selected) |
| 6 | tools-stateful | 48 | **12 genuinely distinct state-machine templates × 4 scored instances** + 6 pre-hashed spare instances (below) |
| 7 | sanity gates | 18 | stop-token ×3, budget-control ×3, template-canary ×3, repetition ×3, long-context needle 8k/16k/24k ×3, determinism ×3 |

**Totals: 576 scored + 18 gates + 6 spares = 600 authored.**

Frozen selection mechanics:
- **IFBench primary stratum**: an item's primary stratum = the first `instruction_id` in its `instruction_id_list` under the canonical alphabetical ordering of the 57 type ids; quotas allocated over the 7 family rollups proportionally (format 35 / words 30 / count 23 / ratio 16 / sentence 10 / custom 4 / repeat 2); ties inside a stratum broken by ascending item id.
- **Cost-aware selection** (coding, math-legacy): source = base run `qwen36-27b-q5km-0411`, statistic = per-item `payload.latency_seconds` (completed generations as recorded; the one null-latency errored item `ifbench-214` is excluded from cost statistics); within a quota, prefer items below the pool's median latency; ties by ascending item id.
- **Math AIME-band draw is model-blind**: from the pinned OlymMATH `en-easy` config at revision `2c6532ea…` (the dataset's AIME-level stratum; upstream ships no "medium" config — rev 3.1, §9), deterministic stratification by the upstream `subject` field where present (else by index buckets), uniform quotas per stratum, seed 20260802, ties by ascending upstream index. No difficulty-by-observed-results selection. Calibration may reveal the draw is imperfect; it may not replace items.
- **Stateful templates**: 12 distinct state machines (booking ledger, inventory, ticket triage, bank-lite ops, calendar constraints, config migration, shipment tracking, library loans, seat allocation, subscription lifecycle, warehouse picking, access-control admin). Each seeded instance alters initial state, entity graph, required arguments, and where possible the valid action path. Generator, generated prompts, canonical final states, accepted equivalent trajectories, and **spare replacement order** are pinned in the manifest. A spare replaces an instance only for a predeclared mechanical validity defect, never for model performance.
- **Held-out family (Gemma-4-12B) is one-shot validation.** A held-out failure rejects the edition; it never authorizes retuning.

## 3. Execution configuration (identical both sides, always)

- Canonical llama.cpp execution edition **LCE-1** = b10076 (`305ba51`), CUDA 13.3, `-ctk f16 -ctv f16 --fit off`, batch 1, server ctx 32768, `-lv 4`; binary/library sha256s + effective server config recorded per run. CLI-owned prompt rendering (template sha recorded).
- Sampling: temp 0, seed 1234, thinking ON where the family supports it. **Think budget locked: 4096** (gate 1 ruling: 2048 would destroy paired signal via added floors exactly where the ruler is weakest).
- **Frozen think semantics**: a think token = any generated token between the family's think-open and think-close markers as rendered by the pinned template; the 4096 limit is enforced by the budget-forcing engine (v1 machinery): at exhaustion the closing marker is force-inserted and answer generation begins; answer-budget counting starts at the first post-close token; malformed or absent think markers are scored as-is with a recorded `protocol_flag`; `finish_reason=length` is scored as-is. **Budget exhaustion is an observed model outcome — never grounds for a rerun.** Answer budgets: mcq 512, ifbench 1024, math 1536, coding 2048, tools-single 512, stateful 512/turn; per-item max_tokens = think + answer + 256 headroom.
- **Runtime: pending Stage 4 pilot.** No wall-time estimate is published; only measured p50/p95 will be. (Gate 1 struck the prior estimate as internally inconsistent.)
- Perf microbenchmark (same command): cold+warm TTFT, prefill buckets 512/4k/16k, fixed 256-token decode ×5 (median+IQR), idle/loaded/peak VRAM, full env identity.

## 4. Statistics and verdicts (pre-registered; gate-1 replacement text adopted)

**Definitions (unconditional over all paired items):** drop = reference-correct → candidate-wrong; leapfrog = reference-wrong → candidate-correct; Δ = leapfrog − drop (as pp of paired items); ρd = leapfrog + drop.

**Measured pool-level baselines** (Qwen3.6-27B cohort; descriptive context, not bounds):

| area | Q6_K ρd/drop % | UD-Q2 ρd/drop % | fusion ρd/drop % | base acc % |
|---|---|---|---|---|
| coding (n=141) | 9.93 / 2.13 | 10.64 / 6.38 | 17.02 / 7.80 | 27.7 |
| instruction (n=294) | 9.86 / 6.80 | 14.97 / 8.16 | 18.03 / 13.95 | 67.0 |
| math-hard (n=139) | 18.7 / 9.4 | 19.4 / 13.7 | 25.9 / 10.8 | 25.9 |
| tools (n=330) | 1.52 / 0.61 | 3.94 / 1.82 | 3.64 / 1.21 | 73.0 |

**Fidelity bounds (frozen formulas; computed once on the FINAL item draw during calibration; equality passes; no post-result adjustments):**
- Disagreement bound per area a: **B_ρ,a = max(F_ρ,a, 1.5 · max_{g∈G} ρ̂_a,g)** with F_ρ = 3% generally, 6% for tools.
- **Drop bound (first-class)** per area a: **B_D,a = max(3%, 1.5 · max_{g∈G} D̂_a,g)**.
- **G (predeclared good-quant set):** the dense `Qwen3.6-27B Q6_K` calibration artifact and the MoE `Qwen3.6-35B-A3B Q6_K` calibration artifact (named now; sha256 pinned at download, before any candidate runs). Gemma excluded.

**Verdict precedence (disjoint, in order):**
1. **broken** — validity/execution hard failure (see gate taxonomy, §6).
2. **degraded** — any area's simultaneous **upper** CI below −margin.
3. **reference-faithful** — every area's simultaneous **lower** CI ≥ −margin, AND every disagreement bound and drop bound passes, AND all required gates pass.
4. **drift** — every area non-inferior, but ≥1 disagreement or drop bound fails.
5. **inconclusive** — everything else; when a fidelity bound fails while non-inferiority is unresolved, published as **"inconclusive — drift bound breached"**.

**KLD is NOT in the verdict** (gate 1: contradicted "never a sole downgrade"). Reported separately as `in-band` / `out-of-band` / `unavailable` against per-family calibrated bands.

**Margins locked now: knowledge 3.0 / instruction 4.0 / coding 5.0 / math 6.0 / tools 4.0 pp.** Calibration populates the frozen bound formulas; it may not widen margins. If an area proves vacuous, that is a disclosed limitation or a pre-validation edition redesign — never post-hoc discretion.

**Bootstrap machinery:** centred, studentised, two-sided simultaneous max-statistic intervals; SE = bootstrap standard deviation of the area paired delta; **100,000 deterministic resamples, seed 20260802**; resampling respects frozen selection strata; stateful instances resample by **template cluster**; IFBench by prompt; coding by task. Fallback (predeclared): if any area has zero bootstrap variance or zero discordance in a comparison, all five areas switch to Bonferroni-adjusted paired score (Tango) intervals for that comparison.

**Aggregation (Local Check Index composite; versioned `check-weights-v1`):** capability-domain weights — knowledge .25, coding .25, instruction .20, tools .20 (single .12 / stateful .08 fixed sub-weights), math .10; signed chance correction on mcq areas (v1 convention); worst-axis always reported alongside the composite. **Unsupported areas are never silently renormalized**: if any area is unsupported the composite is not published — per-area results + "composite unavailable (capability excluded: X)" instead.

**Unsupported semantics:** only a capability unsupported by the **reference/family policy** may be excluded. Candidate-only inability, malformed output, or lost tool support is **failure**, not "unsupported".

**Failure/retry policy:** model/protocol failures score wrong; infrastructure failure (server crash, OOM, transport) invalidates or resumes the run without altering prior item records; **no outcome-conditioned reruns, no denominator reduction**.

**Fine-tune/distill/merge outcomes (four states, per area):** **resolved gain** (simultaneous CI wholly above +2pp) · **resolved loss** (wholly below −2pp) · **practical equivalence** (CI wholly inside ±2pp) · **unresolved** (otherwise — an imprecise interval is never presented as evidence of no change). Hard functional status separate; drop/leapfrog counts published.

**Power reporting:** the closed-form 2.8·√(ρd/n) figures are **unadjusted marginal approximations** and are labeled so wherever shown; the published MDEs are **simulation-derived from the final manifest and final inference procedure** (Stage 2 deliverable). (Gate 1 also corrected the record: near zero net delta, Var(Δ̂) ≈ ρd/n — higher symmetric disagreement worsens net-delta precision; it informs churn, not Δ.)

## 5. Calibration matrix (populates frozen formulas; may not widen margins)

| Artifact | Family | Role | Status |
|---|---|---|---|
| Q5_K_M (reference) | Qwen3.6-27B | **independent reference rerun = positive control** (must land reference-faithful with ≈zero disagreement) | GPU |
| Q6_K (in G), UD-Q2_K_XL | Qwen3.6-27B | bound population / aggressive-quant contrast | retro rows DONE (modules 2–5); GPU for 1, 6, 7 |
| Qwopus fusion | Qwen3.6-27B | merge profile | retro DONE + GPU 1, 6, 7 |
| FF-711 `85a5709a…`, ThinkingCap `37d93cb0…` | Qwen3.6-27B | coding / instruction tunes | GPU |
| Qwen3.6-35B-A3B Q6_K (in G) + one aggressive quant | MoE | architecture generalization + bound population | GPU |
| corrupted GGUF (tensor-truncated) + wrong-template run | Qwen3.6-27B | broken-detection true-positives | GPU (fails fast) |
| Gemma-4-12B ladder | held-out | **one-shot validation; failure rejects the edition** | GPU |

**Acceptance criteria (frozen):** positive control lands reference-faithful; both G artifacts land reference-faithful; corrupted artifact and wrong-template run land broken; UD-Q2 lands drift-or-worse in ≥1 area or the bounds are re-derived per formula on the final draw (never hand-tuned); tune runs produce four-state profiles with fusion's instruction loss resolved. Every calibration artifact sha256-pinned in the calibration report. All GPU runs ask-first.

## 6. Gate taxonomy, anti-gaming, durability

- **Validity gates** (any failure ⇒ `broken`): stop-token, budget-control, template-canary, **determinism** — each of the 3 determinism canaries (one short-form, one tool/stateful, one long-context) runs across **independent server restarts** and requires exact equality of generated token-id sequence, finish reason, parsed tool calls, and scorer result; timing and floating-point logits excluded; **tolerance zero**.
- **Behavioral gates** (paired, not broken-making): repetition traps, long-context needles — reference-pass/candidate-fail blocks `reference-faithful`.
- Anti-gaming/durability as rev 2: pre-registered selection; immutable manifest; additive editions; manifest date vs model revision date displayed; server-side recomputation on submission; hash dedup; the check always runs in full.

## 7. KLD sub-pass (pre-registered; outside the verdict)

Direction **KL(reference ‖ candidate)**, teacher-forced token-by-token on the reference model's tokenization of the pinned corpus slice: **exactly the first 262,144 tokens** of the sha-pinned wikitext-2-test slice, context segments of 4096 with no overlap, fresh context per segment; fp32 logit accumulation; reported: mean, p95, p99 per-token KLD + top-token agreement rate; per-family bands calibrated from G; numeric tolerance: results reported to 4 significant figures, band comparisons exact on rounded values. Runs only when reference weights are local; else `unavailable`. Never affects the verdict tier.

## 8. Manifest format

As rev 2, plus: `drop_bounds`, `aggregation` (check-weights-v1 with sub-weights), `unsupported_policy`, `failure_policy`, `gate_taxonomy`, `determinism_canaries`, `stateful` {templates, instances, spares_ordered, cluster_map}, `kld` (full §7 parameters), `pool_exclusions` with reasons, `preregistration` {this doc's sha256 at FINAL, locked_utc}.

## 9. Gate 1 disposition record

**Rev 3.1 amendment (2026-08-03, pre-data, orchestrator ruling):** rev 3 sourced the 30 model-blind math items from "the pinned upstream olymmath medium split". Stage 2 implementation proved (independently reproduced) that no medium config exists at the pinned revision `2c6532ea2cf929ac1c421532af5951553eaee727` — available configs are exactly `en-hard / zh-hard / en-easy / zh-easy / lean`. "Medium" was a drafting misnomer for a nonexistent stratum. Correction: the source is the **`en-easy` config at the same pinned revision** — the dataset's AIME-level stratum, matching rev 3's locked intent (floor-avoidance counterweight to the saturated hard pools). Stratification field corrected to the upstream `subject` field. Nothing else changes: count 30, model-blind construction, seed 20260802, tie-breaks, coarse-axis framing all unchanged. No model has ever been run on these items under this project and no check-set-v1 manifest had been finalized (draft only), so no results could have informed this change and no shipped edition exists to bump; the pre-registration anchor becomes rev 3.1's sha256, with rev 3's sha `0c97d3ab679b99fc07506067d777e5ff14d13c887cbcf7617ceba57b4f196168` recorded here as superseded-pre-data. Disclosed for oracle gate 3 review.

Oracle gate 1 (GPT-5.6 Sol Pro, session `lb-checkset-gate1`, 27m49s): **LOCK-WITH-CHANGES**. All rulings adopted in this rev: module quotas replace the global mix; math locked 60 as a coarse axis with model-blind medium draw; think 4096 with frozen semantics; GPQA kept at 198; runtime estimate deleted; drop bound added first-class with frozen formulas and predeclared G; stateful 12×4+6 (arithmetic corrected to a true 600); determinism across server restarts at zero tolerance; verdict precedence + "inconclusive — drift bound breached"; 100k studentised simultaneous bootstrap with cluster resampling + Tango fallback; four-state tune outcomes; MDEs simulation-derived; KLD out of the verdict; margins locked; unsupported/failure/gate taxonomies frozen; calibration acceptance criteria + positive control added. No further gate required before Stage 2.
