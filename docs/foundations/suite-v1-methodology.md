# local-bench suite redesign — from v0 (saturated) to a discriminating ladder

Status: 2026-06-13. Synthesis of 9 research dossiers (per-axis benchmark catalogs + meta-studies
of Artificial Analysis, @scaling01, Epoch/LiveBench/OpenLLM-v2/LMArena aggregators, and a
composite-validity track). Pairs with `docs/scoring-methodology.md` (v2, already GPT-5.5
red-teamed) — this memo selects the *content*; that doc governs the *math*. Web-verified
keystone picks (SuperGPQA, IFBench, BFCL, CRUXEval) on 2026-06-13; residual uncertainties are
flagged inline.

---

## 0. The problem we are solving (one paragraph)

v0 = `MMLU-Pro subset (112) + IFEval (100) + generated-math` averaged 1/3 each. It fails to
discriminate: a 9B lands within ~6 pts of frontier on the composite, Gemini "beats" Opus by
acing the easy axes, and two of three axes are saturated (genmath 98% for the 9B in P0; MMLU-Pro
near-saturated at the frontier). **The diagnosis is not a math problem — it is a bench-quality
problem.** No rescaling fixes an axis where the 9B scores 0.98. The fix is to *replace saturated
content with a difficulty ladder that spans 1B→frontier*, and to keep the already-sound
absolute/paired/bootstrap scoring. This is exactly what Artificial Analysis did at v4.0 (they
dropped MMLU-Pro / AIME-2025 / LiveCodeBench for saturation and swapped in harder evals — not a
reweight) and what Epoch's ECI does structurally (stitch benches of different difficulty so the
hard ones separate the frontier and the easy ones separate the floor).

Two non-negotiable constraints shape every pick, and they are *in tension* with the best
frontier benches:
1. **Local-runnable** on an OpenAI-compatible endpoint, single consumer GPU, **no sandbox / no
   browser / no code-exec on the user's machine / no mandatory LLM-judge.**
2. **Discriminate across the WHOLE range** 1B→frontier — not just the frontier (AA's index
   compresses best-open to within ~6 pts of SOTA; that is *their* job, not ours).

The honest finding: the genuinely hard frontier-discriminating benches are almost all gated,
exec-heavy, or judge-dependent. So local-bench's wedge is a **license-clean, judge-free,
generate-then-extract ladder** that we own and can serve — and we accept that "anchor-only
frontier stretch" content (which floors local users) is reported separately, never on the
core composite.

---

## 1. Recommended suite (by capability axis)

Design rule for every axis: **a difficulty ladder, scored as a stratified profile** (per-rung +
worst-rung), with bootstrap CIs, mirroring the existing private-genmath sentinel with a small
private hold-out per axis as the contamination canary. Item counts are **Quick / Standard** per
rung; all "lanes" are answer-only vs native-reasoning (never merged — `scoring-methodology.md`
§8).

### Axis A — Knowledge & Reasoning (REBUILD: 1 saturated axis → 3-rung ladder)

| Rung | Bench | License | Quick | Standard | Lane | Why |
|---|---|---|---|---|---|---|
| Floor / contamination-surface | **MMLU-Pro** (keep, demote) | MIT | 100 | 250 | both | Keeps the *bottom* of the local range separated (modern 7-9B already ~82%, so it still sorts weak-vs-broken) and is our stable contamination-comparison surface. NOT the whole axis. |
| **Discriminating core** | **SuperGPQA** (hard-weighted, stratified) | ODC-BY | 150 | 400 | both | The single best addition. 26.5k MCQ, native easy/middle/hard split; separates 14B (~38% overall / ~20% hard) → DeepSeek-R1 (62% overall / 57% hard) → frontier (~72%). Generate-then-extract, no judge. Open license where GPQA is gated. |
| Frontier stretch (opt-in) | **BBEH-mini** (460-item) | Apache-2.0 + CC-BY | 120 | 230 | both | Restores the frontier discrimination saturated BBH lost (best general ~10% → reasoning-specialist ~45%). Pure deduction, low knowledge surface, contamination-resistant. **Floors sub-30B** → it informs the TOP of the board, normalized, not the bottom. |

Axis rationale: MMLU-Pro alone collapsed the dynamic range (high floor + compressed ceiling).
SuperGPQA's overall-ability spread (27→62→72%) is what restores resolution across *our* users;
its hard split adds headroom above MMLU-Pro for strong local models. BBEH-mini is the optional
frontier-only rung so anchors stay separated without pulling the small-model floor to zero.

**Excluded from this axis (cited context only):** GPQA (gated + explicit no-republication request
— the v0 exclusion is correct and now fully sourced), HLE (small models floor <5%, needs an
LLM-judge, ~30% answer-noise audit), DROP (saturated + CC-BY-SA share-alike + fragile F1),
ARC-AGI-1/2 (grid-JSON OOD for a chat-QA suite; real scores need program-search harnesses),
MuSR (only 756 items, saturating at top — SuperGPQA dominates it).

### Axis B — Math (REBUILD: harden generated + add fresh-competition ladder)

| Rung | Bench | License | Quick | Standard | Lane | Why |
|---|---|---|---|---|---|---|
| **Generated core (keep + harden)** | **local-bench generated-math v2** (GSM-Symbolic-style hardening) | Ours / Apache-2.0 pattern | 40→**60** | 120→**160** | both | Keep the axis we own; fix "doesn't discriminate" by importing GSM-Symbolic's difficulty levers: more reasoning hops (P2), inserted irrelevant/distractor clauses (NoOp), larger/compositional numeric ranges, symbolic answers + sympy equivalence. Self-hostable, contamination-immune, tunable to the *local* band. Keep public + private sentinel. |
| **Fresh-competition discriminator** | **MathArena** fresh final-answer (newest HMMT-Feb + AIME + BRUMO) | CC-BY-NC-SA 4.0 (mirror) | 45 | 90 | both | The clean path to separate non-reasoning → reasoning-tuned → strong local (base-7B ~0 on AIME → reasoning-7B ~53% → frontier ~90%). Sourced from MathArena's licensed HF mirrors with attribution; **freshness-windowed + rotated** each cycle (copy their eval-on-release methodology). **Confirm NC clause OK for our community/non-commercial distribution — open question for Michael.** |
| Hard headroom (clean license) | **Omni-MATH** numeric subset and/or **OlympiadBench** `OE_TO_maths_en` | Apache-2.0 | 40 | 80 | both | Self-hostable headroom above HMMT for strong local models. Drop proof/multimodal/existence items; score numeric/symbolic with sympy; tier-select mid difficulty so small models aren't fully floored. |
| Anchor-only stretch (do NOT score for locals) | **MathArena Apex** | CC-BY-NC-SA | — | — | api | Genuinely unsaturated final-answer set (Gemini 3 Pro 23.4% SOTA, most <6%) but floors all local models → surface as an "anchor stretch" metric only. |

Axis rationale: every *final-answer competition* set saturated at the frontier in 2025-26
(MathArena published "Farewell to Final-Answer Competition Problems as Frontier Benchmarks";
AIME-2026 averages 0.838). So no single math set spans the range — we build a ladder. Generated
math gives contamination immunity + a tunable local band but **cannot reach frontier hardness on
its own** (it tops out at hard-grade-school / early-competition); fresh-competition + Olympiad
subsets supply the upper rungs.

**Licensing landmines (load-bearing):** never self-host raw Hendrycks-MATH / MATH-500 / raw-AIME
text — AoPS DMCA'd the Hendrycks set off HF (Jan 2025); the repo "MIT" covers *code* only, not
problem content. Use MathArena's explicitly-licensed CC-BY-NC-SA mirrors or generate our own.
Avoid proof grading entirely (needs dual-LLM judges).

**Excluded:** GSM8K / MGSM / MATH-500 (saturated + contaminated; keep GSM8K only as a 1-item
endpoint smoke test), FrontierMath (gated data + proprietary verifiers + floors all locals — cite
as the frontier-ceiling reference that justifies API anchoring).

### Axis C — Instruction-Following (UPGRADE: add IFBench, keep IFEval as baseline)

| Rung | Bench | License | Quick | Standard | Lane | Why |
|---|---|---|---|---|---|---|
| **Discriminating core** | **IFBench** (single-turn) | Apache-2.0 code / ODC-BY data | 100 | 250 | both | Built *because* IFEval saturated; out-of-domain verifiable constraints (programmatic verifiers, no judge), still discriminating (top ~83% in 2026, was ~50% at launch). OOD design = contamination-resistant. Drop-in for our existing programmatic IF lane. |
| Table-stakes floor (keep, labeled) | **IFEval** | Apache-2.0 | 100 | 250 | both | Saturated at frontier BUT has a usable FLOOR (7-8B ~72-74%) so it still separates weak local models. Keep as a *labeled baseline*, never for frontier discrimination. Already integrated; parity test = task #13. |

Axis rationale: IFEval compresses the top; IFBench's OOD constraints re-open frontier headroom
*and* resist the memorization IFEval now suffers. Both are programmatic — no judge, fits the CLI-
local model exactly.

**Excluded / server-side-only:** MultiChallenge + FollowBench (best multi-turn / strict-constraint
discriminators but need an LLM judge → server-side optional modules, never CLI-local), InfoBench
(GPT-4 judge + only partial discrimination), **Multi-IF (CC-BY-NC data — conflicts with serving +
any monetization; rebuild equivalent ourselves if we want multilingual multi-turn IF).**

### Axis D — Agentic / Tool-Use (NEW, but narrow: static function-calling only)

| Rung | Bench | License | Quick | Standard | Lane | Why |
|---|---|---|---|---|---|---|
| **Core (default-local)** | **BFCL non-live AST subset** (single-turn simple/multiple/parallel AST + relevance/irrelevance) | Apache-2.0 | 150 | 400 | both | The ONLY agentic bench that is genuinely default-local-runnable: needs only an endpoint, scoring is deterministic AST compare vs a gold call — **no sandbox, no external API, no code-exec, no judge.** Clean monotonic spread with no small-model floor and no frontier saturation (Qwen3.5-2B 43.6% → 9B 66.1% → Llama-3.1-8B 76.1% → 70B 84.8% → 405B 88.5%). Vendor data + AST scorer; pin a version commit. |
| Opt-in module (NOT default) | **tau2-bench** (telecom) | MIT | — | — | both | Best dynamic/multi-turn agentic discriminator that runs on OpenAI-compatible endpoints with no user-hostile Docker — BUT requires API-side tokens for the LLM user-simulator + judge (cost + run-to-run variance). Offer behind an explicit toggle; report pass^k with seeds. |

Axis rationale: the dominant agentic benches (SWE-bench, Terminal-Bench, GAIA, WebArena, OSWorld,
AppWorld) all need a Docker sandbox / live browser / external paid API, AND Berkeley RDI (Apr 2026)
showed eight of them can be driven to ~100% *without solving any task* because the agent executes
in the same container the evaluator scores in — a cheat surface AND a real risk of running model-
authored shell on a user's box. BFCL's static AST subset sidesteps all of it. Excluding everything
exec-heavy is the honest call; tau2 is the one opt-in worth offering.

**Excluded (anchor context / Docker-only opt-in):** SWE-bench Verified/Lite/Pro, Terminal-Bench 2.0,
GAIA, WebArena/VisualWebArena, AppWorld, OSWorld, BrowseComp, ToolBench, AgentBench. Treat all as
cite-the-published-leaderboard context for anchors, never default self-serve runs.

### Axis E — Coding (NEW, but exec-free only: code reasoning)

| Rung | Bench | License | Quick | Standard | Lane | Why |
|---|---|---|---|---|---|---|
| **Core (default-local)** | **CRUXEval-O** (output prediction) | MIT | 120 | 300 | both | The ONLY exec-free coding option: model writes the predicted OUTPUT as text; gold output ships in the dataset; scoring = exact-match after canonicalizing Python literals → **no execution of model code, no sandbox.** Discriminates without flooring small models (partial credit across 800 items; Code Llama 34B ~44-47%). Frame honestly as *"code reasoning (execution-free proxy)"*, NOT "coding ability". Ship a fixed public subset + a private CRUXEval-style sentinel (our engine). **Adopt -O only**; -I needs execution. |
| Docker-only opt-in (deferred) | **BigCodeBench-Hard** (discriminator) + **LiveCodeBench** (date-windowed, contamination) | Apache-2.0 / MIT | — | — | both | If/when we build a Docker lane: BigCodeBench-Hard separates the full range (frontier ~30-35%, 7B ~5-16%, unsaturated); LiveCodeBench with a pinned post-cutoff window is the contamination workhorse (catches leakage: DeepSeek ~60%→~0% post-cutoff). HumanEval+ only as the simplest reference to containerize first — never a scored headline. |

Axis rationale: almost every coding bench scores by *executing* model-generated code (HumanEval+,
MBPP+, BigCodeBench, LiveCodeBench, SciCode, Aider, SWE-bench). EvalPlus itself "strongly
recommends Docker" and ships a bare-metal risk warning. So generation-style coding is fundamentally
a Docker-only opt-in. CRUXEval-O is the one safe exception that ships in the default suite.

**Excluded as scored axes:** HumanEval+/MBPP+ (saturated ~89-92%), **SciCode (floors small local
models ~0-3% — the exact failure we're avoiding; great frontier discriminator, useless for our
core)**, RepoBench (exec-free but FIM/similarity-scored, chat-mismatched, fragile), SWE-bench /
Aider (agentic, heavy multi-toolchain sandbox). Keep SWE-bench/Aider/LiveCodeBench frontier numbers
as labeled "reported" context only.

### Axes F/G — Long-context + Multilingual (DEFERRED to opt-in modules, not launch core)

These are real and discriminating but each carries a cost that bites our audience. **Recommend
NOT in the launch composite; build as opt-in modules.**

- **Long-context → RULER subset** (Apache-2.0, fully synthetic = contamination-clean + regenerable
  as a private sentinel). Sharp small-model collapse 32k→128k is exactly the spread we want — BUT
  discrimination only appears at 32k-128k+, which many consumer single-GPU setups can't reach with
  usable KV cache (our own P0: 27B-FP8 KV didn't fit a 32GB card). So: **separate opt-in
  context-tier module** (8k/16k/32k/64k tiers the user opts into), report *effective context length*
  (threshold-crossing) not one scalar, drop the saturated NIAH subtasks, keep aggregation/multi-hop/
  QA. Lanes never merge across context tiers. LongBench-v2 (Apache-2.0, no-judge MCQ) is the
  realistic-task complement when ready.
- **Multilingual → INCLUDE + Global-MMLU(-Lite)** (both Apache-2.0, judge-free MCQ). INCLUDE =
  native regional-exam content (best contamination profile; not English-MMLU-translated);
  Global-MMLU adds a culturally-sensitive/agnostic split. Strong small-to-frontier spread on
  low-resource languages. Defer because it widens scope before the core ladder is proven.
- **Excluded:** Multi-IF (NC license), MGSM (saturated + contaminated + confounds math with
  language), NIAH standalone (saturated ~98%, smoke-test only), ZeroSCROLLS (superseded), HELMET's
  judged subtasks (LLM-judge).

### Optional new axis — Calibration / hallucination-discipline (FLAG for Michael)

Orthogonal to knowledge/math; resists saturation differently and separates model families
(Anthropic-style refusal vs confident confabulation). Two routes, both with a judge caveat:
- **SimpleQA-Verified** (1,000 Qs, factuality) — needs an LLM grader for fidelity (server-side or
  relaxed strict-match) → a *future factuality axis*, not a core fix.
- A **ShizoBench-style nonsense-premise** axis (generate our own items + a programmatic pushback-
  detection scorer) — license-clean, contamination-resistant, but answer-extraction is fragile.
Recommend: **defer**, note as the most interesting future axis. AA-Omniscience's +1/−1/0 scoring
(reward correct, penalize confident-wrong, zero for abstain) is the scoring template if we add it.

---

## 2. Composite design (solves 9B-near-SOTA and Gemini>Opus-via-easy-axes)

The scoring methodology v2 is sound and survives the meta-research — **keep absolute
chance-corrected normalization as the published per-setup score** (validated by AA's pass@1 means
and by the "track-my-setup needs temporal stability" requirement; relative Elo/IRT re-ranks
everyone when a new model ships and cannot express "Q4 cost you X points"). The composite changes
below are *additive* to that doc.

**Normalization.** Per-bench chance-correct first: `signed = (raw − c)/(1 − c)` with the bench's
true chance baseline (MMLU-Pro 0.10, SuperGPQA ≈ 1/9.67 ≈ 0.10, BBEH ≈ 0, IFBench/IFEval/genmath 0,
BFCL-AST ≈ 0 — it's structured not MCQ, CRUXEval-O ≈ 0, MathArena 0). **This is the direct fix for
"Gemini wins by acing easy axes"**: chance-correcting a 10-option MCQ (chance 0.10) before
averaging removes the spurious inflation that let an easy high-chance axis dominate. Do NOT clamp
before aggregating (clamping biases floor scores upward — exactly the small-model region we
target); carry signed values through, clamp to [0,1] for display only, render "≈chance" when the
CI crosses 0.

**Weighting.** Weight by capability **DOMAIN, not bench count** (AA's 4×25% pattern; our existing
1/3 split generalizes). Recommended launch weights (5 axes, the deferred ones excluded):

| Domain | Weight | Benches (weight splits within domain) |
|---|---|---|
| Knowledge & Reasoning | 25% | SuperGPQA 15% + MMLU-Pro 6.25% + BBEH-mini 3.75% |
| Math | 20% | generated-v2 10% + MathArena-fresh 7% + Omni/Olympiad 3% |
| Instruction-Following | 20% | IFBench 13% + IFEval 7% |
| Agentic (tool-use) | 20% | BFCL-AST 20% |
| Coding (code-reasoning) | 15% | CRUXEval-O 15% |

Within a domain, a saturated bench gets its weight CUT at the quarterly window, not silently. The
**crucial anti-failure rule** (the v0 root cause): weight should follow *discrimination/
information* — v0 failed partly because the only discriminating axis (MMLU-Pro) was 1/3 of a
composite whose other 2/3 were saturated. Low-information saturated axes are down-weighted, never
left at equal weight.

**Explicit saturation handling (keep ceiling effects out — standing gate, not a one-off).**
1. **Item curation to 20-80% pass rate across the model range** is the primary lever (saturation is
   a content problem). Target items the frontier anchors actually MISS *and* small models can
   partially solve.
2. Compute a **saturation index per axis at a quarterly window** — the operational rule "all
   frontier anchors within ~1 point" (used by AA and the saturation meta-study), or
   `S_index = exp(−R_norm²)`. Any axis whose **local-floor-to-frontier-ceiling spread collapses**
   gets harder items injected or its weight cut. This is the standing gate that would have caught
   v0 genmath (0.98 for the 9B).
3. **Internal 2PL/Rasch layer as the early-warning + curation tool** (NOT the user number — that's
   the §10 1PL-before-2PL roadmap, now externally validated: Epoch ECI ships the exact form
   `σ(α_b·[C_m − D_b])` at 40+ benches). Use per-item discrimination (point-biserial proxy; IRT α
   when dense) to PRUNE low-discrimination saturated items and pick replacements. tinyBenchmarks is
   the citable precedent for IRT-driven item subsetting.
4. **Headroom buffer at the composite DISPLAY layer** (LLM-Stats 1.25 idea: map current
   frontier-anchor SOTA to ~80/100) so the frontier doesn't visually pin the ceiling and a future
   better model has somewhere to go. Display-only; raw chance-corrected values stay internal for the
   quant-delta math.

**The meta-research nuance to bank:** a PRIVATE held-out set gives **no saturation advantage** and
only modest contamination benefit — its value is the *differential* public-vs-private gap, not
secrecy. So the private genmath sentinel is the **contamination/gaming canary, not an anti-saturation
device** (the docs already frame it this way — keep it). The actual contamination workhorse is
**date-windowing / fresh items** (MathArena eval-on-release rotation; LiveBench-style monthly
regeneration), which we now get for free from the MathArena-fresh rung and from regenerating the
generated-math + CRUXEval-style + BFCL-AST private variants each quarter.

**CI method.** Bootstrap, never Wilson (items aren't iid Bernoulli — shared subjects/templates/
graders cluster failures). Cluster the bootstrap at the highest hierarchy level (resample
questions/strata). Three separately-reported estimands stay as-is: repeatability (run-to-run,
fixed items), **paired quant-delta** (paired bootstrap / McNemar on item-level discordance — item
noise cancels, ~1.9 pt MDE vs ~13 pt unpaired), generalization (item-sampling, Standard/pooled
only). Matches Epoch (bootstrap n=500, ±1 SE, 16 reps) and LMArena (1000× percentile). The honesty
rule — *marketing language may never outrun the paired CI* — is load-bearing for the quant-delta
wedge. New axes change nothing here; they just add strata.

**Reasoning-lane policy.** STRICT lanes — composite computed within a lane only, lanes never merge.
Report tokens-to-answer / cost BESIDE accuracy, never folded in. This deliberately diverges from AA
(one index, only difference = temperature 0 vs 0.6): our audience is choosing a *deployable* setup,
where a reasoning model burning 10× tokens at equal accuracy is a different product, not a footnote.
Sampling within a lane follows each lab's recommended settings (greedy/temp-0 non-reasoning; the
model's recommended reasoning temp + max-token budget) to avoid truncation-penalizing reasoning
models — mirrors AA's per-model-recommended-settings practice and our P0 cap-truncation finding.

**Contamination canary.** Per-axis private sentinel at matched difficulty (generated-math already;
add CRUXEval-style + BFCL-AST + a regenerated SuperGPQA-style hold-out where feasible). The
public-vs-private gap is the canary. Plus the MathArena-fresh rung (rotate on release) and quarterly
regeneration of all generated/templated axes as the actual contamination resistance.

---

## 3. Delta from the current v0 build

**KEEP**
- The entire scoring stack: absolute chance-corrected normalization, unclamp-for-inference,
  bootstrap CIs, three-estimand honesty rule, paired quant-delta, difficulty stratification,
  reasoning lanes, governance (index-v{n}/suite-v{n}), 1PL-before-2PL roadmap.
- MMLU-Pro (MIT) and IFEval (Apache-2.0) — **demoted to floor/baseline rungs**, kept with CIs and
  labels, never as standalone axes.
- The generated-math axis + public/private sentinel split (the contamination canary mechanism).
- The web IA shell (home table + model page + run detail + methodology + trust) and the lane-rank /
  no-rank-for-unranked-Quick honesty patterns.

**CHANGE**
- Suite from `suite-v0` → `suite-v1`; index from `index-v1` → `index-v2` (new domains + weights +
  saturation gate + headroom buffer). Re-run the licensing audit at the bump (it's a gate).
- Composite from 3 equal axes → **5 domain-weighted axes** (Knowledge&Reasoning 25 / Math 20 / IF
  20 / Agentic 20 / Coding 15), each a multi-rung ladder. Weight by domain, low-info axes
  down-weighted.
- generated-math: **harden** with GSM-Symbolic levers (hops/distractors/ranges/symbolic+sympy);
  bump Quick 40→60, Standard 120→160; this is the fix for "generated math doesn't discriminate".
- MMLU-Pro: from sole knowledge axis → one of three knowledge rungs (add SuperGPQA + BBEH-mini).
- Web `TABLE_AXES` (`home-leaderboard.tsx` line 10), the model/run pages, and the data pipeline:
  generalize the hard-coded `["mmlu_pro","ifeval","genmath"]` to the 5-domain profile.
- Add a **saturation/discrimination panel** to the methodology page (per-axis anchor spread +
  S_index + point-biserial). This is a credibility moat vs AA/LLM-Stats and directly answers the v0
  critique.
- Add a **headroom-buffered display scale** (SOTA-anchor → ~80) at the composite display layer.

**ADD**
- **SuperGPQA** (ODC-BY) — discriminating knowledge core, hard-weighted, stratified.
- **IFBench** (Apache-2.0 / ODC-BY) — discriminating IF core.
- **BFCL non-live AST subset** (Apache-2.0) — new agentic axis (vendor data + AST scorer, pin
  commit; build a robust tool-call-shape normalizer before AST compare — the main eng risk).
- **CRUXEval-O** (MIT) — new exec-free coding axis + private sentinel.
- **MathArena fresh final-answer** (CC-BY-NC-SA mirror) — fresh-competition math rung, rotated.
- **BBEH-mini** (Apache-2.0 + CC-BY) — optional frontier-stretch reasoning rung (normalized).
- **Omni-MATH / OlympiadBench numeric subsets** (Apache-2.0) — hard math headroom.
- Anchor-only **MathArena Apex** stretch metric (not on the local composite).
- Per-axis **private sentinels** beyond genmath (CRUXEval-style, BFCL-AST, SuperGPQA-style).
- New `LICENSES/` texts: ODC-BY-1.0, CC-BY-4.0, CC-BY-NC-SA-4.0, MIT (CRUXEval) + attribution/NOTICE
  entries.

**REMOVE**
- Nothing is hard-deleted. genmath-easy behavior is *fixed* (hardened), not removed. The 3-equal-axis
  composite is *superseded* by the 5-domain ladder. GSM8K-class easy content survives only as a
  1-item endpoint smoke test (never scored).
- From the scored set permanently barred: GPQA, AIME/MATH-500 raw text, HLE, SciCode, NIAH-standalone,
  MGSM, DROP, Multi-IF, all exec/agentic benches (SWE/Terminal/Web/GAIA/OSWorld) — cited context only.

**Deferred (explicit, opt-in modules — not launch core):** long-context (RULER tiers + LongBench-v2),
multilingual (INCLUDE + Global-MMLU), Docker coding lane (BigCodeBench-Hard + LiveCodeBench),
dynamic agentic (tau2-bench), calibration/hallucination axis.

---

## 4. Presentation spec (lead with the LOCAL/QUANT wedge, not an AA-clone)

- **Home leaderboard.** Keep the sortable table but make the **per-axis profile the headline, the
  composite the sortable summary** (red-team + Epoch both favor decomposition; it is the v0 fix made
  visible). Generalize `TABLE_AXES` to the 5 domains. Hero chart = **quality-vs-VRAM scatter** (x =
  consumer hardware / VRAM / quant, y = composite) with frontier anchors as dashed reference lines —
  the AA quadrant chart re-axised onto *our* wedge. Open-weight-vs-anchor visual split (already
  present). Show tokens-to-answer + est-cost columns (already present). **Headroom-buffered y so the
  frontier doesn't pin the top.** Keep the no-rank-for-unranked-Quick + lane-caveat honesty.
- **Model page.** Per-domain radar/bars with bootstrap CI error bars; "≈chance" rendering when a CI
  crosses chance. A **quant-degradation strip** (the launch hero): paired deltas across that model's
  quants with dominance language (better/worse/tied/**mixed**, each "within uncertainty"), scoped
  "on suite-v1 fixed items". A **"reported" shelf** for frontier benches we don't run (SWE-bench,
  GPQA, HLE, Aider, LiveCodeBench) — clearly labeled *reported*, never charted on a measured axis.
  Reasoning vs non-reasoning shown as an explicit split.
- **Run detail.** Per-axis-per-rung breakdown (e.g. SuperGPQA easy/middle/hard; BFCL simple/multiple/
  parallel/relevance), public-vs-private-sentinel gap (the contamination canary, surfaced), tokens +
  cost + latency, manifest (suite-v1 hash, item-set SHAs, decoding/lane config, anchor-vs-local).
  Conservative ranking for thin-coverage entries (μ−3σ pattern).
- **CIs and lanes everywhere.** Error bars on every score; "≈chance" instead of a precise sub-chance
  point; quant deltas as paired comparisons scoped to fixed items; reasoning/non-reasoning lane
  caveat persistent on every leaderboard view; dated suite-v{n}/index-v{n} tags on each run so a
  re-pruned suite never silently moves historical scores.
- **Methodology page.** Publish the saturation/discrimination diagnostics (per-axis anchor spread,
  S_index, point-biserial/IRT α) + every weight + formula. This transparency is the credibility moat.

---

## 5. Open questions for Michael

1. **Agentic scope.** Ship BFCL-AST as a default axis now (recommended — it's the only safe one), and
   offer tau2-bench as an opt-in token-cost module later? Or hold agentic entirely until the Docker
   stance is decided?
2. **Exec-sandbox stance.** Confirm the no-code-exec-on-user-machines line (CRUXEval-O only for
   coding at launch; all generation/agentic-exec benches Docker-only opt-in). This is the biggest
   product-shape call and it gates the whole coding/agentic axis design.
3. **How many axes at launch?** Recommended 5 (Knowledge&Reasoning, Math, IF, Agentic-static,
   Coding-reasoning); long-context + multilingual deferred to opt-in modules. Confirm the count and
   whether to slip multilingual (INCLUDE/Global-MMLU are cheap MCQ adds) into core.
4. **MathArena NC license.** MathArena's fresh sets are CC-BY-NC-SA 4.0. Our community/non-commercial
   distribution is *probably* fine with attribution + share-alike, but it conflicts with any future
   monetization and with us serving items. Accept the NC constraint for the fresh-math rung, or
   generate-our-own and use MathArena only as an internal cross-reference? (Same question class as why
   we excluded AIME.)
5. **Item-licensing tradeoffs / serving.** OK to serve SuperGPQA (ODC-BY) and BBEH (CC-BY) question
   text via our public API with attribution? (Both look clean, unlike GPQA — but it's a serve-the-
   data decision, not just a read-the-data one.)
6. **Calibration axis.** Build a ShizoBench-style hallucination-discipline axis (our own items +
   programmatic pushback scorer) as a future differentiator, or skip? It's orthogonal and
   saturation-resistant but answer-extraction is fragile.
7. **Refresh cadence + compute.** The hardened suite re-saturates within ~6 months (AA's v4.0 climbed
   50→60-65 in that window). Commit to a quarterly item-refresh + anchor-rerun budget? And the FP16/
   large-model baselines still need rented GPUs (P0 limitation) for the quant-study hero.

---

## 6. Residual uncertainties (flagged, not papered over)

- Several aggregator sites (benchlm.ai, llm-stats, intuitionlabs, codesota) carry **confabulated-
  looking model names** ("Claude Fable 5", "Autopoiesis Aristotle-X1", "DeepSeek-V4-Pro-Max",
  "Qwen3.7 Max"). The *percentages/patterns* recur across sources and are usable; the specific
  top-of-leaderboard *names* are not load-bearing here. Trust Epoch AI / official model cards / our
  own anchor runs over those.
- **SuperGPQA small-model exactness:** README confirms the difficulty stratification and the
  ability spread (Yi-1.5-34B ~27.6% → DeepSeek-R1 61.82%; hard split 56.87%), but the gap *between*
  difficulty tiers at the frontier is modest (~63→57) — discrimination across our range comes mainly
  from overall ability, with the hard split as headroom. Verify exact 7-14B numbers on our own
  anchor+local runs before finalizing item weights.
- **BFCL category counts shift between versions** (v1→v4); pin a specific commit and re-derive the
  ~1,390 non-live AST entry count at adoption. Tool-call-shape normalization (OpenAI tool_calls vs
  inline JSON vs Python) is the real engineering risk — budget parity-testing against the official
  `bfcl-eval` extractor.
- **MathArena freshness window** must be re-pinned each cycle and confirmed strictly *after* each
  anchor's training cutoff; AIME-2024 is provably contaminated, newest cycle only.
- **License strings to re-confirm before SERVING (not just reading):** BBEH (Apache code + CC-BY
  data — confirm the data tag covers redistribution), Omni-MATH/OlympiadBench item provenance (avoid
  AoPS-DMCA-sensitive items), and that the SuperGPQA/BBEH *code* license (separate from the ODC-BY/
  CC-BY data) permits vendoring the scorer.
- The composite *weights* in §2 are a recommended starting point grounded in AA's 4×25% precedent +
  the "weight by discrimination" rule; they should be re-tuned once we have anchor+local
  discrimination data per new axis (the 2PL diagnostic layer informs this).
