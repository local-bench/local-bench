# Off-family anchor validation — RESULTS + LOCKED VERDICT (local-bench, 2026-06-21)

Companion to `ANCHOR-VALIDATION-PREREG-2026-06-21.md`. Reproducible eval: `anchor_eval.py`
(self-verifying) → `anchor-validation-results.json`. Adjudicated with two independent GPT-5.5
red-teams: **oracle (GPT-5.5 Pro)** on the verdict, **codex (GPT-5.5 xhigh)** on the R1 recovery.
The GO/launch verdict is independent of this; this is the EXTERNAL-VALIDITY result.

## 1. Outcome (BLUF)
**Overall = INCONCLUSIVE / partial external validation.** Not PASS, not clean FALSIFY.

> Granite (the one fully-independent non-Qwen lineage) supports the claim that the axes measure
> general capability, not Qwen-family output patterns. The Llama-3.1 reasoning-distilled anchors
> (R1-Distill, Nemotron) expose an **Instruction-axis lane/bracket limitation** under capped-thinking
> — not a Qwen-family artifact.

| Axis | Verdict | Basis |
|---|---|---|
| Knowledge (MMLU-Pro) | Supportive / no-falsify, **not formal PASS** | Granite-8B + Nemotron in-bracket; Granite-2B small CI-surviving miss (−7.2pp, <10pp); R1 large miss (−35pp, lane-attributable) |
| Instruction (IFBench) | **INCONCLUSIVE** | Granite in-bracket; R1 + Nemotron miss big (−34, −25pp). Numeric FALSIFY fires but lineage-independence + IFEval-bracket provenance are compromised |
| Overall | **INCONCLUSIVE / partial external validation** | Not Qwen-pattern-only (Granite + Nemotron-Knowledge place correctly), but not broadly validated across off-family reasoning-distilled models |

## 2. Validated data (strict S / termination T / conditional C, %)
Scored through localbench's own `_score_response_detail` + `aggregate`. The re-score **reproduces
every known-good number exactly** (Nemotron's printed run; the §6.1 locked Qwen strict rungs) and
asserts 400/294 item coverage per model.

```
                KNOWLEDGE (MMLU-Pro, n=400)     INSTRUCTION (IFBench, n=294)
model         S     T     C   S_CI95            S     T     C    S_CI95
qwen-0.8b    24.8  48.2  51.3                  12.9  48.3  26.8
qwen-2b      51.5  70.2  73.3                  19.0  57.1  33.3
qwen-4b      73.0  93.0  78.5                  43.2  66.0  65.5
qwen-9b      78.5  94.2  83.3                  57.1  78.9  72.4
granite-2b   17.5  99.5  17.6 [14.0,21.2]      14.3 100.0  14.3 [10.5,18.4]
granite-8b   34.5  99.5  34.7 [30.0,39.2]      18.0  99.7  18.1 [13.6,22.5]
nemotron-4b  52.5  94.8  55.4 [47.8,57.5]      17.7  97.6  18.1 [13.3,22.4]
r1-8b        38.0  91.0  41.8 [33.2,42.8]       9.5  97.6   9.8 [ 6.5,12.9]
```

## 3. Recovery + data integrity (no GPU re-runs; both red-teams signed off)
Two deterministic transcript artifacts were recovered losslessly on CPU:
- **Granite `\boxed{}`** answers — recovered by the committed additive MCQ extractor (proven
  unchanged on legacy cases). Granite-8B mmlu extraction failures 146 → 98 (the rest are genuine).
- **R1-Distill byte-level BPE** transcripts (`Ġ`=space, `Ċ`=newline) — recovered by `decode_bpe`
  (GPT-2 byte inverse), then re-scored. **R1 mmlu 7.5% → 38.0%** (343 → 77 extraction fails);
  **R1 IFBench 24.5% → 9.5%** (the corruption — no real whitespace — spuriously PASSED count/format
  constraints; decoding restores the same normal-text surface the clean models were scored on; the
  raw-checker flip was 59↑/14↓, 57/13 after the production cap gate).

**Codex (GPT-5.5 xhigh) red-team verdict: R1 recovery is TRUSTWORTHY.** Independently confirmed
`decode_bpe` equals `tokenizers.decoders.ByteLevel` on all 693 non-empty R1 items, **0 chars
dropped**; the 2 `U+FFFD` are invalid byte sequences in R1's RAW output, both outside answer regions
(do not affect any score). No scorer bug advantages/disadvantages R1; R1 misses on **both** S and C.
Codex's must-fixes are folded into `anchor_eval.py` as locked evidence: the ByteLevel decoder audit,
exact 400/294 coverage asserts, and the corrected `U+FFFD` accounting. Decode-then-rescore is ruled
**admissible** for the validity verdict (token generation unchanged; deterministic CPU decode;
recovery script + audit are part of the locked evidence) — a GPU re-run is not methodologically
required, though it may be cleaner optics for a polished public leaderboard row.

## 4. Two structural confounds + the metric decision
1. **Termination asymmetry.** Every non-Qwen anchor terminates near-perfectly (mmlu 91–99.5%,
   ifbench 97.6–100%); the Qwen ladder terminates poorly, especially on Instruction (T 48/57/66/79%).
   Low Qwen-T depresses Qwen strict-S but INFLATES Qwen conditional-C (it is scored only on the
   easier items it finishes). A difficulty audit confirms the anchors show ~no selection bias
   (Qwen-4b accuracy on each anchor's terminated vs non-terminated mmlu subset is ~73% either way;
   non-terminated subsets are 2–36 items).
2. **Bracket provenance.** Knowledge brackets came from card MMLU; **Instruction brackets came from
   card IFEval** — easier than IFBench (58 new OOD constraints) and measured under each model's
   native SAMPLED full-CoT recipe, not our greedy temp-0 lane. The pre-reg flagged this. So the
   Instruction brackets for the reasoning anchors are likely set too high.

**Metric decision (oracle-endorsed deviation from the pre-reg's literal text):** report **strict S**
as the primary placement metric. The pre-reg named health-gated conditional C primary; post-hoc, the
termination asymmetry makes C-vs-Qwen unfair to the high-terminating anchors (`S = T × C`;
conditioning on "terminated" makes the comparison depend on each model's own missingness). The
oracle confirmed strict-S is the right **lane** metric, while noting it is *not* a pure latent-
capability estimate. This deviation is documented, not silent, and **both metrics agree on every
anchor's verdict** (R1/Nemotron miss far below bracket on S AND C).

## 5. Bracket placement + 4-status adjudication
Placement vs the §6.1 strict Qwen-rung brackets, with bootstrap 95% CIs; health gate (T ≥ min
Qwen-T − 10pp) PASSES for all anchors:

```
anchor       axis         bracket  S     miss   CI-survives
granite-2b   Knowledge    25-52   17.5  -7.2pp  yes (but <10pp)
granite-2b   Instruction  13-43   14.3  IN      -
granite-8b   Knowledge    25-73   34.5  IN      -
granite-8b   Instruction  19-57   18.0  -1.0pp  no (CI overlaps -> IN)
nemotron-4b  Knowledge    52-73   52.5  IN      -
nemotron-4b  Instruction  43-57   17.7  -25.5pp yes
r1-8b        Knowledge    73-78   38.0  -35.0pp yes
r1-8b        Instruction  43-57    9.5  -33.7pp yes
```

**Knowledge:** 2/4 in-bracket (Granite-8B, Nemotron), Granite-2B a sub-threshold miss, R1 a large
lane-attributable miss (its card's 73 MMLU-Pro is sampled full-CoT; under greedy capped-thinking it
scores 38, terminating fine at 91% — a decoding-regime penalty). 3/4-in-bracket is not achieved →
**no formal PASS, but no falsification.**

**Instruction — the FALSIFY question:** the numeric trigger fires (Nemotron −25.5, R1 −33.7, both
CI-surviving, both health-OK). It resolves to **INCONCLUSIVE, not FALSIFY**, on two grounds the
oracle endorsed:
- **Lineage.** R1-Distill-Llama-8B and Nemotron-Nano-4B are **both Llama-3.1-based reasoning-
  distilled/post-trained** — one correlated failure class, not two independent non-Qwen lineages.
  The criterion's intent (avoid declaring a general non-Qwen failure from one correlated cluster)
  is therefore not met. This is **pre-registration-consistent, not retroactive**: the pre-reg §1
  already stated it "validates against Qwen-family architecture/output-tokenizer specificity, NOT
  against all possible Qwen- or DeepSeek-influenced post-training styles … Granite is the cleanest
  claim-supporting anchor (Apache, non-Qwen, non-distilled)." Granite (the independent lineage)
  lands in-bracket on **both** axes.
- **Bracket provenance.** IFEval-derived brackets are weak priors for strict IFBench under a
  different decoding lane (§4.2).

(Had the pre-reg pre-committed R1 and Nemotron as two independent lineages, the honest record would
be Instruction = FALSIFY-with-explanation. It did not — it pre-flagged them as the correlated
post-training-style cluster.)

## 6. Lane limitation (documented, not "unfair")
The capped-thinking lane is intentionally fixed for reproducibility. It may **understate** models
whose reported capabilities depend on native sampled/full-CoT decoding, long reasoning traces, or
model-specific answer formats — most visibly the Llama-derived reasoning-distilled anchors on
IFBench. The lane is *fair* as a deterministic, identical, user-facing product; it is not an
estimate of each model's best native recipe. local-bench reports **S/T/C** and is a **strict lane
benchmark, not a universal native-capability ranking.**

**Leaderboard-safe claim (oracle wording):** "The Qwen3.5 ladder and IBM Granite anchors indicate
the axes are not merely detecting Qwen-family output patterns. Off-family validation is partial:
Llama-derived reasoning-distilled anchors substantially underperform bracket expectations on IFBench
under this lane. Scores are lane performance, not native sampled-CoT or model-card capability."

## 7. Pre-registered follow-ups (oracle-flagged; none change the locked verdict)
Done here: difficulty audit; bracket placement with item-bootstrap CIs; decoder/coverage audit.
Open (CPU, sharpen honesty): IFBench failure taxonomy for R1/Nemotron (transcript evidence for the
greedy-lane mechanism — partially shown via the 59 spurious constraint-passes); cluster-bootstrap by
constraint family; uncertainty on the Qwen bracket endpoints; IFBench selection audit.
Open (GPU, scope expansion toward a cleaner PASS — **user decision, not auto-run**): local-lane
IFEval on the four anchors (separates "IFEval-bracket provenance" from "IFBench uniquely harder");
a no-think / answer-only ablation on IFBench (tests reasoning-trace interference); and **≥2 more
genuinely-independent non-Qwen families** (non-Llama, non-Qwen + a plain Llama-Instruct non-reasoning
baseline) — currently Granite is the only clean independent anchor.

## 8. Locked evidence / reproduce
- `anchor_eval.py` (self-verifying) → `anchor-validation-results.json`. Run:
  `cli/.venv/Scripts/python.exe docs/foundations/methodology-lock/anchor_eval.py`.
- Run transcripts: `cli/runs/anchor-{granite-3.3-2b,granite-3.3-8b,nemotron-nano-4b,r1-distill-llama-8b}.json`,
  Qwen ladder `cli/runs/campaign-qwen3.5-{0.8b,2b,4b,9b}.json`.
- Red-team transcripts (oracle GPT-5.5 Pro + codex GPT-5.5 xhigh) retained in the session record.
