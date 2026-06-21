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

### 6.1 Locked per-anchor brackets (pre-run, 2026-06-21)
Set from published model-card benchmarks as BROAD ordinal bands (most cards lack MMLU-Pro → Knowledge
extrapolated from MMLU; reasoning-model cards use SAMPLING + full reasoning, so our greedy-temp-0
8192-budget lane will likely score LOWER, esp. R1/Nemotron). Qwen rung refs (our STRICT scores):
Knowledge MMLU-Pro 0.8B 24.8 / 2B 51.5 / 4B 73.0 / 9B 78.5; Instruction IFBench 0.8B 12.9 / 2B 19.0 /
4B 43.2 / 9B 57.1.

| Anchor | card evidence | Knowledge bracket | Instruction bracket |
|---|---|---|---|
| Granite-3.3-2B | MMLU 55.9, IFEval 65.8 | Qwen 0.8B–2B (~25–52%) | Qwen 0.8B–4B (~13–43%) |
| Granite-3.3-8B | MMLU 65.5, IFEval 74.8 | Qwen 0.8B–4B, exp ~2B (~35–55%) | Qwen 2B–9B (~19–57%) |
| Nemotron-Nano-4B | GPQA-D 55.1, MATH500 96.2, IFEval 82.6 (reasoning-on, sampled) | Qwen 2B–4B (~51–73%) | Qwen 4B–9B (~43–57%) |
| R1-Distill-Llama-8B | **MMLU-Pro 73.0 reported**, IFEval 80.0 | Qwen 4B–9B (~65–78%) | Qwen 4B–9B (~43–57%) |

Ordinal prediction (R1-Distill most reliable = only reported MMLU-Pro):
**R1-Distill-Llama-8B ≳ Nemotron-4B ≈ Granite-8B > Granite-2B.** Dominant risk = lane-stress
(greedy temp-0 + 8192 think budget vs the anchors' sampled/longer-CoT recipes) → elevated cap-hit for
R1/Nemotron expected; that triggers the conditional-metric + health-gate path or LANE-INCOMPATIBLE,
NOT a Qwen-bias conclusion.

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

## Execution log + run recipe (2026-06-21)
Harness: scorer hardening `5048f49` (strict gate + T/C/S decomposition) + off-family prompt-rendering
generalization `b7ee79d` (renders each model's OWN chat template via HF `apply_chat_template`;
`--hf-model-id` + `--reasoning-activation {qwen3,granite,nemotron,r1}`; Granite `<response>`-strip). 639
cli tests green; Qwen3 path byte-identical.

**Prereqs (Windows client ↔ WSL vLLM server):**
- Serve via `~/serve_anchor.sh <hf-id> <served-name>` (= serve_localbench.sh MINUS `--reasoning-parser
  qwen3` — that parser needs `</think>` as SPECIAL tokens, which the anchors lack; budget-forcing stops on
  the literal `</think>` string regardless). Prefix `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`.
- cli venv needs `transformers` + `jinja2` (installed; jinja2 isn't auto-pulled — should be added to
  cli/pyproject.toml).
- Tokenizers must be in the WINDOWS HF cache (the weights live in WSL's cache for vLLM, but the Windows
  client loads the tokenizer to render the prompt). Download copy-mode:
  `HF_HUB_DISABLE_SYMLINKS=1 python -c "from huggingface_hub import snapshot_download; snapshot_download(
  repo, allow_patterns=['*.json','*.txt','*.model','*.jinja','tokenizer*','special_tokens*'])"` (Windows
  lacks symlink privilege without Developer Mode).
- SMOKE VERIFIED end-to-end on Granite-8B: err=0, term=100%, `<response>`-strip extracts + scores.

**Per-model runs** (serve → run full sets MMLU-Pro 400 + IFBench 294, `--lane capped-thinking --provider
local --concurrency 8` → `runs/anchor-<model>.json`; kill; next):
| model | --hf-model-id | --reasoning-activation | served-name | status |
|---|---|---|---|---|
| Granite-8B | ibm-granite/granite-3.3-8b-instruct | granite | granite-3.3-8b | RUNNING |
| Granite-2B | ibm-granite/granite-3.3-2b-instruct | granite | granite-3.3-2b | queued |
| R1-Distill-8B | deepseek-ai/DeepSeek-R1-Distill-Llama-8B | r1 | r1-distill-llama-8b | queued |
| Nemotron-4B | nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1 | nemotron | nemotron-nano-4b | queued |

**Eval:** custom 4-status script (§6) — anchors (native strict T/C/S from the new scorer) vs the Qwen
ladder (strict via gate-at-read = `correct AND finish_reason != "length"`); conditional accuracy primary
(health-gated), brackets §6.1.

## OUTCOME (2026-06-21) — full results in ANCHOR-VALIDATION-RESULTS-2026-06-21.md
**Verdict: INCONCLUSIVE / partial external validation** (not PASS, not clean FALSIFY). Granite (the
one independent non-Qwen lineage) supports general-capability measurement; the Llama-3.1 reasoning-
distilled anchors (R1-Distill, Nemotron) expose an Instruction-axis lane/bracket limitation under
capped-thinking. Knowledge = supportive / no-falsify (not formal PASS: Granite-8B + Nemotron
in-bracket, Granite-2B −7pp <10pp, R1 −35pp lane-attributable). Instruction = INCONCLUSIVE: the
numeric FALSIFY trigger fires (Nemotron −25.5, R1 −33.7, CI-surviving) BUT R1+Nemotron are one
Llama-reasoning-distill cluster, not two independent lineages (pre-registration-consistent per §1),
and the IFEval-derived brackets are weak priors for strict IFBench. **Metric deviation:** strict-S
reported as primary (the cross-family termination asymmetry — Qwen 48–79% T vs anchors ~100% —
confounds the §4 health-gated-C placement); both metrics agree on every anchor's verdict. Adjudicated
by oracle (GPT-5.5 Pro) + codex (GPT-5.5 xhigh) red-teams. R1 recovered losslessly from byte-BPE
transcripts (decoder audited == tokenizers ByteLevel on all items); no GPU re-runs. Open follow-ups
(esp. ≥2 more independent non-Qwen families, local-lane IFEval, no-think ablation) listed in §7 of
the results doc — GPU expansion is a user decision, not auto-run.
