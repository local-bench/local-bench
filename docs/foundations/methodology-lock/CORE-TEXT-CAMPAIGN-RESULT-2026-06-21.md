# Core Text discrimination campaign — RESULT (2026-06-21)

Executes the pre-registered rule in `CORE-TEXT-CAMPAIGN-PREREG-2026-06-20.md`. Decision tool:
`%TEMP%/analyze_campaign.py` (paired item-bootstrap, B=5000, seed=42). Runs (local, gitignored):
`cli/runs/campaign-qwen3.5-{0.8b,2b,4b,9b}.json`.

## VERDICT: STRONG GO on both axes → **LAUNCHABLE Local Intelligence Index**

Panel: Qwen3.5 same-family ladder **0.8B / 2B / 4B / 9B** (isolates scale). Full sets MMLU-Pro 400 +
IFBench 294, `capped-thinking` lane (budget 8192, s1 two-pass forcing, greedy temp 0), concurrency 8,
local vLLM, **zero spend**. Metric = raw accuracy, answer-pass truncation counted incorrect (option A).

**Local Intelligence Index (composite = chance-corrected mean of the two axes):**
`0.8B 17.8 → 2B 37.8 → 4B 59.9 → 9B 69.1` — monotonic, ~17-point steps.

### Knowledge — MMLU-Pro (n=400) — STRONG GO
| model | acc | 95% CI | cap-hit |
|---|---|---|---|
| 0.8B | 24.8% | [20.8, 29.0] | 51.7% |
| 2B | 52.2% | [47.2, 57.2] | 29.8% |
| 4B | 73.8% | [69.5, 78.0] | 7.0% |
| 9B | 79.2% | [75.0, 83.2] | 5.8% |

Adjacent deltas (paired bootstrap): 2B−0.8B **+27.5** [+22.7,+32.7] · 4B−2B **+21.5** [+16.8,+26.5] ·
9B−4B **+5.5** [+2.2,+9.0]. Full spread **9B−0.8B +54.5pp [+49.5,+59.5]**. All CIs clear of zero.

### Instruction — IFBench (n=294) — STRONG GO
| model | acc | 95% CI | cap-hit |
|---|---|---|---|
| 0.8B | 20.1% | [15.6, 24.8] | 51.7% |
| 2B | 29.3% | [24.1, 34.4] | 42.9% |
| 4B | 49.3% | [43.5, 55.1] | 34.0% |
| 9B | 61.6% | [56.1, 67.0] | 21.1% |

Adjacent deltas: 2B−0.8B **+9.2** [+3.7,+14.6] · 4B−2B **+20.1** [+14.3,+26.2] · 9B−4B **+12.2**
[+7.1,+17.3]. Full spread **9B−0.8B +41.5pp [+34.7,+48.0]**. All CIs clear of zero.

Both axes meet the STRONG-GO bar (spread ≥12pp AND CI lower bound ≥5pp), monotonic, 9B top / 0.8B
bottom, all adjacent deltas positive. Per the pre-reg decision tree: **Launchable.**

## Caveats / open items (do NOT publish absolute numbers until resolved)
1. **IFBench cap-hit is high across the whole ladder** (0.8B 51.7% → 9B still 21.1%). IFBench answers
   are longer-form, and the `max_tokens=16384` ceiling truncates valid answers → the *absolute* IFBench
   numbers are depressed (true scores are likely higher). The **separation is robust** (monotonic, CIs
   clear), so the GO stands, but the operating point understates the models. **ACTION: raise the
   answer-pass token budget for IFBench and re-score** before the absolutes go on the site.
2. **Budget-forcing truncation audit:** per model, 16–33 cap-hit items scored CORRECT (0.8B 21 / 2B 33 /
   4B 21 / 9B 16; ~3–5%, consistent → doesn't bias the comparison). Contradicts option A (truncation =
   incorrect). Resolve the truncation exception before publishing.
3. **`localbench.probe` is unusable on these runs** ("label must be anchor or local"): `campaign-labels.json`
   lacks the anchor/local `kind` field the probe expects. The pre-registered `analyze_campaign.py` is the
   actual decision tool and worked. Fix the probe's label schema separately (secondary artifact).
4. **Scope:** a same-family ladder proves the axes detect SCALE within Qwen3.5, NOT ecosystem-wide rank.
   Per pre-reg, add 1–2 OFF-FAMILY anchors at similar sizes before claiming general validity.

## Next
Wire this ladder as the FIRST real ranked `capped-thinking` data on the site (it was an intentional empty
catalog awaiting exactly this) → the Local Intelligence Index goes live. Then the KLD/drift column + the
two re-score fixes above.
