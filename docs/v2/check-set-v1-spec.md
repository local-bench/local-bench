# check-set-v1 — manifest, statistics, and calibration specification

Status: DRAFT rev 2 for oracle gate 1. Rev 2 folds in measured paired statistics mined from the four same-profile v1 bundles (base Q5_K_M vs Q6_K / UD-Q2_K_XL / Qwopus-fusion; manifests verified identical: suite 02874cff…, profile generic_think_tags_8192_v1; recomputed accuracies match recorded aggregates to 1e-9). Margins remain PROVISIONAL until the calibration matrix locks them. Nothing publishes a verdict before this document's FINAL rev is sha-pinned.

## 1. Purpose and claim discipline

`localbench check <file>` measures how a local artifact (quant / fine-tune / distill / merge) relates to its family's **pinned local reference** on a fixed ~600-item set, plus how it runs (perf microbenchmark). It never produces an absolute cross-family intelligence claim by itself; the landing Local Check Index ranks *best variant per family* on this same fixed ruler and says so. AA baseline numbers are external family context (credited, versioned, as-of dated), never arithmetic inputs. Verdict claim template: "Reference-faithful to <reference edition> on check-set-v1 under <execution edition>. The AA score was not measured for this artifact."

## 2. Modules and item selection

Measured context that drives selection (4-model cohort): **76.7% of legacy items are degenerate** (all-pass or all-fail within the cohort) — but degeneracy is cohort-relative (weaker families would flip ceiling items), so selection uses an **informative/general mix: ~60% drawn from measured-informative items (1–3 of 4 models correct), ~40% stratified from the general pool** to preserve discrimination range across families. Deterministic seed 20260802 throughout; all inputs to selection sha-pinned in the manifest.

| # | Module | Items | Source & selection | Scorer |
|---|---|---|---|---|
| 1 | knowledge | 198 | GPQA Diamond, HF `Idavidrein/gpqa` diamond split, revision-pinned, canary stripped+logged; all 198, choices shuffled (seed) | mcq (exists) |
| 2 | coding | 96 | BCB-hard usable pool = **141** (7 sandbox-unscoreable ids `bcbh-006/007/014/035/074/096/104` excluded from the manifest outright); informative pool = 38 (all in), + 58 stratified from remainder, cost-aware (drop slowest-decile unless informative) | coding_exec sandbox (exists) — **Stage 2 note: read executed verdicts from run items, never `scored_items` (measured gotcha: that file is a pre-execution placeholder, all-false)** |
| 3 | instruction | 120 | IFBench pool 294; stratified proportional over measured constraint families (**format 98 / words 83 / count 64 / ratio 44 / sentence 28 / custom 11 / repeat 9** → ≈ 35/30/23/16/10/4/2), informative-weighted within strata (82 informative items); prompt = the unit; strict scoring primary | ifbench verifiers (exist) |
| 4 | math | 60 | **Resized from 84 (cost) and re-tiered (measured floor): base solves only 36/139 of the hard pools, and median reasoning tokens SATURATED the old 8k budget on both olymmath and amo.** 30 from existing pools (olymmath informative 46 + amo informative 9, cost-aware) + **30 NEW medium-tier items from the same pinned upstream olymmath dataset's medium split** (base-mid-range difficulty target) | math symbolic/numeric (exists) |
| 5 | tools-single | 54 | tc_json pool 330, **93% degenerate (231 ceiling)**; draw = all **30 `fresh_common_tools`** (hand-authored, least contaminated) + 24 from bfcl_backbone weighted toward informative (23) and `call_or_arg_mismatch`-prone / multi-tool strata (tools-per-item 2–4) | tc_json conformance (exists) |
| 6 | tools-stateful | 30 | NEW authored: 6 deterministic scenario templates × 5 seeded instances (booking ledger, inventory, ticket triage, bank-lite ops, calendar constraints, config migration); fixed scripted user turns (no LLM simulator), no network, ≤6 turns; labeled "stateful tool use — not a comprehensive agentic score" | exact tool-call + final-state match (Stage 2) |
| 7 | sanity-gates | 18 | NEW authored: stop-token ×3, pinned-budget truncation ×3, template canary ×3, repetition trap ×3, long-context needle 8k/16k/24k ×3, determinism repeat-pair ×3 (measured motivation: one base item errored null mid-run; 5 IF items hit finish_reason=length at the old total cap) | exact/programmatic |

Total: 576 scored + 18 gates + 6 stateful-instance spares = 600 authored. Modules 1–5 reuse existing scorers unchanged; 6–7 are the only new content.

## 3. Execution configuration (identical both sides, always)

- Serving: canonical llama.cpp execution edition **LCE-1** = b10076 (`305ba51`), CUDA 13.3, `-ctk f16 -ctv f16 --fit off`, batch 1, server ctx 32768, `-lv 4` evidence logging; binary/library sha256s + effective server config recorded per run.
- Prompt rendering CLI-owned (pinned per-family template path, renderer identity + template sha recorded).
- Sampling: temp 0, seed 1234, thinking **ON** where supported. **Static think budget 4096** `[OPEN — oracle Q3: 2048 vs 4096; see cost model]`; answer budgets: mcq 512, ifbench 1024, math 1536, coding 2048, tools-single 512, stateful 512/turn; per-item max_tokens = think + answer + headroom 256 (kills truncation-by-total, measured in v1).
- **Wall-time model (27B on 5090), from measured per-item medians** (old 8k-budget latencies: coding 52.9s, IF 62.6s, olym 125.2s, amo 128.2s, tc 10.0s; saturated modules scale ≈ think/8192): knowledge ≈198×~70s ≈ 3.9h?? → **honest hypothesis: full check ≈ 3–5h at think 4096, ≈ 2–3h at think 2048** (+ KLD ~20–40m + microbench ~10m). The public speed promise is whatever Stage 4 measures (p50/p95), not this table.
- Quants additionally: KLD sub-pass — teacher-forced logits on a sha-pinned wikitext-2-test slice (~300k tokens), llama-perplexity from LCE-1; report mean/p95/p99 KLD + top-token agreement; per-family calibrated bands; never a sole downgrade; "unavailable" when reference weights absent.
- Perf microbenchmark (same command): cold+warm TTFT, prefill buckets 512/4k/16k, fixed 256-token decode ×5 (median+IQR), idle/loaded/peak VRAM, full env identity.

## 4. Statistics and verdicts (pre-registered)

**Four paired measures** per area and overall: net delta (pp), drop rate (reference-correct → candidate-wrong), leapfrog rate, total disagreement ρd.

**Measured baselines (Qwen3.6-27B cohort, % of paired items):**

| area (bench) | Q6_K (good quant) ρd / drop | UD-Q2 (aggressive) ρd / drop | fusion (merge) ρd / drop | base acc |
|---|---|---|---|---|
| coding (bcbh, n=141) | 9.93 / 2.13 | 10.64 / 6.38 | 17.02 / 7.80 | 27.7 |
| instruction (ifbench, n=294) | 9.86 / 6.80 | 14.97 / 8.16 | 18.03 / 13.95 | 67.0 |
| math-hard (olym+amo, n=139) | 18.7 / 9.4 | 19.4 / 13.7 | 25.9 / 10.8 | 25.9 |
| tools (tc, n=330) | 1.52 / 0.61 | 3.94 / 1.82 | 3.64 / 1.21 | 73.0 |

Two measured design facts: (a) adjacent-quant disagreement is ~10–20% on reasoning tasks even when net delta ≈ 0 — churn is mostly symmetric, so fidelity bounds must be sized on ρd, not |Δ|; (b) **drop rate separates quality where net delta misleads** (Q6: +5.67 net with only 2.13 drop on coding; fusion: +1.42 net but 7.80 drop) — drop rate is a first-class fidelity signal, not a tiebreaker.

**Machinery**: paired item bootstrap, 10,000 resamples, seed 20260802; per-area one-sided non-inferiority at α=0.025; simultaneity across the five scored areas via max-statistic bootstrap; Wilson intervals for displayed proportions; IFBench resampled at prompt level, coding at task level.

**Quant verdicts**: **broken** (load/protocol/scorer/validity hard failure, or a fully-failed gate class) · **degraded** (any critical area's simultaneous CI wholly below −margin) · **drift** (all areas non-inferior but a disagreement bound exceeded) · **reference-faithful** (every area non-inferior AND every disagreement bound met AND all gates passed AND KLD-in-band when available) · **inconclusive** (none established — displayed, never hidden) · **unsupported** per-capability (excluded from verdict, loudly labeled).

**Margins (materiality thresholds) and disagreement bounds** `[PROVISIONAL → locked at calibration sign-off]`:

| Area | non-inf. margin | disagreement bound (rule: 1.5× good-quant ρd, floor 3%) |
|---|---|---|
| knowledge | 3.0 pp | 12% `[assumed ≈ IF-like; GPQA ρd measured at calibration]` |
| instruction | 4.0 pp | 15.0% `[= 1.5 × 9.86]` |
| coding | 5.0 pp | 15.0% `[= 1.5 × 9.93]` |
| math | 6.0 pp | `[recomputed after medium-tier build; hard-pool value 28% is saturation-inflated]` |
| tools (single+stateful pooled) | 4.0 pp | 6% `[tc measured 2.3% is ceiling-suppressed; stateful unknown — provisional]` |

**Fine-tune / distill / merge delta profile** (no fidelity vocabulary): per-area **resolved gain** / **resolved loss** (simultaneous CI wholly beyond ±2pp practical margin) / **no resolved change**; hard functional status separate; drop/leapfrog counts published. Measured sanity check: the instrument correctly resolves fusion's instruction loss (−9.86pp, drop 13.95% at n=294) while returning "no resolved change" for its +1.42pp coding delta — which is the honest answer at that n.

**Honest power statement (published)** — 80% MDE ≈ 2.8·√(ρd/n) at measured ρd: knowledge ≈ 6.3pp (n=198, ρd .10 assumed) · coding ≈ 9.0pp (96, .10) · instruction ≈ 8.1pp (120, .10) · math ≈ 15pp (60, .18) · tools ≈ 6.6pp (54, .03 — informative-weighted draw raises effective ρd and improves this) · stateful ≈ direction-only (30). The check resolves hard failures, material regressions, and large per-area tune effects; Q5-vs-Q6-class differences will frequently be *inconclusive* — by design.

## 5. Calibration matrix (locks margins; selection/validation separation enforced)

| Artifact | Family | Role | Status |
|---|---|---|---|
| Q5_K_M (ref), Q6_K, UD-Q2_K_XL | Qwen3.6-27B (dense) | quant discordance ladder | **retro rows DONE (this rev) for modules 2–5**; GPU for 1, 6, 7 |
| Qwopus fusion | 〃 | merge profile | retro DONE + GPU for 1, 6, 7 |
| FF-711 `85a5709a…`, ThinkingCap `37d93cb0…` | 〃 | coding / instruction tunes | GPU (ask-first) |
| Qwen3.6-35B-A3B ladder subset | MoE | architecture generalization | GPU |
| corrupted GGUF (tensor-truncated) + wrong-template run | 〃 | broken-detection true-positive | GPU (fails fast, minutes) |
| Gemma-4-12B ladder | held-out | validation ONLY — excluded from selection & margin fitting | GPU |

Margin-locking: margins = materiality values above unless calibration shows MDE-implied inconclusive rates that make an area vacuous (then flagged to owner, not silently widened); disagreement bounds recomputed from calibration Q6-class runs on the FINAL item draw (the mined values above are pool-level, pre-selection). Any post-lock change = check-set edition bump.

## 6. Anti-gaming and durability

Pre-registered selection (this doc + manifest sha published before any verdict); manifest immutable; additive editions; legacy results keep edition labels; manifest date + model revision date displayed ("public-set exposure possible" when model postdates manifest); server-side recomputation from item records when community reopens; file-hash dedup; the check always runs in full (no KLD-conditioned ordering).

## 7. Manifest format

As rev 1 (JSON: modules[{source{dataset,revision,split}, items[{id,content_sha256}], scorer{name,version}, selection{algorithm,seed,inputs_sha256}}], execution{edition, budgets…}, statistics{margins, bounds, bootstrap, practical_margin}, kld{corpus sha, tokens}, preregistration{spec sha, locked_utc}), plus `pool_exclusions` (e.g. the 7 unscoreable BCB ids) with reasons.

## 8. Open questions for oracle gate 1

1. **Selection mix**: is 60% informative / 40% stratified-general the right anti-overfit balance given degeneracy is measured on a 4-model single-family cohort? Should the held-out family instead gate the mix ratio?
2. **Math module**: confirm the resize (84→60) and medium-tier replacement given measured floor (base 36/139) and budget saturation; is 15pp math MDE acceptable for a module this expensive, or should math shrink further/expand cheaper?
3. **Think budget**: 4096 vs 2048 — 4096 costs ~3–5h/file, 2048 ~2–3h but raises floor rates on hard items (less paired signal). Both sides always identical, so only cost/signal trades, not fairness. Which side of the trade?
4. **GPQA at full 198**: costs ~1.5–3.9h alone by the scaling model — keep full (bridge value + stable science module) or subset to ~120 informative-after-calibration?
5. **Disagreement bounds from 1.5× good-quant ρd**: principled? tc's measured 2.3% is ceiling-suppressed and math's 28% is saturation-inflated — is the per-area floor/recompute treatment sound?
6. **Stateful templates 6×5**: diversity sufficient once public? Instance-seeding design guidance?
7. Determinism gate: batch-1 temp-0 repeat-pair — sufficient, and what tolerance if not bitwise?
8. Anything failing the pre-registration standard set in the pivot review?
