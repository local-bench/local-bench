# suite-v1.1 methodology proposal (AA-v4.1-informed) — for red-team

*2026-06-16. Trigger: Artificial Analysis Intelligence Index v4.1 shifted toward agentic, REMOVED IFBench
for saturation, and added per-task cost/time/tokens metrics. Michael wants the methodology RIGHT before any
more tests. This proposal is to be adversarially red-teamed (GPT-5.5 xhigh) before we build/test.*

## 0. Our own corroborating data (this morning, real runs)
- **IFBench is saturating in the REASONING lane**: Qwen3.6-27B-Q4 reasoning = 100% (n=6); GPT-5.5 87.5%, Gemini
  97.5% (n=40, old anchor data, soft). In ANSWER-ONLY it still spreads: Qwen-Q4 53.8%, Q2 47.5%, Gemma-12B 42.5%
  (n=80). So IFBench discriminates the local range only in answer-only — and we just chose the reasoning lane.
- **BFCL single-turn AST (our agentic axis) is saturated**: Qwen-27B-Q4 = 91.2% (n=80) — AT/ABOVE GPT-5.5 (82.5%)
  and Opus (84.0%). A 27B beating frontier ⇒ the axis measures call-formatting, not agentic capability. (BFCL
  numbers span pre/post the boolean-fix era — soft, but the direction is unambiguous.)

## 1. The core reframe (sharper than "we can't follow AA")
AA's mission is **separating frontier models**; ours is **separating local setups + measuring distance-to-frontier**.
AA's v4.1 core (Terminal-Bench 2.1, SWE-bench, GDPval) **floors the local range** (our research: Qwen2.5-Coder-32B
4.9% on SWE-bench, 7-13B ≈ 0%; GDPval needs frontier judges). A bench where every local scores ~0 gives us zero
discrimination even run server-side. So we don't chase those — not (only) for constraint reasons, but because they
measure the wrong range. The **agentic SHIFT** itself we CAN reappropriate via harder-but-local-runnable tool-use.

## 2. Proposed changes

### 2a. Agentic axis: execute the (already-decided) multi-rung upgrade — the build skipped it
`suite-v1-DECISION.md §1` already locked Agentic = **ToolHop (core) · BFCL multi-turn · BFCL-AST (floor)**, but the
shipped suite has only BFCL-AST single-turn. Build the rungs:
- **ToolHop (CC-BY-4.0, code Apache)** — multi-hop tool use, GPT-4o ~49% (frontier headroom), **judge-free**,
  final-answer correctness over an interdependent chain. Exec posture: tools are locally executable Python; run
  **in-process, non-networked, vendored audited stubs** (NOT model code) — a *carve-out* of the no-exec rule, OR
  grade call-sequence correctness without running. NEEDS ACQUISITION (`bytedance-research/ToolHop`).
- **BFCL V4 multi-turn (Apache-2.0)** — **data already vendored** (`bfcl-eval-ref/.../BFCL_v4_multi_turn_*.json`);
  simulated in-process stateful backend, **state-comparison + AST, no live API, no judge**. Just build the axis.
- **BFCL-AST single-turn** — keep as the FLOOR rung (separates weak locals), down-weighted.
- **Seal-Tools (Apache-2.0)** — the **pure-no-exec alternative** (JSON comparison: format-match + API-name F1 +
  param F1, zero execution, no judge) if the red-team rules the ToolHop exec carve-out unacceptable.

### 2b. IFBench fate (NEW — AA-prompted)
AA removed it; our reasoning-lane data corroborates saturation. Proposal: **keep IFBench for now but make its
reasoning-lane discrimination a PRIMARY probe question**; if the probe confirms saturation (anchors + a 27B
cluster high), **demote its weight and prioritise the ring-fenced own-IFBench** (procedural compositional
instruction-following, harder by construction). Do NOT silently keep a saturated axis at full weight.

### 2c. Index / normalization
Keep **absolute chance-corrected normalization** (temporally stable; a fixed score means the same thing across
model generations) rather than AA's **Elo** (relative to the current field, drifts as the field changes). For a
*distance-to-frontier + quant-delta* tool, absolute is the better fit. Do NOT reweight toward agentic until the
agentic axis is de-saturated (else we'd up-weight a broken axis). Re-confirm vs AA's reasoning.

### 2d. Per-task metrics — ADOPT
AA made Cost/Time/Tokens-per-task headline; we already spec tokens-to-answer in the reasoning-lane doc. Surface
all three AA-style (accuracy vs compute-burned), never folded into the accuracy score.

### 2e. The exec/judge line — confirm pure-local-runnable
Keep judge-free + (exec-free OR in-process vendored-stub carve-out). No server-side LLM-judge tier (breaks
reproducibility/cost/community-runnable; and the benches that need it floor the local range anyway).

## 3. The sequencing point (important)
The **discrimination probe** (`suite-v1-DECISION.md §3`) is THE gate that finalises axis selection + weights from
OUR runs — but it's a TEST, and tests are on hold. So: this red-team + the agentic BUILD are DESIGN + CODE (no
tests); they make the suite methodologically complete so that when the probe IS green-lit it measures the RIGHT
suite. Methodology-right-before-tests = nail the axis design + build the scorers now; the probe validates later.

## 4. Public tooling (the "reappropriate with public tools" answer)
ToolHop (HF + Apache code), BFCL/`bfcl-eval` (Apache, vendored), Seal-Tools (Apache), ZebraLogic (logic/CSP,
judge-free, generatable), LiveCodeBench-output-pred (we use), MMLU-Pro (we use) — all public, runnable, judge-free.
Frameworks like inspect-ai / lm-eval-harness exist but we keep our thin in-process scorers (no heavy harness dep).

## 4b. VERIFIED (web research, 2026-06-16) — the axis-killer question answered
The load-bearing risk was "does the harder agentic bench FLOOR small locals (like SWE-bench) or discriminate?"
Measured:
- **ToolHop DISCRIMINATES the local range** — Qwen2.5 7B **11.5%** → 14B **17.4%** → 32B **20.0%** → GPT-4o **~49%**.
  Not floored, real gradient, frontier headroom (arXiv 2501.02506). License CC-BY-4.0. Exec = in-process Python
  tool stubs → the multi-hop signal NEEDS the tools run (grading-without-running loses the chain), so the
  vendored-audited-non-networked-stub carve-out (resource/timeout-limited, like our existing no-Docker
  constrained-exec lane) is the posture. **→ CORE.**
- **BFCL multi-turn DISCRIMINATES + is already vendored** — small models drop to ~35% multi-turn (Qwen3-4B) vs
  82% single-turn AST; frontier ~75% (BFCL-V4 leaderboard). Judge-free state-comparison, in-process sim. **→ RUNG.**
- **BFCL-AST single-turn = saturated** (our 27B 91% ≈ frontier) → keep as down-weighted FLOOR only.
- **tau2/tau3-bench EXCLUDED for our core** — requires an LLM USER-SIMULATOR (gpt-4.1/gpt-5.2 in the loop);
  scoring reward is programmatic (judge-free) but the user-sim is a frontier-LLM dependency → not local-runnable,
  not deterministic. (This is AA's territory; they run it datacenter-side.)
- **Seal-Tools = unverified fallback** — judge-free, zero-exec JSON comparison, but cross-size discrimination not
  confirmed and shape looks closer to the saturating AST task. Use only if the ToolHop exec carve-out is rejected,
  and verify its spread first.

**Finalized agentic axis: ToolHop (core) + BFCL-multi-turn (rung) + BFCL-AST (down-weighted floor).** All
judge-free; ToolHop uses the constrained-exec carve-out; the other two are no-exec/in-process-sim.

## 5. Questions for the red-team (be CERTAIN before we build)
1. **Agentic set**: is ToolHop(core)+BFCL-multi-turn+BFCL-AST(floor) right? Is the ToolHop in-process vendored-stub
   exec carve-out acceptable, or must we use Seal-Tools (pure no-exec)? Does each rung actually discriminate the
   LOCAL range (1-14B→frontier), not just frontier-vs-frontier? Current dataset state/license/contamination?
2. **IFBench**: keep-and-measure vs replace-now vs demote? Is the reasoning-lane saturation real enough to act on
   pre-probe, or strictly a probe question? Is own-IFBench the right durable answer, and is it in scope now?
3. **Normalization**: absolute chance-corrected vs Elo — which serves distance-to-frontier + quant-delta better?
   Any AA per-task-metric or cached-token nuance we should copy?
4. **Anything missing**: a public, local-range-discriminating, judge-free bench (agentic or otherwise) we're not
   considering? Any way the proposed agentic axis still saturates or floors? Any methodology error that would
   make the eventual probe measure the wrong thing?
5. **Sequencing**: is "build the agentic axis now, probe-validate later" sound, or does anything here REQUIRE a
   measurement before we commit code?

End with: a finalized recommended axis set (+ exec/judge posture per rung), a GO / GO-WITH-FIXES / NO-GO on
building the agentic upgrade, and the must-fix list.

---

## RED-TEAM VERDICT (GPT-5.5 xhigh, 2026-06-16) — GO-WITH-FIXES
Web-verified the axis-killer (ToolHop discriminates: 7B 11% → 32B 20% → GPT-4o 49%; BFCL-multi-turn discriminates;
tau2/tau3 excluded for the LLM user-sim dependency). The methodology is sound; the risk is **measuring the
harness/stub fidelity instead of the model**. Build the agentic axis WITH these must-fixes (folded into the build):
1. **Pin ToolHop dataset/code/license provenance with hashes** before implementation.
2. **Define the constrained-exec contract precisely** — NO broad in-process arbitrary Python. Safe version: frozen
   audited tool stubs, allowlisted imports, **no network / no subprocess / no filesystem writes**, deterministic
   RNG + time, resource/time limits; else a process boundary or reject. (Applies to ToolHop AND the BFCL
   multi-turn in-process env.)
3. **Golden-trace / stub-conformance tests** (deterministic) BEFORE any model scoring.
4. **Failure taxonomy logging**: format / wrong-tool / wrong-args / wrong-state / wrong-final-answer / timeout
   (so the probe can split "bad call syntax" from "bad state reasoning").
5. **Report ToolHop, BFCL-multi-turn, BFCL-AST SEPARATELY** before any composite weighting.
6. **Pre-register the discrimination probe design** (model set, budgets, retries, max-turns, context budget,
   saturation thresholds) — the probe must hold prompting/format/retries/turns CONSTANT across models, or it
   measures the scaffold, not the model.
7. **IFBench reasoning-lane weight is PROVISIONAL** until the probe confirms it still separates locals.

**Decision: GO on building ToolHop (core) + BFCL-multi-turn (rung) + BFCL-AST (floor)** with the above contract.
Normalization stays absolute chance-corrected. Build = design + code (no tests/GPU/spend); the probe (held)
validates discrimination later under the pre-registered design.
