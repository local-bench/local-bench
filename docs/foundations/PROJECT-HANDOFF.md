# local-bench — Project Handoff & Context Brief

*Self-contained context for a new agent or collaborator. Last updated 2026-06-13.*

## 1. What local-bench is
A community **quality**-benchmark leaderboard for **LOCAL / open LLM setups**. A user runs a frozen
benchmark suite against their own rig — **model × quantization × runtime × hardware** — with one CLI
command pointed at any OpenAI-compatible endpoint (Ollama / vLLM / LM Studio / llama.cpp). Results are
server-scored and placed on boards and charts **alongside frontier "anchor" models measured on the
identical suite**. Tagline: *"Geekbench for local AI intelligence."* Repo: `<home>\local-bench`.

## 2. The wedge (why anyone uses it)
The launch differentiator is the **quant-degradation dataset nobody else publishes**: *"what does Q4_K_M
actually cost YOUR model, measured, with confidence intervals."* Verified gap: Artificial Analysis does
quality composites but **API-models only**; LocalScore does community runs but **speed only**; the HF Open
LLM Leaderboard died on central-compute cost. **Nobody does community-run QUALITY benchmarks on your actual
local setup, anchored to frontier.** We measure **distance-to-frontier across the local range** — the
frontier anchors are a *reference ceiling*, not a ranking we try to resolve.

## 3. The five hard constraints (every benchmark we adopt obeys ALL of them)
1. **License-clean** to redistribute/serve (no CC-BY-NC, no gated / no-republish data).
2. **Local-runnable** via an OpenAI-compatible endpoint on a single 16-48GB consumer GPU — **no sandbox /
   browser / code-exec of model output** on the user's machine.
3. **Discriminates across the local range** (1-14B → frontier) — not saturated, not floored.
4. **Contamination-resistant** — synthetic/regenerable, date-windowed, or private-sentinel canaried.
5. **Programmatic scoring — NO LLM judge** (deterministic + reproducible).

## 4. The journey (how we got here)
- **v0 suite** (MMLU-Pro subset + IFEval + generated-math, ⅓ each) **failed to discriminate**: a 9B scored
  within ~6 composite pts of frontier SOTA, and Gemini "beat" Opus by acing the saturated easy axes. Root
  cause: 2 of 3 axes saturated (everyone near ceiling); the composite averaged them, collapsing dynamic range.
- This is a **measurement-VALIDITY** problem, not a code bug. Our tests verify we *compute* the composite
  correctly, never that it *means* anything. P0 validated repeatability + licensing but **never discrimination**.
- **Key external validation:** Artificial Analysis hit the SAME problem and fixed it by **REPLACING**
  saturated benches — their Intelligence Index **v4.0** (Dec 2025) dropped MMLU-Pro / AIME / LiveCodeBench;
  the top score fell **73 → 50**. The industry leader's answer to our exact failure is our precedent.
- Multi-agent research → a **measure-first revised spec** (`suite-v1-REVISED.md`).

## 5. The decisive rule (learned the hard way, twice)
**Weight by MEASURED discrimination, never by leaderboard numbers** (which go stale in *weeks*). Selection
AND weights are set by a **discrimination probe**: run the 4 frontier anchors + ≥3 local models (1-3B / 9B /
~32B) on a sample of each candidate bench, compute floor→frontier spread, and keep/weight only what spreads
(weight → 0 if anchors cluster within ~3 pts). Be willing to ship FEWER, genuinely-discriminating axes.

**Corollary (2026-06-13):** many 2026 aggregator leaderboards carry **confabulated model names/scores** — the
design patterns + licenses surfaced by research are trustworthy, but specific "model X scores Y%" numbers are
NOT; trust Epoch AI / official cards / our own probe runs.

## 6. Current revised suite (candidates — the probe finalizes them)
- **Knowledge & Reasoning:** SuperGPQA (core) + MMLU-Pro (floor) + BBEH-mini (frontier stretch).
- **Instruction-Following:** IFBench (core) + IFEval (floor).
- **Math (license-clean ladder):** AMO-Bench-39 (MIT, newly-authored = clean) + OlymMATH-HARD (MIT) as the
  DISCRIMINATING rung; **generated-math is the private SENTINEL only** (hardening it won't separate the frontier —
  grade-school math is too easy a substrate). HARP/OlympiadBench have an MAA/third-party-copyright catch (packaging
  is MIT, the problems are not). *Needs a sympy/`math_verify` scorer upgrade.* Frontier-vs-frontier math is a real
  ceiling (final-answer format is dead at the frontier) — honest reference ceiling.
- **Long-Context:** RULER 32k (Apache, synthetic) + LongBench v2 (MIT). VRAM-tiered.
- **Agentic:** upgrading from BFCL-AST-only to a multi-rung axis — ToolHop (CC-BY-4.0, discriminates both
  ends) + BFCL multi-turn (already vendored) + BFCL-AST floor.
- **Logical/CSP (candidate add):** ZebraLogic / AutoLogi — clean, generatable, judge-free, strong spread.
- **Coding:** reopened 2026-06-13 — a shippable **exec-free** lane exists (LiveCodeBench output-prediction,
  CC-BY-4.0, date-windowed) + an optional **no-Docker** constrained-exec lane; Docker = opt-in hardening.
  (The earlier "Docker-only / unmeasured" read was too pessimistic.)
- **Calibration:** v2 (build-our-own, scored by AURC over self-consistency — see notes).

## 7. The scoring stack (KEEP — it is sound; this is a CONTENT problem, not a math one)
Absolute chance-corrected normalization; unclamp-for-inference (display-clamp only); **clustered bootstrap
CIs**; three estimands kept distinct (**repeatability** / **paired quant-delta** / **generalization**);
**strict reasoning lanes** (composite within a lane only; tokens/cost shown beside accuracy, never folded in);
difficulty stratification; **private sentinel = contamination canary**; dated `suite-v{n}` / `index-v{n}`
governance. Paired quant-deltas are reported "on suite-v{n} fixed items ± paired CI", never as a universal %.

## 8. "Build our own benchmark" — RECOMMENDED to graduate to a real workstream (2026-06-13 research)
Every existing benchmark saturates in months, carries license friction, and mostly can't separate
frontier-vs-frontier locally. An **OWN benchmark** — procedurally generated + private hold-out — is
contamination-/saturation-/license-proof **by construction** (verification asymmetry: the generator computes the
gold answer, so scoring stays exact-match / poly-time even when *solving* is hard). It's **extension, not
greenfield** — we already ship the engine (`suite/genmath_gen/`, public/private sentinel, judge-free scoring,
169 tests). The feasibility research recommends **graduating this to a real workstream: own 2-3 procedural axes
as the contamination-proof spine, ALONGSIDE the license-clean assembled discriminators that work (a hybrid).**
- **Pilot first (smallest high-signal):** own compositional **instruction-following** (own IFBench) — deterministic
  Python verifiers, frontier-hard in 2026 (IFBench <50% for Claude-4-Sonnet / Qwen3-32B), clean N-constraint
  difficulty dial, extends existing IFEval work. Then own code-output-tracing + own logic-grids/CSP.
- **Durable difficulty levers (these BITE the frontier):** search-space size / NP-hard optimization (most durable),
  execution-step / state-mutation depth, compositional constraint stacking, long-context multi-hop.
- **Defeated levers (TRAPS — do NOT use):** GSM-NoOp distractors (debunked 2026), shallow grade-school perturbation
  (GSM-Symbolic P1/P2 — frontier shrugs it off), fixed-template small-world (bAbI). ARC-AGI grid+test-time-training
  measures the harness, not the model — our no-sandbox rule rightly forbids that shape.
- **Validation is the real cost center (all judge-free):** CTT item analysis (point-biserial / discrimination
  index), input-ablated shortcut detection, convergent validity vs established benches, canary GUID + private
  rotation, human baseline + bootstrap CIs + published generators.
**Thesis: an original local-bench benchmark is the site's most defensible moat.** Tracked as #29 + the deep-research
prompt (`own-benchmark-research-prompt.md`, with a required 3-model red-team).

## 9. Key docs (all in `docs/foundations/`)
- **`methodology-lock/METHODOLOGY-v1.2-LOCKED.md` — CURRENT canonical methodology** (2026-06-19): the single
  consolidated spec (lane, headline axes, composite, KLD/churn, stats, open-item status). Read this first.
  Reproduce a run: [`../REPRODUCE.md`](../REPRODUCE.md).
- `methodology-lock/` also holds: `DECISION.md` (dual red-team + Michael sign-off), `SUITE-LOCK.md`,
  `WEDGE-RESULT.md` (accuracy-wedge NO-GO), `LADDER-RESULT.md`, `KLD-RESEARCH.md` + `KLD-VALIDATION.md`,
  and the deferred-run specs `MATH-REBUILD-SPEC.md` + `RULER-CHECK-SPEC.md`.
- Historical lineage: `suite-v1-DECISION.md` (2026-06-14 adopt-only) ← `suite-v1-REVISED.md` ←
  `suite-v1-methodology.md` (superseded on axis/weights). | `README.md` — folder entry. | `red-team-findings.md`.
- `replacement-research-notes.md` · `website-design.md` · `research-dossiers.json` — research/design backing.

## 10. What's decided vs open
**LOCKED (METHODOLOGY-v1.2, 2026-06-19):** the reasoning-on lane; headline composite = Knowledge + Instruction
(0.5 each); Math + Long-Context = candidates and Agentic + Coding = experimental (all weight 0, shown not
scored); the accuracy-wedge **NO-GO** → product claim "verified local quality vs frontier"; KLD + churn as the
honest quant-drift story. The four consolidation open-items are CLOSED: weight reconcile (one code registry +
drift-gate test) ✓; KLD-in-CLI (`localbench kld`) ✓; math rebuild SPEC'd (validation deferred); RULER
discrimination SPEC'd (run deferred).
**Open (need Michael — all sign-off-gated, $ or GPU):** (1) the deferred validation runs that can PROMOTE Math
+ Long-Context candidate → headline (`MATH-REBUILD-SPEC` / `RULER-CHECK-SPEC`); (2) frontier anchors on the
locked suite (the "vs frontier" spine); (3) exec stance (lean: exec-free coding only at launch); (4) refresh cadence.

## 11. Execution model & guardrails
Claude manages/reviews/synthesizes; research fans out to subagents; **codex GPT-5.5 xhigh** implements heavy
code. Hardware: **RTX 5090** for local runs (mining pauses for benches, restored after); the **vast.ai host
box (machine 105688) is EXCLUDED** from all benchmarking (revenue asset, reliability must not be risked).
API keys live in a machine-local file outside the repo — loaded into process env only, **never echo or commit**.
Work on branches, not `main`, until signed off.
