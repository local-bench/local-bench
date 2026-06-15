# suite-v1 — DECISION (adopt-only launch + ring-fenced own-bench track)

**Status: the decision that closes the bench-design phase. Resolves the "open" items in
`PROJECT-HANDOFF.md` §10 and the "candidates" framing of `suite-v1-REVISED.md`. Pending one
Michael sign-off (to release the discrimination probe). 2026-06-14.**

---

## BLUF — the call

**local-bench v1 launches on an adopt-only suite** of robust, well-recognised, license-clean
benchmarks anchored to frontier. **We do NOT gate launch on building our own benchmark.**
Building our own stays a *run-when-idle R&D side-track* (StateTrace + ConstraintForge),
explicitly off the launch critical path. The only remaining benchmark step before we can lock
the suite is the **discrimination probe** (~$5-15 + a few hours of 5090 time), which runs the
moment this doc is signed off.

**Why adopt is the right call (not a compromise):**
- For a *comparator* leaderboard, **recognition = trust = the product.** Recognised benches are
  pre-validated; an invented one carries a "prove it's valid" tax (human baseline, convergent
  validity, discrimination study) before anyone believes a number.
- The contamination trap that normally makes "just adopt MMLU" a mistake is **already solved**
  by adopting the **generator / date-windowed subset** (RULER, ZebraLogic, AutoLogi, LiveCodeBench,
  IFBench) — robust *and* contamination-resistant without building anything.
- **Precedent:** Artificial Analysis hit our exact saturation failure and fixed it by *replacing*
  saturated benches (Intelligence Index v4.0, Dec 2025; top score fell 73→50), not by inventing
  their own.
- The 3-model red-team proved own-bench is **a separate project with a gated payoff**: of 5
  designs, 3 died, 2 reached *pilot-only* — and even those need a 3-4 day discrimination smoke
  test before a 2-4 engineer-week build, with no guarantee.

---

## 1. The locked candidate set (the probe finalises inclusion + weight)

**"Locked" means we stop hunting for benches** — the candidate set is frozen. The measure-first
rule (§3) decides final inclusion and weights from *our own runs*, not from published numbers.

| # | Axis | Picks (core / floor / stretch) | License | Contamination posture | Notes |
|---|---|---|---|---|---|
| 1 | **Knowledge & Reasoning** | SuperGPQA (core) · MMLU-Pro (floor) · BBEH-mini (stretch) | ODC-BY / MIT / Apache+CC-BY | static (provenance-filter SuperGPQA) | carries local **and** frontier signal |
| 2 | **Instruction-Following** | IFBench (core) · IFEval (floor) | Apache+ODC-BY / Apache | IFBench = fresh programmatic verifiers | built *because* IFEval saturated |
| 3 | **Math (license-clean ladder)** | AMO-Bench-39 · OlymMATH-HARD-100 (discriminating) · generated-math v2 = **private sentinel** | MIT / MIT / ours | AMO newly-authored; gen-math procedural | **not** HARP/OlympiadBench (MAA copyright). Prereq: sympy scorer. Frontier = honest reference ceiling |
| 4 | **Long-Context** | RULER @32k (core) · LongBench-v2 (core) · RULER @64k (VRAM-gated stretch) | Apache / MIT | RULER = synthetic generator (best posture) | drop ≤16k (saturated no-op) |
| 5 | **Logic / CSP** | ZebraLogic (core) · AutoLogi rung (if earned) | ⚠️ verify repo / CC-BY-SA ⚠️ | generator + Z3 uniqueness (best posture) | the standout missing axis; the slot ChromaLadder was killed for |
| 6 | **Agentic** | ToolHop (core) · BFCL multi-turn · BFCL-AST (floor) | CC-BY-4.0 / Apache / Apache | static schemas (synth-finetune risk) | vendored audited stubs / in-process sim — **no live API, no judge** |
| 7 | **Coding (exec-free)** | LiveCodeBench Test-Output-Prediction | CC-BY-4.0 data + MIT harness | date-windowed / rotatable | exec-free spine **only** at launch; real code-gen → Docker opt-in later. ToS-awareness flag on problem statements |

**Deferred / opt-in (clearly labelled, NOT launch core):** coding constrained-exec + Docker
hardening · calibration v2 (own AURC pushback detector) · multilingual (INCLUDE / Global-MMLU) ·
tau2-bench dynamic agentic.

**Honest caveats carried forward (state these on the methodology page):**
- Frontier-vs-frontier separation is **largely out of reach** for a license-clean / judge-free /
  local suite (especially math) — the anchors are a **reference ceiling**, not a ranking we resolve.
- Coding at launch is **output-prediction only** — genuine code-gen needs execution (Docker opt-in).
- Expect the probe to cut this to **~4-5 surviving axes**. Ship fewer genuinely-discriminating
  axes rather than pad the composite (that padding is what killed v0).
- **License audit before serving:** ZebraLogic repo license, AutoLogi repo LICENSE (CC-BY-SA from
  arXiv listing only), SuperGPQA item provenance, each scorer-code license before vendoring.

---

## 2. The own-bench track (ring-fenced — off the launch critical path)

- **Parked, pilot-ready:** **StateTrace** (code execution-trace / output-prediction; pilot 1st,
  cleanest gold) · **ConstraintForge** (compositional OOD instruction-following; pilot 2nd,
  best-evidenced).
- **Killed by red-team → replaced by an adopt:** ChromaLadder → **ZebraLogic** · AbstainBench →
  **calibration-v2** probe · Interlock → **BFCL multi-turn + ToolHop**.
- **Promotion gate (hard):** each pilot must pass a **3-4 day discrimination smoke test** —
  monotone success-decline as difficulty rises; frontier clearly below ceiling on the hard rung;
  the local panel spreads with no step-cliff; anti-shortcut baselines fail the hard rung; positive
  point-biserial item-discrimination — **before** any launch-quality build, and only enters the
  suite if it out-discriminates or cleanly complements the adopted axis it would replace.
- **Cadence:** run a pilot when there's spare 5090 time. **Never blocks launch.** Pure upside —
  every own-bench failure mode is one we can fix by turning a knob; adopted-bench failures are
  external and permanent.

---

## 3. The discrimination probe (THE gate — runs after sign-off)

**The lesson it enforces:** v0 failed because 2 of 3 axes saturated and the composite averaged them
(a 9B scored ≈ SOTA). Adopting recognised benches *without* measuring discrimination just repeats v0
with better names. The probe has **two legs**: **A — between-model** (does each axis spread the local
range?) sets axis selection + weights; **B — within-model quant** (can the suite *resolve* a quant
delta?) validates the product wedge. Skipping Leg B ships the quant-degradation differentiator on an
assumption — the same assumed-≠-measured mistake as v0, one level down.

### Leg A — between-model discrimination (selection + weights)
1. **Run** the 4 frontier anchors (Gemini 3.1 Pro, GPT-5.5, Opus 4.8, Sonnet 4.6) + ≥3 local models
   spanning the range (a 1-3B, a ~9B, a ~32B) on **Quick-tier samples** of each candidate bench.
2. **Compute** per-bench floor→frontier spread + point-biserial discrimination index.
3. **Keep / weight rule:** weight ∝ measured spread. **Drop** any bench where the anchors cluster
   within ~3 pts (frontier-flat) OR all locals floor near chance (no mid-range signal).

### Leg B — within-model quant sensitivity (validates the wedge)
*Rewritten after a 3-frontier-model red-team (GPT-5.5 REVISE / Gemini 3.1 Pro FATAL / Qwen 3.7 Max
REVISE — `quant-methodology-redteam.md`). The paired architecture is sound; the original single-model,
N=3-floor, Quick-tier validation would have shipped underpowered false-negatives as "quant is free."
Non-negotiable corrections:*
1. **Matrix, not one model.** Quant ladder (FP16 / Q8_0 / Q4_K_M / Q3_K_M, same weights) across **≥3
   sizes** (~1.5B / ~8B / ~32B) and **≥2 runtimes** (vLLM + llama.cpp), same frozen items, pinned
   sampling. One model validates nothing — Q4 is ~catastrophic at 1.5B and ~free at 32B; the detectable
   delta is a property of (N, discordant-rate, axis, scorer, competence), not a suite constant.
2. **Power first — Standard-tier+ only for quant.** Resolution is set by discordant-pair count: a
   typical 1-3pt quant gap needs **~400 to >1000 items/axis** (McNemar, 80% power). **Quick-tier
   (~100-200) cannot resolve quant** → exploratory-only here. Pre-register a **minimum detectable effect
   per tier** + a **practical-equivalence margin**; never report "quant is free" unless the CI lies
   *inside* that negligible band (else it is absence-of-evidence, not evidence-of-absence).
3. **Per-config noise floor, N≥10** (NOT 3, NOT FP16-only). Q4 has its own, usually higher, run-to-run
   variance (different kernels / KV-cache quant / atomicAdd non-associativity); cross-applying FP16's
   floor is invalid. ≥10 repeats per config, floor stratified by runtime.
4. **Same-runtime ladders for any causal "Q4 costs" claim.** A FP16-vLLM vs Q4-llama.cpp delta is
   dominated by kernel/KV-cache/tokenizer, not weights. Vary **only quant within a fixed runtime** for
   attribution; cross-runtime/cross-rig deltas are labelled **tuple-level, not quant-causal.**
5. **Split format failures from capability failures.** k-quants preserve salient weights, so damage is
   often **diffuse or shows as JSON/stop-token/format breakage on EASY items**, not "hard items first."
   Instrument parse/format failure as its own channel so scorer brittleness isn't scored as reasoning
   loss; the degradation *profile* is a result to MEASURE, never an assumption.
6. **Scoring-stack fixes are prerequisites (see §4):** drop chance-correction on the discrete
   {−1,0,+1} delta; cluster-robust bootstrap by shared-context/prompt-family; FDR-correct the
   per-(axis×stratum×quant) `severe_subgroup_regression` flags against a pre-registered harm threshold.
7. **Gate (raised):** PASS = the **composite** quant-delta CI excludes zero **AND ≥50% of axes** resolve
   the delta outside their per-config floor at Standard-tier, **AND** a known-large degradation (Q3) is
   detected on multiple axes (positive control). "≥1 axis" was far too weak — a wedge that only sees
   quant on hard-math is useless to most users.

### Both legs
- **Lock weights + the published quant-delta item-counts from the measured numbers; publish the
  saturation + minimum-detectable-delta diagnostics on the methodology page** — that transparency is
  the credibility moat.
- **Cost:** ~$5-15 anchor spend (Leg A) + a few hours of 5090 time for both legs. Leg B adds only
  local quant runs (anchors aren't quantised → no extra API spend). Pauses mining, restore after.
- **Can run in waves** as each axis's scorer lands (§4) — probe the ready axes first.

---

## 4. Implementation prereqs (these gate the probe, per-axis)

An axis can only be probed once its scorer works. Rough priority:
- **sympy / `math_verify` scorer** (replaces regex+Fraction in `math_numeric.py`) — gates the whole math ladder.
- **RULER generator integration** + a runner assertion the endpoint actually served the full
  requested context (no silent truncation); KV-quant guidance per VRAM tier.
- **BFCL AST scorer + tool-call-shape normaliser** (parity-test vs `bfcl-eval`); **ToolHop** stub
  vendoring (audited, non-networked).
- **IFBench verifier vendoring + parity test** (extends the IFEval verifier work).
- **SuperGPQA item-provenance filter** before serving.
- **LiveCodeBench date-window harness** (output-prediction scenario, exact-match).
- *(Site is already axis-agnostic as of the 2026-06-14 `site-overhaul` — new axes flow through
  schema→build_data→leaderboard→run pages with no code edits.)*

**Quant-measurement fixes (red-team-surfaced — these gate the WEDGE, not a single axis):**
- **Drop chance-correction on the per-item paired delta** (`paired_delta.py:_delta_item`): chance
  correction belongs to each config's aggregate success proportion, not a single-trial {−1,0,+1}
  discordance — applying it to the delta distorts variance and makes MCQ vs generative non-comparable.
- **Cluster-robust bootstrap** (`paired_delta.py` / `bootstrap.py` / `subgroups.py`): resample by
  shared-context / prompt-family cluster, not only difficulty stratum — correlated items (long-context,
  multi-turn, RAG) otherwise shrink the CI ~√(cluster size) and manufacture false "real" deltas. (The
  handoff's "clustered bootstrap" claim is currently stratified-by-difficulty only — a real claim↔code gap.)
- **FDR/Holm correction + per-config N≥10 floor + exact-McNemar/Wilson interval** for
  `severe_subgroup_regression` (`subgroups.py`): ~15-60 cells with no correction → 50-95% family-wise
  false-positive rate; the −10pt threshold must tie to a pre-registered harm margin, not be a bare constant.
- **Optional higher-power instrument to evaluate:** a paired **log-prob / perplexity delta** on fixed
  items is ~10× more N-efficient than discrete McNemar for quant sensitivity — but needs endpoint
  logprobs (not always exposed) and measures distributional shift, not task success. Pilot as a
  complement, not a replacement for the accuracy delta.

---

## 5. Decided vs needs Michael

**Decided here:** adopt-only for v1 · candidate set frozen · own-bench ring-fenced as run-when-idle
R&D · measure-first weighting. Carried forward (already sound): the wedge (quant-degradation
dataset), the 5 hard constraints, the distance-to-frontier framing, the entire scoring stack.

**Needs Michael's sign-off to unblock:**
1. **Approve this adopt-only decision** (closes bench-design).
2. **Authorise the probe spend** (~$5-15 + 5090 time; mining pauses, restored after).
3. **Confirm the exec stance** (lean: exec-free coding only at launch; Docker as a later opt-in module).
4. **Confirm refresh cadence** (lean: quarterly generator regen + anchor re-run).

---

## 6. Provenance

Built from `suite-v1-REVISED.md` (measure-first spec), `replacement-research-notes.md` (5-axis
gap-fill: coding / agentic / math-headroom / calibration / logic-CSP), and
`own-benchmark-deep-research.md` (5 own-designs + a 3-frontier-model red-team). This doc supersedes
the "open / candidates" status of those documents **for the launch decision**; they remain the
detailed backing. All published bench numbers in the backing docs justify *what to probe*, never
final weights — the §3 measure-first rule governs.
