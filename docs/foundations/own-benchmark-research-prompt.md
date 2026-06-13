# Deep-research prompt — "best benchmarks → craft our own" (draft for Michael)

Paste the block below to a fresh research agent (general-purpose, web-enabled). It reads the project
handoff first, does a deep mechanics survey, then designs original benchmarks local-bench could own.

---

```
ROLE: You are a benchmark methodologist doing deep research for "local-bench". BEFORE anything else,
read the full project context at C:\Users\Michael\local-bench\docs\foundations\PROJECT-HANDOFF.md and
skim docs/foundations/suite-v1-REVISED.md + replacement-research-notes.md so you don't re-tread what's
already decided. This is EXPLORATORY — deliver evidence and designs for Michael to decide; do not assume
we are committing to build our own benchmark.

GOAL (two phases):
  PHASE 1 — understand HOW the best current LLM benchmarks actually work (their mechanics, not their scores).
  PHASE 2 — use those design patterns to propose ORIGINAL benchmarks local-bench could author and own.

THE FIVE HARD CONSTRAINTS (anything we'd build or adopt must satisfy ALL):
  1. License-clean to redistribute/serve (no CC-BY-NC, no gated/no-republish).
  2. Local-runnable via an OpenAI-compatible endpoint on a single 16-48GB consumer GPU — no sandbox/browser/
     code-exec of MODEL output on the user's machine.
  3. Discriminates across the local range (1-14B → frontier) — not saturated, not floored.
  4. Contamination-resistant — procedurally generated/regenerable, date-windowed, or private-hold-out.
  5. Programmatic scoring — NO LLM judge (deterministic + reproducible).

HEAD-START — what we ALREADY KNOW (build on this; do NOT re-derive). From local-bench's own feasibility research:
  - WHY own-benchmarks work: VERIFICATION ASYMMETRY — the generator computes the gold answer, so scoring stays
    exact-match / poly-time even when SOLVING is hard. Design every axis around this. We already own a procedural
    engine (suite/genmath_gen/) — design new axes as EXTENSIONS of that shape (generator + deterministic verifier +
    public/private sentinel), not greenfield.
  - DURABLE difficulty levers (proven to bite the 2026 frontier): (1) search-space size / NP-hard optimization
    (most durable — combinatorial hardness doesn't evaporate with scale); (2) execution-step / state-mutation depth
    (code tracing); (3) compositional constraint stacking (instruction-following); (4) long-context multi-hop.
  - DEFEATED levers — TRAPS, do NOT base difficulty on these: GSM-NoOp / irrelevant-distractor clauses (debunked —
    frontier drop ≈ 0 once distractors are truly irrelevant); shallow added-hop perturbation of grade-school math
    (GSM-Symbolic P1/P2 — frontier shrugs it off; templated grade-school is too easy a substrate to be frontier-hard);
    fixed-template small-world (bAbI saturates); ARC-AGI grid + test-time-training (measures the harness, not the
    model — forbidden by our no-sandbox rule).
  - VALIDATION toolkit (all judge-free; the real cost center): CTT item analysis (difficulty p 0.3-0.8, discrimination
    index D≥0.3, point-biserial >0.2-0.3, discard ≤0); input-ablated baseline (catch shortcuts/leaks); AFLite-lite
    prune; convergent validity (correlate vs MMLU-Pro/IFEval/SuperGPQA); canary GUID + private rotation; human
    baseline + bootstrap CIs; publish every generator + verifier.
  - LEADING PILOT candidate (validate ONE axis fully before more): own compositional INSTRUCTION-FOLLOWING (own
    IFBench) — deterministic Python verifiers, frontier-hard in 2026, clean N-constraint difficulty dial. Then own
    code-output-tracing + own logic-grids/CSP.
  - The verdict so far is HYBRID: keep the assembled discriminators that work (SuperGPQA, IFBench, RULER) AND own
    2-3 procedural axes as the contamination/saturation/license-proof spine.
  - SOURCE CAVEAT: 2026 aggregator leaderboards carry CONFABULATED model names/scores — use the PATTERNS and licenses,
    but treat specific "model X scores Y%" numbers as unverified (confirm via your red-team models / Epoch / official cards).

PHASE 1 — BENCHMARK MECHANICS DEEP-DIVE.
Across these domains — knowledge/reasoning, math, coding, agentic/tool-use, instruction-following,
long-context, logical/deductive (constraint-satisfaction), and calibration/hallucination — identify the most
respected AND most DISCRIMINATING current (2024-2026) benchmarks. For EACH important benchmark, document:
  - WHAT capability it actually tests (the underlying cognitive skill).
  - The EXACT item format — include 1-2 real or faithfully-representative example items (actual prompt + gold answer).
  - HOW it is scored — the precise rule (exact-match / AST / sympy / unit-test / recall) vs LLM-judge.
  - HOW difficulty is controlled; whether it has a difficulty ladder.
  - CONTAMINATION posture — static vs procedurally generated vs date-windowed; how it resists memorization.
  - CURRENT discrimination — who floors, who saturates, the spread small→frontier (sources + dates).
  - License (data + code).
Then SYNTHESIZE the cross-cutting DESIGN PATTERNS that separate a discriminating, contamination-resistant
benchmark from a saturated/gameable one. Pay special attention to PROCEDURALLY-GENERATED benchmarks — RULER,
GSM-Symbolic, ZebraLogic, AutoLogi, NPHardEval, ARC-AGI / ARC-AGI-2, bAbI, SATBench, DyCodeEval, synthetic
long-context — and REVERSE-ENGINEER how they generate items that stay hard for frontier models yet remain
deterministically gradable, and exactly which difficulty levers they expose (and which levers are now
discredited, e.g. GSM-Symbolic "NoOp" distractors).

PHASE 2 — DESIGN OUR OWN BENCHMARK(S).
Using those patterns, propose 2-4 ORIGINAL benchmark designs local-bench could build and own. EACH must satisfy
all five constraints, ESPECIALLY contamination-proof-by-construction (procedural generation + private hold-out)
and judge-free scoring. For each design specify:
  - The capability it targets and why it's valuable / orthogonal to existing axes (SuperGPQA, IFBench, math
    ladder, long-context, agentic).
  - The GENERATION METHOD — how items are procedurally created, with 2-3 concrete EXAMPLE generated items
    (prompt + gold answer) at easy / medium / hard.
  - The SCORING — the exact deterministic rule.
  - The DIFFICULTY LEVERS — how to keep it hard for FRONTIER reasoning models WITHOUT flooring small locals
    (the central hard problem; ground each lever in a Phase-1 precedent that proved it works).
  - VALIDATION — how to prove it discriminates (anchor + local spread, item-discrimination/IRT, no degenerate
    shortcuts) and how to defend credibility ("is it a real benchmark?": published methodology, private
    rotation, correlation with established benches).
  - EFFORT / RISK estimate vs adopting an existing bench.
RECOMMEND the 1-2 to pilot first (smallest high-signal pilot) and give an HONEST verdict: should an
own-benchmark be a CORE part of the site (the moat), a supplementary axis, or not worth it?

GROUNDING: cite sources (URLs + dates) for every factual claim; benchmarks saturate fast — prefer 2025-2026
data; give REAL example items, not vague descriptions; flag anything unverifiable. The project's decisive
lesson: leaderboard numbers go stale in weeks, so use them to decide WHAT to probe, never as final truth.

PHASE 3 — RIGOROUS MULTI-MODEL RED-TEAM (REQUIRED — do not skip).
Submit the Phase-2 candidate designs (with their difficulty-lever claims + example items) for INDEPENDENT
adversarial critique to THREE frontier models. Run all three; no single model's view dominates. Each reviewer is
told to ATTACK the designs as hard as possible, not to be agreeable.
  - GPT-5.5 @ xhigh reasoning — via the codex CLI, read-only, stdin-attach the designs:
        codex exec --sandbox read-only --effort xhigh - < <designs.md>
        (use -m gpt-5.5 if the local codex default isn't 5.5; see ~/.claude memory reference_codex_cli_invocation.md)
  - Gemini 3.1 Pro — via the Gemini API, model `gemini-3.1-pro-preview` (key in
        C:\Users\Michael\Desktop\API keys.txt; see ~/.claude memory gemini_api_access.md or the gemini CLI).
  - Qwen 3.7 Max — via its API (DashScope or OpenRouter). CONFIRM the endpoint/key is configured first; if it is
        not available, say so explicitly and substitute the strongest reachable Qwen (note the substitution) —
        do NOT silently drop the third reviewer.
Each reviewer must attack, with concrete grounded reasons: (a) will it ACTUALLY discriminate small→frontier, or
floor/saturate like the v0 suite? (b) is it GAMEABLE — degenerate shortcuts, a weak model passing without the target
skill, prompt/format/length hacking? (c) CONTAMINATION holes — can items or answers leak or be memorized despite the
generation + private hold-out? (d) SCORING — does the deterministic scorer mis-grade correct answers or accept wrong
ones; answer-extraction fragility? (e) LICENSE / provenance traps; (f) CREDIBILITY — would the eval community accept
it as a real benchmark? Require each reviewer to give a verdict per design: SHIP / REVISE / KILL, with the single
biggest risk named.
Then SYNTHESIZE the three critiques: surface CONSENSUS failures (≥2 models agree = high priority), reconcile
disagreements with your own judgment, and REVISE or KILL each design accordingly. Note any design that survived all
three red-teams (that is the strongest signal).

OUTPUT: a structured markdown report — Phase 1 per-domain catalog → design-patterns synthesis → Phase 2 candidate
designs → Phase 3 per-model red-team verdicts (GPT-5.5 / Gemini 3.1 Pro / Qwen 3.7 Max) + synthesis → REVISED designs
→ final recommendation (which 1-2 to pilot, smallest high-signal pilot, and a core-vs-supplementary verdict). Save it
to C:\Users\Michael\local-bench\docs\foundations\own-benchmark-deep-research.md and return a 12-line summary.
```

---

## Notes for Michael (not part of the prompt)
- **Scope/cost:** this is a big two-phase brief — it will run long and spend real subagent budget. If you want it
  faster/cheaper, split Phase 1 (catalog) and Phase 2 (design) into two runs, or narrow Phase 1 to the 3-4
  domains where an own-benchmark is most likely (logical/CSP, code-reasoning, instruction-following, math).
- **Overlap:** the lighter exploratory agent (#29) is already returning a first feasibility read; this prompt is
  the deeper version and will supersede it.
- **Already-found own-benchmark seeds** (from the replacement research, worth handing the agent as a head start):
  ZebraLogic/AutoLogi (procedural CSP — generators released), DyCodeEval metamorphic code-mutation (rotatable
  code-reasoning), GSM-Symbolic levers (reasoning-hop depth works; NoOp distractors discredited), AURC +
  self-consistency (a judge-free calibration metric).
- **Red-team access:** GPT-5.5 xhigh (codex CLI) and Gemini 3.1 Pro (Gemini API key) are ready to go. **Qwen 3.7
  Max is the open access question** — there's no DashScope/OpenRouter key in the standard key set; provide one (or
  say "use OpenRouter") or the agent substitutes the strongest reachable Qwen and flags the substitution.
- I can run this for you as a workflow whenever you say go (I'd orchestrate the 3-model red-team properly) — or you
  paste the block into a fresh agent yourself.
