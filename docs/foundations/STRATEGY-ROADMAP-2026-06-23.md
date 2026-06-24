# local-bench — strategy + roadmap (oracle-informed synthesis)

Date 2026-06-23. Source: GPT-5.5 Pro (oracle) strategic review `localbench-project-agentic-
strategy-review` (full transcript in that oracle session; briefing at
%TEMP%\project-strategy-oracle-briefing.md), weighed against the CLI agent's own analysis.

## The reframe (the single most important takeaway)
local-bench is strongest as **the decision layer for local deployment** — *"which exact local
artifact (model + quant + lane) should I run on this class of consumer GPU, and at what
speed/VRAM/quality tradeoff?"* — NOT "the one true local-intelligence leaderboard." The
**product object is a decision card, not a trophy rank.** The rank is useful; the
recommendation ("use Q4_K_M; Q6/Q8 cost VRAM for no measurable gain; this distill underperforms
its base") is the differentiator. Ship narrow; be almost annoyingly explicit about scope.

## Verdict
Core strategy is RIGHT (judge-free, locked scorecards, candidate-vs-headline separation, quant
as a decision problem). The error is **language that sounds broader than the evidence**: a
2-axis Knowledge+Instruction score is "Core Text," not "intelligence" unless the subtitle is
always attached.

## P0 — credibility footguns to fix BEFORE more benchmarks
1. **Terminology contradiction (verify + fix):** methodology overview reads "agentic = candidate"
   while `axes.py` says BFCL-agentic = experimental/non-promotable. Split into a
   **`function_calling` profile (BFCL AST/multi-turn)** and a future **`agentic_exec`
   candidate**; make methodology + registry + website + docs agree. Small inconsistency,
   outsized trust cost.
2. **Lock sampler semantics:** finish the **top_k=1** greedy hardening (don't ship temp-0-only).
   Already queued as the post-campaign no-op check.
3. **Make lane ranking impossible to misread (see Lanes below).**
4. **Stratified frozen slices:** the suite's first-N item selection is a credibility weakness;
   move to stratified-random frozen slices BEFORE scaling to many families. NOTE (CLI agent):
   this re-baselines existing Qwen/gemma runs — real cost, but cheaper now than later.

## Agentic axis — build execution-verified, do NOT promote BFCL
- **Hard truth: agentic cannot be promoted using BFCL.** BFCL = function-calling/tool-format
  profile (keep as diagnostic). Under the no-LLM-judge rule, the only defensible path is
  **execution / final-state verification; trajectory metrics are diagnostics, never score.**
- **Build `localbench-agent-v1` (a small DETERMINISTIC local tool-world).** Construct: complete
  multi-step, stateful, tool-mediated tasks under a fixed tool protocol + turn budget + token
  budget, scored ONLY by final state + exact artifacts. Harness: model emits `tool_call` or
  `final_answer` JSON; deterministic Python tools; no internet; no LLM user-sim; no trajectory
  judge; all initial states + target assertions hashed. A model that can't emit valid JSON
  loses (that's part of tool-use capability).
- **Task families (120-160 scored + a `lite` tier):** (1) stateful business APIs
  (orders/refunds/inventory/policy), (2) cross-app personal workflow (calendar/email/notes/
  files with forbidden-action constraints), (3) local doc + SQLite tools (search/reconcile/
  compute/update), (4) adversarial/collateral-damage (irrelevant tools, forbidden writes,
  prompt-injection in tool outputs, canaries, permission boundaries). NOT code-gen (that's
  coding-exec).
- **Score = Agentic Success Rate** = % tasks where all final-state assertions pass AND no
  forbidden-collateral assertion fails. Hard-fails: wrong/missing/forbidden state change,
  invalid final answer, max-turn/token-cap exceeded, unrecoverable malformed tool call,
  forbidden/destructive tool, canary misuse. Display-but-don't-composite (v1): invalid-tool-call
  rate, schema errors, turns, tokens, timeouts, collateral rate, recovery-after-error. **Do NOT
  put efficiency in the main score** (models learn recklessness) — measure success, then show cost.
- **Separate lane + budget:** 8-12 tool turns, fixed 64k ctx, greedy top_k=1, global token cap,
  per-turn cap, smaller per-turn thinking cap than the K+I lane; cap-hit = task failure.
- **Off-the-shelf pointers:** **AppWorld** = best existing match (local API world, programmatic
  state/unit-test verification, collateral checks) — pilot an "AppWorld-lite" subset or borrow
  its design. τ²-bench = good design source but needs a deterministic FSM user (not the LLM-sim).
  AVOID for the scored axis: SWE-bench (contamination/scaffold-heavy; OpenAI dropped it),
  WebArena/GAIA (later/diagnostic), ToolBench/ToolEval (uses an LLM judge).
- **CLI-agent nuance (de-risk the build):** building a bespoke tool-world is the BIGGEST item on
  this roadmap. START by piloting AppWorld-lite (it already has deterministic verifiers) to
  validate the construct cheaply; build bespoke tasks only after the construct discriminates.
- **Promotion gate (stronger than "separates a small ladder"):** ≥95% human-audit agreement on
  pass/fail; repeated-run stability within pre-registered CI; discrimination across ≥3 families
  × 3 size bands with CI-bound spread; no floor/ceiling; independence from K+I (not instruction-
  following in disguise); gaming audit (parser/schema targeting doesn't trivially win); cost
  feasible on one 5090. Until then: candidate, displayed separately. If it validates → a future
  **Overall Local Score**, NOT the Core Text headline.

## Headline composition
- **v1: Core Text Score = 50% Knowledge + 50% Instruction.** Keep. Card shows: Core Text, K, I,
  weakest axis, lane, quant, VRAM, tok/s, answer-cap-hit, tokens-to-answer, CI, recommended quant.
- **Do NOT add math yet** — olympiad-hard puts locals near the floor (not discriminating); rebuild
  with mixed difficulty that separates 7B/14B/30B first.
- **Do NOT call BFCL "agentic"** — rename to function-calling profile.
- **Coding-exec = "Extended Exec"** until it validates.
- **No "Overall Score" until ≥1 execution axis validates.** Promotion gate = 10 criteria
  (measurement validity + product value); the load-bearing one: *if an axis doesn't change "which
  model/quant should I run?", it's a profile metric, not a headline metric.*
- Weighting: 50/50 fine for 2 axes; once ≥3 validated, capped spread-proportional (not naive equal).

## Lanes — two tables (Option C)
Per-lane labeling is NOT enough if cross-lane composites sit in one ranked column (users WILL
compare them). Design:
1. **"Best Local Operating Mode"** — user-facing decision table; each model in its recommended
   native mode (reasoning→capped-thinking, non-reasoning→answer-only); lane + cost first-class.
2. **Apples-to-apples diagnostic lanes** — capped-thinking-only / answer-only-only / coding-exec /
   agentic-exec, each ranked WITHIN its estimand.
Rule: **rank within estimand; summarize across estimands only as "recommended operating mode."**

## Roadmap sequence (solo maintainer, one GPU)
- **P0:** fix the credibility footguns above (terminology, top_k, lane tables, stratified slices).
- **P1:** ship v1 read-only with the narrow promise ("reproducible local model+quant decision
  cards on a single RTX 5090"). Don't wait for agentic; don't ship "overall intelligence" copy.
- **P2:** increase model-FAMILY coverage — run FEWER quants across MORE families (Q4+Q6 for major
  contenders; Q8 only for a quant-loss question; full ladders only for likely winners/surprises).
  Goal = "the practical Pareto frontier for this GPU class," not "we ran everything."
- **P3:** build `agentic_exec` v0 (pilot AppWorld-lite first; bespoke only if it discriminates).
- **P4:** candidate-axis discrimination campaign (math, long-context, coding-exec, agentic-exec
  through the promotion gate; promote nothing on vibes).
- **P5:** KLD/drift diagnostics selectively (support decision pages; don't let it consume the project).
- **P6:** v2 community submissions (only after the score surface is stable; the trust-tier design
  is good).

## What NOT to do
Browser/GUI/WebArena for v1 agentic; LLM judges anywhere scored; LLM-sim user in a scored agentic
axis; promote BFCL as agentic; full SWE-bench; chase every model release; support every backend/OS;
over-invest in submissions before anchor credibility; claim Q4 is *universally* lossless (we have
cross-family EVIDENCE, not a law); a broad Overall Score before an execution axis validates; let
answer-only + capped-thinking silently share one rank.

## Differentiation (the niche)
Can't beat Artificial Analysis on breadth. Niche = **artifact-level local deployment guidance on
one consumer GPU**: GGUF/quant behavior, reproducible transcripts, runtime settings, VRAM, speed,
tokens, drift/churn, scorecard identity. AA/Open-LLM answer "what model is strong?"; local-bench
answers "which exact local artifact should I run on my 5090, at which quant, with what tradeoff?"
vs LMArena (not deterministic/local/quant/judge-free; "Leaderboard Illusion" concerns) and model
cards (BF16/API-oriented, omit local runtime). Be the thing users consult AFTER the model card.

## Immediate implications for the live campaign (CLI agent)
- **"More families, not more quants"** redirects the benchmark loop: the deep gemma quant ladder is
  lower-value than breadth. RECOMMEND: let gemma Q3 finish (running), then **skip gemma Q5** (a
  deeper quant on an already-bracketed family) and instead add a NEW family at Q4+Q6. Pending
  Michael's call.
- top_k=1 check + KLD pilot stay queued (P0.2 / P5).
- Site framing → "decision card, not trophy rank" is guidance for the SITE agent.

## Open decisions for Michael
1. Endorse the reframe + "Core Text" naming (renames "Local Intelligence Index" → subtitle always on)?
2. Greenlight the agentic_exec track (pilot AppWorld-lite first)?
3. Redirect the benchmark loop to "more families at Q4+Q6" (skip gemma Q5)?
4. Fix-now vs later: the stratified-slices re-baseline (it re-runs existing data).
