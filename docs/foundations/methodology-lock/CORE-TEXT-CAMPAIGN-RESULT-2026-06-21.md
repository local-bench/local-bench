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
> ⚠️ **SUPERSEDED (2026-06-21):** this headline used the **legacy (pre-strict-gate) IFBench**. The
> official **STRICT** composite (the only scorer now; re-emitted into the campaign run JSONs) is
> `0.8B 14.2 → 2B 32.3 → 4B 56.4 → 9B 66.5` — still monotonic, STRONG GO holds. The site shows the
> strict composite. See §STRICT RE-SCORE.

## STRICT RE-SCORE — official numbers (2026-06-21, oracle-endorsed)

Inspection of all 62 of 9B's IFBench cap-hits found they are **non-termination / degenerate loops** at
the full 8192-token answer budget (median 25.9k chars), NOT truncated valid answers; 13 still scored
correct by matching required tokens mid-ramble. Per GPT-5.5 Pro oracle (session `ifbench-cap-methodolog`)
+ my analysis: **do NOT raise the cap, do NOT change decoding**; instead **strict-score** any answer-pass
`finish_reason=length` as INCORRECT and report a 3-way decomposition. CPU re-score of existing
transcripts (no GPU). **GO HOLDS — STRONG GO on both axes.** Identity: `strict = termination × conditional`
(conditional = instruction-following *when the model completes*). Script: `%TEMP%/analyze_campaign_strict.py`.

**Knowledge — MMLU-Pro (n=400), STRICT** (barely changed — few false positives):
| model | legacy | **strict** | termination | conditional | strict 95% CI |
|---|---|---|---|---|---|
| 0.8B | 24.8% | 24.8% | 48.2% | 51.3% | [20.8, 29.0] |
| 2B | 52.2% | 51.5% | 70.2% | 73.3% | [46.8, 56.5] |
| 4B | 73.8% | 73.0% | 93.0% | 78.5% | [68.8, 77.2] |
| 9B | 79.2% | 78.5% | 94.2% | 83.3% | [74.2, 82.5] |

Strict spread 9B−0.8B **+53.7pp [+48.8, +59.0]** → STRONG GO.

**Instruction — IFBench (n=294), STRICT** (where the false positives were):
| model | legacy | **strict** | termination | conditional | strict 95% CI |
|---|---|---|---|---|---|
| 0.8B | 20.1% | 12.9% | 48.3% | 26.8% | [9.2, 17.0] |
| 2B | 29.3% | 19.0% | 57.1% | 33.3% | [14.6, 23.5] |
| 4B | 49.3% | 43.2% | 66.0% | 65.5% | [37.4, 49.0] |
| 9B | 61.6% | 57.1% | 78.9% | 72.4% | [51.7, 62.6] |

Strict spread 9B−0.8B **+44.2pp [+37.8, +50.7]** (WIDER than legacy +41.5pp) → STRONG GO. Decomposition:
0.8B can't follow *or* terminate (cond 26.8%); 9B follows well when it completes (cond 72.4%) but runs
away on 21% of items (termination 78.9%).

**STRICT Local Intelligence Index (composite, OFFICIAL):** `0.8B 14.2 → 2B 32.3 → 4B 56.4 → 9B 66.5`
— chance-corrected mean of the two strict axes (knowledge 0.5 / instruction 0.5). Supersedes the
legacy `17.8 → 69.1` headline (which used the pre-strict-gate IFBench). Monotonic, ~14–24-pt steps,
STRONG GO unchanged. Re-emitted into `cli/runs/campaign-qwen3.5-*.json` by `reemit_campaign_strict.py`
(strict_handoff_manifest.json carries the per-model expected numbers for the site integrity gate).

**Site method note:** *Outputs that hit the answer-token cap are counted incorrect — this prevents
non-terminating generations from getting credit for matching required tokens inside a runaway response.*
Display per model×axis: strict accuracy (headline), termination rate, conditional accuracy.

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

## Caveats / open items
1–2. **RESOLVED by the STRICT RE-SCORE above (2026-06-21).** The cap-hits were NON-TERMINATION
   (degenerate loops at the full answer budget), not truncated valid answers — raising the budget would
   not have helped. Strict scoring (non-terminating → incorrect) removes the ~13–33 false-positives per
   run, the decomposition reports termination explicitly, and the strict absolutes above are official.
   GO unchanged (STRONG GO both axes).
3. **`localbench.probe` is unusable on these runs** ("label must be anchor or local"): `campaign-labels.json`
   lacks the anchor/local `kind` field the probe expects. The pre-registered `analyze_campaign.py` is the
   actual decision tool and worked. Fix the probe's label schema separately (secondary artifact).
4. **Scope:** a same-family ladder proves the axes detect SCALE within Qwen3.5, NOT ecosystem-wide rank.
   Per pre-reg, add 1–2 OFF-FAMILY anchors at similar sizes before claiming general validity.

## Next
Wire this ladder as the FIRST real ranked `capped-thinking` data on the site (it was an intentional empty
catalog awaiting exactly this) → the Local Intelligence Index goes live. Then the KLD/drift column + the
two re-score fixes above.
