# FOUNDATION-WIDENING RESEARCH — 2026-06-19 (pre-red-team synthesis)

*Investigation into Michael's directive "don't launch on weak foundations — address the narrowness + saturation
+ quant-blind-spot risks." Five parallel research tracks (coding, agentic, knowledge-saturation, instruction-
saturation, quant-blind-spot), ~12 web-research agents, cited. This is MY synthesis; it is NOT yet a recommendation
— a dual frontier red-team (GPT-5.5 + Gemini 3.1 Pro) is running against it. Distinguish MEASURED (our harness)
from CLAIMED (papers/single-family). Nothing here is measured on OUR harness yet — that gate is GPU-gated.*

## The headline reframe
**The narrowness is substantially MORE fixable than I argued.** I claimed coding + agentic were structurally
out of reach without relaxing the no-exec/no-judge constraint. That was too pessimistic. The 2025-2026 research
surfaced judge-free, exec-free, license-clean, size-discriminating options for BOTH. We can plausibly go from a
2-axis headline to a 4-5 axis headline WITHOUT executing model code or using an LLM judge — pending our-harness
measurement.

## Per-axis findings (candidate → top caveat)

### Coding — addressable judge-free
- **CodeMMLU** (CC0 — serve freely; ~20k MCQ; judge-free + exec-free, reuses our `mcq.py`; GPT-4o ~65%, NOT
  saturated). The cleanest fit by license + format.
  **TOP CAVEAT (the validity attack): MCQ-about-code measures KNOWLEDGE ABOUT code, not code-GENERATION.** It may
  behave like a second knowledge axis, not a real coding signal. This is the single biggest thing the red-team
  must pressure-test.
- **CRUXEval-O / CRUXEval-X** (open; I/O prediction; scoring = one local `assert`, no sandbox of model code;
  7B ~56% → 32B ~83% → frontier ~82% w/ CoT). Discriminates locally but approaches frontier saturation; same
  class as our current (saturated) LCB output-pred but better-discriminating.
- **Exec path** (BigCodeBench-Hard Apache-2.0: 18%→27%→60%; SWE-bench MIT: 23%→37%→62%→80%) discriminates BEST
  but needs Docker/server-side execution. Defer as an opt-in module; community precedent = bigcode PR-submission
  model (user runs Docker locally, submits JSON).

### Agentic — addressable judge-free (revive what we parked)
- **ToolHop** (Apache-2.0 code / CC-BY-4.0 data; locally-executable Python tools, NO live API, NO simulator;
  7B ~10% → 14B ~26% → 32B ~25% → frontier ~49%). We PARKED this — reconcile: it is **answer-verified** (gold
  final answers embedded), not call-trace-verified; our parking was about deriving call-traces. Worth reviving.
  **CAVEAT: binary cascade scoring floors 7B near noise (~10%)** → weak signal below 14B.
- **ACEBench** Normal+Special only (drop the Agent category = GPT-4o simulator; ~3,800 items; judge-free AST +
  rule-based; 7B 55% → 32B 80% → frontier 85%, ~30pp). License needs confirmation.
- **BFCL-v4 multi-turn** (we have it; Apache-2.0; non-live subset clean size staircase 0.8B 25%→27B 68%→397B 73%).
  **CAVEAT: fine-tuning INVERTS the size order on multi-turn** (specialized 8B fine-tunes beat GPT-4o) → only
  compare like-for-like (base vs base). Single-turn AST is dead (saturated); keep multi-turn only.

### Knowledge — saturation is real, fix exists
- MMLU-Pro IS saturated at frontier (88-92%, ~3.5pp spread) and **16.2% contaminated** (infini-gram, 2025).
- Fix: **harden to Math+Physics hardest-quartile** (still ~40pp local discrimination, MIT, reuses our scorer)
  AND/OR re-add **SuperGPQA** (ODC-BY, not saturated at frontier ~74%, 52pp range) with our provenance filter —
  note we left SuperGPQA earlier for key-quality (~36% flagged); reconcile whether provenance-filtering fixes it.

### Instruction — better than the AA headline implied
- **Two different "IFBench" exist.** The **Allenai IFBench** (canonical) is NOT saturating (o3 69.3%, frontier
  35-52%, 8B 35%, 32B 37%). The **AA-IFBench** variant is the one AA dropped for top-compression. **Confirm which
  we vendored** (likely Allenai → we're healthier than feared).
- Mandatory (already done): reasoning-lane vs answer-only scored separately (27pp lane gap → pooling indefensible).
- Hedges if it ever compresses: **IFEval++** (parameterized, judge-free), **EvolIF** (non-saturable by design),
  or **generate our own** multi-constraint IF (feasible for format/structure constraints — like we generate math).

### Quant blind spot — real but narrower than feared
- Q4 vs Q8 with reasoning on, on 32B+ GGUF: holds (~0) on knowledge/IF and ~MATH-500 (−1pp) and coding (−1 to
  −4pp); **FAILS on AIME-level math (−8pp), long-context (severe, up to −59%), and is UNMEASURED on agentic**
  (IFEval proxy suggests ~−4pp). So "Q4 costs ~0" is a large-model, easy-task statement.
- KLD productionization: **5-slice hashed calibration corpus** (prose/code/math/instruction/tool-use, ~170k tok,
  pinned SHAs) fixes the inflated absolutes; report per-slice. **HARD LIMIT (Duan 2026): KLD/perplexity can be
  stable while internal features collapse** (INT6: PPL improves, 51% of SAE features destroyed) → KLD is a
  necessary-not-sufficient red flag, never a sufficiency guarantee. Honest framing required.
- Cheap confirm (GPU-gated): LCB Easy/Medium (50) + MATH-500 (20) at Q8 vs Q4 → ~1h local, $0 API.

## Candidate widened foundation (to be red-teamed, NOT locked)
Headline (judge-free, exec-free, reproducible): **Knowledge (MMLU-Pro hardened ± SuperGPQA) + Instruction (IFBench
Allenai) + Coding (CodeMMLU, IF it survives the "is it really coding" attack; else CRUXEval) + Agentic (ToolHop
revived ± ACEBench) + Math (mixed-difficulty rebuild)** — a 4-5 axis headline.
Profile/experimental (shown, not scored): exec coding (BigCodeBench-Hard / SWE-bench) as a future opt-in Docker
module; BFCL multi-turn; long-context (RULER) until validated.
Quant: domain-sliced hashed KLD + churn + VRAM + speed, framed as drift-not-score; accuracy-wedge re-tested on a
coding+math slice before any "Q4 is safe" claim.

## Cross-cutting validity risks (for the red-team to attack)
1. **CodeMMLU = coding or knowledge?** If MCQ-about-code doesn't predict code-gen ability, it's a fake coding axis.
2. **assumed ≠ measured.** Every discrimination number here is published / mostly single-family (Qwen), NOT our
   harness. Our recurring lesson. Each axis needs the GPU-gated discrimination probe before it's headline.
3. **Fine-tune inversion** (agentic multi-turn) and **construction bias** (ToolHop built by GPT-4o) distort order.
4. **Adding axes re-introduces the saturation/longevity exposure** we just escaped — more axes = more surfaces to
   saturate; weighting over 5 partly-correlated axes is unsolved.
5. **Does widening dilute the wedge or strengthen the product?** More axes also means more places quant could bite
   (re-opening the quant blind spot we just bounded).

## Open decisions (for Michael, after red-team)
- Relax no-exec for an OPT-IN coding module (best discrimination) — yes/no?
- 4-axis vs 5-axis headline; which coding/agentic candidate survives validation.
- Authorize the GPU-gated discrimination probe (the only way "candidate → headline" gets earned).
