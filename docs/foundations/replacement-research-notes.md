# Replacement-benchmark research — running notes (2026-06-13)

Gap-filling research for the axes the suite-v1 revision down-weighted or removed (coding,
agentic, math frontier-headroom, calibration) + a wildcard sweep for missing axes + an
exploratory "build our own benchmark" side track (#29). Five agents launched in parallel;
this file accumulates their findings as they return, to be synthesized into
`suite-v1-REVISED.md` once all land. **All numbers below are published (stale-in-weeks) —
they justify WHAT TO PROBE, never final weights (the §6 measure-first rule still governs).**

Agent status: calibration+wildcard ✅ · coding ✅ · agentic ✅ · math-headroom ✅ · own-benchmark ✅ (ALL 5 IN)

---

## Calibration + wildcard missing axes ✅ (agent a36103e596d7bcae0)

### Calibration / hallucination → confirm DEFER to v2, but the build is now de-risked
- Off-the-shelf all fail our constraints: **AbstentionBench** is CC-BY-**NC** + non-discriminating
  ("scale has almost no effect"); **AA-Omniscience** proprietary + needs grading; SimpleQA needs a judge.
- **The unlock (kills the old "it just rewards refusal" objection):** score with **AURC** (Area Under
  the Risk-Coverage curve) over **self-consistency confidence** (sample k=5-8×, confidence = answer-
  agreement frequency — NOT verbalized confidence, which is biased). AURC discriminates by capability
  (measured: Claude-Sonnet-4 0.242 vs Qwen3-235B 0.472) and **cannot be gamed by blanket refusal**
  (abstain-all → zero coverage → degenerate AURC).
- **Build-our-own design:** item pool = false-premise + unanswerable + matched answerable controls
  (controls are required to compute the risk-coverage curve), seeded/regenerated from FalseQA + (QA)²
  (regenerable = contamination-resistant); correctness via programmatic pushback detector (regex
  refusal/correction markers) + existing MCQ/exact-match; axis score = AURC + honest-abstention rate
  as a secondary diagnostic. Stratify false-premise items by entity obscurity for a difficulty gradient.
- Verdict: still a **v2** axis (not launch-gating), but now low-risk and a real differentiator (AA spends
  a whole Index slot on this via AA-Omniscience). Reuses our existing multi-sample infra.

### Wildcard missing axes (ranked, all PROBE-GATED)
1. **Logical / CSP reasoning — the standout missing axis.** LiveBench itself runs Zebra puzzles in its
   Reasoning category (judge-free precedent). Candidates:
   - **ZebraLogic** (ICML 2025) — synthetic (randomized + Z3 uniqueness check → contamination-immune),
     judge-free (cell-wise EM gives partial credit for the floor + puzzle-level all-correct separates the
     top). Spread: 7-10B **<1%** hard → Claude-3.5 33.4% / 12.4% hard → frontier ~97%. **Best discriminator.**
     ⚠️ verify repo license. Risk: floors at the hard end → gate puzzle size by the probe.
   - **AutoLogi** (Qwen+Fudan) — open-ended (anti-guessing), **generation pipeline + program verifiers
     released** (regenerable). CC-BY-SA-4.0 (arXiv listing; SA = share-alike, NOT NC → servable; ⚠️ no repo
     LICENSE file — verify). Spread: Llama3.1-8B 30.8% → 70B 58% → 405B 68% → GPT-4o/Claude-3.5 ~70%
     (compresses at top = local-range discriminator, reference-ceiling at frontier).
   - **NPHardEval** (Apache-2.0) — CSP/planning alt (TSP/Knapsack/Graph-Coloring × 10 difficulty levels,
     auto-gen + auto-check, monthly refresh). Generator withheld (data+checker only → weaker contam posture).
     **Overlaps ZebraLogic — pick ONE CSP family to avoid correlated double-count in the composite.**
   - **SATBench** (CC-BY-4.0) — likely **too hard** (o4-mini 65% on hard UNSAT ≈ 50% floor → floors all
     locals); keep only easy/medium if the probe shows local signal, else skip.
   - **Recommendation:** add a **Logical-Reasoning axis** seeded by ZebraLogic (cell-wise + puzzle) +
     AutoLogi (open-ended rung), probe-gated. Clean, generatable, judge-free, hardest floor→ceiling spread
     of anything surveyed — exactly the shape v0 genmath lacked. **Also feeds the build-our-own track (#29):
     these are procedurally generated, so we could author our own CSP generator instead of vendoring.**
2. **Table / structured-data reasoning — TableBench** (Apache-2.0). EM on Fact-Check + Numerical subtasks
   (defer Visualization — needs code-exec). Clean gradient: Qwen2.5-7B 22% → 72B 49% → GPT-4o 52% →
   Claude-4-Sonnet 55% → o4-mini 62% → human 86%. Distinct capability, clean license, spreads locals AND
   keeps a human-gap ceiling. ⚠️ verify subtask scorers are EM not ROUGE.
3. **BBEH** (Apache code + CC-BY-4.0 data — flag closed, it's clean) — keep as the **top-end stretch rung**
   already in the spec (best general 9.8% / best reasoning 44.8% → floors sub-30B; informs the TOP only).
4. **NPHardEval** — see #1 (CSP alternative).
- **Skip:** SATBench (floors frontier), scientific-beyond-GPQA (SuperGPQA suffices), commonsense-adversarial
  / trap-robustness (better as in-axis perturbation variants than a standalone axis).

### License flags to verify before serving
ZebraLogic repo license · AutoLogi repo LICENSE (CC-BY-SA from arXiv listing only) · FalseQA license ·
TableBench per-subtask scorer (EM vs ROUGE).

---

## Agentic ✅ (agent a6af5c025468f8bb7) — VERDICT: a frontier-discriminating local agentic axis IS achievable
Blind spot corrected: "static function-calling" ≠ "single-turn BFCL AST". Harder statically-gradable
function-calling benches re-open frontier headroom. Recommended upgrade to a multi-rung agentic axis:
- **ToolHop (CC-BY-4.0) — NEW CORE.** Multi-hop tool use; 3,912 self-contained executable Python tools
  (zero-cost, offline). Discriminates at BOTH ends: GPT-4o 47.7 / Claude-3.5 45.2 / Gemini-1.5-Pro 33.1
  (~14pt frontier spread) and 72B 38 → 14B 26 → 7B 16 → 8B 13.5 (clean local ladder, no floor). The one
  bench that separates frontier-vs-frontier AND the local range. ⚠️ CAVEAT: running its tools is code-exec
  of VENDORED audited non-networked stubs (not model code) — mild bend of the no-exec rule; carve-out
  ("executes only vendored audited stubs") or grade on call-sequence correctness without running.
- **BFCL V4 Multi-Turn (Apache-2.0) — FREE ADD-ON.** Already vendored — just stop excluding the multi-turn
  category. Simulated in-process stateful Python backend (no live API, NO judge), state-comparison + AST
  match. 5-10pt harder than single-turn for every model; Qwen3-0.6B ~1.4% → GPT-4o/Sonnet ~76-78%.
  Berkeley weights it 30% in V4 *because* single-turn AST saturated.
- **Seal-Tools (Apache-2.0) — NO-EXEC ALTERNATIVE.** Pure JSON comparison (format-match + API-name F1 +
  param F1), nested calls, zero execution, no judge. Cleanest if the no-exec rule is strict. Frontier
  numbers unverified (needs-probe).
- **NESTFUL v2 (Apache-2.0) — HARD STRETCH (probe-gated, normalized).** Nested API sequences; very hard
  (GPT-4o ~28% full-seq, Llama-405B ~10%) → compresses at top; use Win Rate metric. Use data_v2 (local
  executables) NOT v1 (RapidAPI).
- **ACEBench (repo MIT; arXiv license is just the submission)** — parameter-type + irrelevance/infeasible
  detection; English subset; static categories only. Needs-probe (backend-independence + data license).
- Keep **BFCL non-live AST** only as the **floor rung** (still sorts weak locals), like MMLU-Pro for knowledge.
- REJECTED: API-Bank (saturated, GPT-4 92.9), ComplexFuncBench (LLM-judge + 128k), ToolSandbox (Apple
  license + user-sim + RapidAPI), NoisyToolBench (LLM evaluator), ToolACE (it's a training-data pipeline,
  not a bench), HammerBench (ROUGE-L fuzzy scorer — usable but noisier).
- needs-probe flags: Seal-Tools frontier spread, ACEBench static-category backend independence + data license,
  NexusBench per-task scoring.

## Coding ✅ (agent ab4985e97e3d73576) — VERDICT: coding is SHIPPABLE, not "Docker-only/unmeasured"
Prior "no exec-free coding signal" conclusion was too pessimistic + factually wrong on LiveCodeBench. 3 lanes:
- **EXEC-FREE SPINE (ship): LiveCodeBench Test-Output-Prediction + Code-Execution scenarios.** Model predicts
  the literal output string → exact-match, NO sandbox needed to score. **CC-BY-4.0 (data) + MIT (harness).**
  Date-windowed (`--start_date/--end_date`, v6=Apr 2025) = genuinely contamination-resistant + rotatable.
  Clears all gates. ⚠️ exact small-vs-frontier split not cleanly published (needs-probe). ⚠️ LCB problems are
  sourced from LeetCode/AtCoder/Codeforces → their ToS *may* constrain commercial redistribution of problem
  statements regardless of the CC-BY wrapper (Michael-awareness; it's the field-standard served artifact).
- **SAFE NO-DOCKER CONSTRAINED-EXEC (ship, default-on): network-denied, resource-limited, timeout-killed
  subprocess** running HumanEval+/MBPP+/LCB-codegen. The whole ecosystem already does exactly this (HumanEval
  `reliability_guard` + EvalPlus + bigcode + LCB = subprocess+neuter+rlimits+timeout, Docker optional). Pure-
  function benches = full fidelity in a no-FS/no-net sandbox. **Docker → opt-in `--sandbox docker` hardening,
  NOT a prerequisite.** Weak leg = Windows (Job Objects, no seccomp/`resource`) — the strongest arg for
  offering opt-in Docker. Requires an honest first-run disclaimer (modeled on HumanEval's).
- **DOCKER OPT-IN MODULE (later):** LiveCodeBench (recent window) spine (needs no Docker itself) + optional
  BigCodeBench-Hard (Apache-2.0, anti-saturated ~30-35% frontier, not floored).
- **TRAPS — frontier-only, FLOOR the local range, do NOT use as core:** SWE-bench Verified (Qwen2.5-Coder-32B
  only **4.9%**, 7-13B ≈ 0), Terminal-Bench-Hard (AA v4's coding axis — floors locals), SciCode (≈0 for small).
- **REJECTED:** CodeMMLU (MIT but **NON-MONOTONIC** — Qwen-14B beats Llama-70B & R1; frontier doesn't stay
  above locals = the v0 failure mode AGAIN — important catch, would have re-failed), CRUXEval (re-confirmed
  contaminated), CoRe / BigO-Bench (CC-BY-NC), RestrictedPython/Pyodide (NOT security boundaries; note: Pyodide
  is NOT abandoned — 314.0.0 Jun 2026 — it's just not a sandbox).
- **STEAL FOR BUILD-OUR-OWN:** DyCodeEval / "Dynamic Benchmarking" metamorphic mutation (variable-rename +
  semantics-preserving structural mutation) → rotatable code-reasoning items; verified to spread the local
  range (StarCoder2-3B 20.8 → Qwen-7B 26.6 → 14B 39.2 → 32B 40.3 → DeepSeek-V3 46.7).

## Math frontier-headroom ✅ (agent ad1059e5a82c67dd9) — frontier-math is a real CEILING; distance-to-frontier is fixable
- **License-clean + judge-free + fully-local + FRONTIER-vs-frontier math = NOT achievable in 2026** (structural,
  not a search gap). The frontier separators are all blocked: FrontierMath (private/Epoch-held, OpenAI-exclusive),
  MathArena incl. Apex (CC-BY-NC-SA), Lean formal proof (measures prover SCAFFOLDS not models-as-shipped; toolchain
  not locally installable for Windows hobbyists; compiling LLM-emitted Lean = arbitrary code-exec → only viable
  server-side, anchor-only, P3). **ACCEPT the ceiling**; get frontier signal from other axes (MMLU-Pro/SuperGPQA).
- **Distance-to-frontier WITH restored discrimination = YES, cleanly.** Replace the saturated genmath *discriminating*
  rung with **AMO-Bench-39** (MIT; 50 NEWLY-AUTHORED, originality-verified problems → genuinely contamination-resistant;
  use the 39 parser-checkable, drop the 11 LLM-judge ones; IMO-level, sub-60% pass@1 for everyone = wide spread) +
  **OlymMATH-HARD-100** (MIT; answers restricted to reals/intervals e.g. `[√33,+∞)` for rule-based SymPy; ~38pt spread
  Gemini-2.5-Pro 58% → R1 20%). ~139 MIT, SymPy-checkable, contamination-resistant items that floor locals + keep the
  frontier on top. Keep generated-math as the **private sentinel** (its real value), not the discriminating rung.
- **REQUIRES the sympy/Math-Verify scorer upgrade** (math_numeric.py is scalar+fraction only; can't do intervals/sets/
  symbolic). Same prereq the earlier math agent flagged.
- **LICENSING CATCH (corrects earlier math agent's "HARP=MIT, the find"):** HARP's MIT covers PACKAGING only — its
  problems are AMC/AIME/USAMO = **MAA-copyrighted** (same reason we excluded AIME). Same for OlympiadBench (real
  olympiads + Gaokao, third-party copyright; MIT wrapper only). → **AMO-Bench (newly authored) is the cleanest pick;**
  flag HARP/OlympiadBench problem-provenance for the licensing audit.
- FLAGS: OlymMATH-HARD frontier-2026 numbers inferred from early-2025 models (probe before trusting as a frontier
  separator); MathArena ArXivMath is CC-BY-SA (not NC) but arXiv-source licenses unverified (derivative risk); ignore
  the llm-stats "Apex 90.2%" figure (unverified, contradicts official ~5%).

## Build-our-own benchmark — EXPLORATORY (#29) ✅ (agent ae945b395697d1cd5) — VERDICT: GRADUATE to a real workstream
- **YES — author 2-3 procedural axes** (scoped, NOT a from-scratch suite). More defensible than the foundations docs
  credit: should be a PRIMARY discrimination strategy, because assembled benches leave only 2 of 5 genuinely
  discriminating (SuperGPQA, IFBench — both with serving-license/saturation risk we DON'T control). With an
  own-benchmark we control saturation + license + contamination BY CONSTRUCTION (verification asymmetry: the generator
  computes the gold, so scoring stays exact-match/poly-time even when solving is hard). EXTENSION not greenfield — we
  already ship the engine (`suite/genmath_gen/` ~1914 LOC, public/private sentinel + disjointness, judge-free, 169 tests).
- **DURABLE difficulty levers (bite the frontier):** (1) search-space size / NP-hard optimization (most durable —
  combinatorial, doesn't evaporate with scale; ZebraLogic X-Large <50% for o1/R1, not fixable by inference compute);
  (2) execution-step / state-mutation depth (code tracing — continuous dial ~3 OOM); (3) compositional constraint
  stacking (own IFBench — OOD constraints defeat memorization); (4) long-context multi-hop.
- **DEFEATED levers (TRAPS — avoid):** GSM-NoOp distractors (DEBUNKED — only 12.4% of auto-distractors truly
  irrelevant; frontier drop ≈ 0 after audit); shallow added-hop perturbations of grade-school math (GSM-Symbolic
  P1/P2 — frontier shrugs off); fixed-template small-world (bAbI saturates). ARC-AGI cautionary (measures the
  harness/TTT, not the model — our no-sandbox constraint rightly forbids that shape).
- **⚠️ CORROBORATES the math finding + corrects our current plan:** "harden genmath with GSM-Symbolic levers" (the
  current suite-v1-REVISED.md Math plan) will FLOOR small models but NOT separate the frontier — grade-school math is
  too easy a substrate. → generated-math = **private sentinel**, NOT the discriminating rung; use AMO-Bench/OlymMATH
  (or an own NP-hard/algorithmic axis) for hard discrimination.
- **Judge-free validation toolkit** (the real cost center): CTT item analysis (difficulty p 0.3-0.8, discrimination
  D≥0.3, point-biserial >0.2-0.3); input-ablated baseline (shortcut/leak detection); AFLite-lite prune; convergent
  validity (correlate vs MMLU-Pro/IFEval/SuperGPQA); canary GUID + private rotation; human baseline + bootstrap CIs +
  published generators/verifiers (only ~32% of bench papers report a human baseline → differentiator).
- **RECOMMENDED PILOT (smallest high-signal): own compositional instruction-following (own IFBench)** — best
  risk-adjusted fit (deterministic Python verifiers, IFBench <50% for Claude-4-Sonnet/Qwen3-32B = frontier-hard in
  2026, clean N-constraint difficulty dial, extends existing IFEval work #13). Then own code-output-tracing + own
  logic-grids/CSP. DoD = generator + parity-tested verifier + discrimination probe + validation mini-bundle.
- **Hybrid is the answer:** keep the assembled discriminators that work (SuperGPQA, IFBench, RULER) AND own 2-3
  procedural axes as the contamination-proof spine. "Every own-benchmark failure mode is one we can fix by turning a
  knob/regenerating; assembled-bench failures are external and permanent."
- **META-FLAG (important for ALL the research):** 2026 aggregator leaderboards carry CONFABULATED model names/scores
  ("Claude Fable 5", "GPT-5.5 Pro", "Qwen3.7 Max", "Gemini 3.1 Pro" with "0 verified, 13 self-reported"). The design
  PATTERNS, licenses, and mechanics across all 5 reports are solid; specific "model X scores Y%" numbers are NOT
  load-bearing → trust Epoch AI / official cards / our own probe runs. Reinforces the measure-first rule.
