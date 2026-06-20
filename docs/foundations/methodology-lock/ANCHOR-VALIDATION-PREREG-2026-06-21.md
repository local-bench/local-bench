# Off-family anchor validation — PRE-REGISTRATION (local-bench, 2026-06-21)

Status: design LOCKED here; per-anchor numeric **brackets** are locked in §6 BEFORE each run. Synthesis
of my draft + a GPT-5.5 Pro oracle red-team (session `anchor-validation-design`, transcript in
`~/.oracle/sessions/`). The GO/launch verdict is independent of this; this is an EXTERNAL-VALIDITY check.

## 1. Purpose + precise claim
The Qwen3.5 same-family ladder (0.8B/2B/4B/9B) proved the Local Intelligence Index axes detect **scale
within Qwen3.5**. Off-family anchors test whether the index measures **general capability** vs
Qwen-family output patterns. Precise claim being tested:
> This validates against Qwen-family **architecture / output-tokenizer specificity**, NOT against all
> possible Qwen- or DeepSeek-influenced post-training *styles* (several strong open reasoning models are
> R1-distilled). Granite is the cleanest claim-supporting anchor (Apache, non-Qwen, non-distilled).

## 2. Lane-compatibility constraint (the crux)
The locked headline lane is **capped-thinking**: greedy temp-0, s1 two-pass budget forcing that stops
the think pass on a literal `</think>` and force-closes at the 8192 think cap. Anchors MUST be genuinely
non-Qwen **reasoning** models emitting literal `<think>…</think>`, license-clean, ≤~14B (one RTX 5090),
spanning ~2–9B. **Pre-run mechanical smoke test (gate, §5)** screens this before any full run.

## 3. Anchor set (oracle-recommended, 4 = preferred)
PRIMARY:
- `ibm-granite/granite-3.3-2b-instruct` — Apache-2.0, native `<think></think>` + `<response></response>`.
  (HF reports ~3B params despite "2b" — label "Granite-small". Strip one outer `<response>` wrapper, §7.)
- `ibm-granite/granite-3.3-8b-instruct` — Apache-2.0, same format. Granite-small→8B = a 2nd-family scaling check.
- `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` — Llama-3.1-8B arch, R1-style `<think>`. License = Llama-3.1
  terms (NOT plain MIT — correct the draft). R1-distilled → "style" not "architecture" off-family.
PRIMARY-PLUS (4th, fills the middle):
- `nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1` — Llama-derived, reasoning-on via system prompt. NVIDIA Open
  Model + Llama terms. Card recommends sampling → pre-register greedy-temp-0 as a lane-stress confound.
SENSITIVITY ONLY (run after the 4): `NousResearch/DeepHermes-3-Llama-3-3B-Preview` (R1-style; card warns
hard items can need ~13k think tokens → budget-stress vs our 8192).
EXCLUDED (LANE-INCOMPATIBLE by construction — different delimiters, not literal `</think>`):
Phi-4-mini-reasoning (`<|...|>` format), Gemma thinking (`<|think|>`/channel markers), Granite-4.1
(instruct, not native long-CoT), OpenThinker/Bespoke-Stratos-7B (Qwen-derived → not off-family).

## 4. Metrics (report all three, per anchor × axis)
Same lane + STRICT scoring + the decomposition (from the scorer hardening). Full sets MMLU-Pro 400 +
IFBench 294. Served offline (vLLM, 5090), zero spend.
- **T = termination rate** = natural-`</think>`-close + parseable final / all items (health/property).
- **C = conditional accuracy** = correct / terminated (instruction-following *given* completion).
- **S = strict accuracy** = correct / all items (non-terminating → incorrect; the locked-lane leaderboard score).
**C is the PRIMARY cross-family capability-placement metric** (S mixes termination, which across families
is a chat-template/RL artifact, not capability). S stays the user-facing leaderboard score. Identity
S = T × C.
Health metrics tracked: natural_think_close_rate, forced_close_rate, final_answer_parse_rate,
leaked_reasoning_rate, length_stop_rate, empty_or_no_final_rate.

## 5. Pre-run mechanical smoke test (GATE before full runs)
Serve each anchor; send a small probe set under the EXACT pre-registered rendered prompt (official
reasoning activation only — no post-hoc prompt tuning). A model qualifies for a full run ONLY if its raw
decoded output contains a literal natural `</think>` (before budget exhaustion) at a healthy rate. A
model that fails → **LANE-INCOMPATIBLE**, dropped (not evidence of Qwen-bias).

## 6. Validity criterion — 4-status, bracketed, CI-thresholded
For each anchor × axis, BEFORE running, set an expected **Qwen-rung bracket** `[lower_rung, upper_rung]`
from external public / model-card evidence — used as BROAD ordinal bands only (cards often use sampling;
our lane is greedy temp-0; do NOT use sampled numbers as point targets). Sample-size reality: at ~50%,
SE ≈ 2.5pp (400 items) / 2.9pp (294 items) → a 10pp miss is signal, a 3pp miss is noise.

Health gate: if `T ≥ min(Qwen-ladder T) − 10pp`, use **C** as primary placement; else → LANE-INCOMPATIBLE
/ INCONCLUSIVE (do not claim PASS from C alone). Also run a terminated-subset difficulty audit (compare
Qwen-ladder avg accuracy on anchor-terminated vs non-terminated items) to catch conditional-selection bias.

- **PASS:** ≥3 primary anchors land within their brackets on BOTH conditional Knowledge AND conditional
  Instruction; no independent non-Qwen family has a catastrophic healthy miss; termination health passes.
- **FALSIFY:** ≥2 anchors from ≥2 non-Qwen lineages land below their lower bracket on the SAME axis by
  ≥10pp OR ≥2 rung-bands, the miss survives item-bootstrap CI (lower 95% bound below the bracket), and
  termination/parse health are normal.
- **LANE-INCOMPATIBLE:** poor natural close / high forced-close / abnormal leaked reasoning / family
  parser-template failure prevents a capability interpretation.
- **INCONCLUSIVE:** anything else (one bad miss, adjacent-rung noise, marginal termination).

## 7. Confound handling (pre-registered)
- **Chat-template:** pre-register exact rendered prompt bytes per family; official reasoning activation only.
- **Delimiter:** only literal-`</think>` families are primary (smoke-test enforced).
- **`<response>` wrapper (Granite):** after `</think>`, strip at most ONE balanced outer
  `<response>…</response>`; no other rewrite/repair. Apply uniformly.
- **Natural vs forced close:** track separately; C conditions on natural close + parseable final.
- **Greedy vs sampled:** keep greedy temp-0 (locked); use broad brackets, not sampled point targets.
- **Budget:** models needing >8192 think (e.g. DeepHermes) → sensitivity-only, not primary.
- **Hidden reasoning → IFBench:** score only the final response after `</think>` (except leaked-reasoning diagnostics).
- **Answer parser:** one deterministic extractor (last unambiguous option token), applied after
  final-channel normalization. No LLM judge.

## 8. Harness work this requires (some via Codex, after the scorer hardening)
natural-vs-forced-close tracking in budget_forcing; `<response>`-wrapper strip + post-`</think>` final
isolation in scoring; the 6 health metrics in the run record; the bracket/audit analysis. The strict-gate
+ T/C/S decomposition (scorer hardening, in progress) is the foundation.

## 9. Constraints
No LLM judge; reproducibility/determinism (locked greedy lane); local-only; GPU available. The GO/launch
verdict already holds and is independent of this check.
