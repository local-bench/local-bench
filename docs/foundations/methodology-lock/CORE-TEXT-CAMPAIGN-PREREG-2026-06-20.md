# Core Text discrimination campaign — PRE-REGISTERED decision rule (2026-06-20)

Registered BEFORE running, so the keep/kill is not post-hoc. Endorsed by the GPT-5.5 Pro oracle
(session `localbench-campaign-design`). Question: do the headline axes — **Knowledge (MMLU-Pro)**
and **Instruction (IFBench)** — separate local models of different sizes on the locked
reasoning-on `capped-thinking` lane (8192 budget, two-pass budget forcing, greedy temp 0)?

## Design (fixed)
- **Panel:** Qwen3.5 same-family ladder **0.8B, 2B, 4B, 9B** (controls architecture / training /
  tokenizer; isolates scale). All local vLLM, zero spend.
- **Item sets:** FULL standard sets — MMLU-Pro 400, IFBench 294 (no first-N slice; a 100-item
  slice is too noisy (±10–14pp) and order-biased for a keep/kill — oracle).
- **Metric:** RAW accuracy, answer-pass truncation counted as incorrect (option A). Uniform budget
  forcing kept (a fair shared operating point; if it helps weak models, surviving separation is
  MORE convincing). No per-model tuning / caps / post-hoc exceptions.
- **Cap-hit rate:** reported prominently per model+bench, NOT down-weighted. Annotation bands:
  10–17% = cap-limited; >20% = high output-contract failure; >30% = valid but interpretation less clean.
- **Stats:** PAIRED item-bootstrap 95% CI (same item set across models), for each adjacent delta
  (2B−0.8B, 4B−2B, 9B−4B) and the full local-range spread (9B−0.8B). Per axis, separately.

## GO threshold (an axis separates) — ALL of:
1. 9B beats 0.8B by **>= 10 pp** (point estimate).
2. Paired-bootstrap 95% CI lower bound for **9B − 0.8B > 0** (preferably >= 3–5 pp).
3. Ladder mostly monotone (ideal 0.8B<2B<4B<9B; a single adjacent inversion/tie < ~2pp OK if 9B
   clearly top and 0.8B clearly bottom).
4. >= 2 of the 3 adjacent gaps positive by point estimate.
5. NOT explained by one model melting down via extreme cap-hit behavior.
- **Strong GO:** point spread >= 12 pp AND CI lower bound >= 5 pp on BOTH axes.

## KILL / demote (an axis is flat for launch) — ANY of:
1. Full-set 9B − 0.8B spread < 5 pp, or
2. Non-monotone with the best model not reliably the largest, or
3. 95% CI for the local-range spread compatible with near-zero AND no coherent size trend.
- Ambiguous (neither GO nor KILL) = launch failure; do not promote to the headline yet.

## Decision tree
| Result | Decision |
|---|---|
| MMLU-Pro GO + IFBench GO | Launchable Local Intelligence Index |
| MMLU-Pro GO + IFBench flat/ambiguous | Keep Knowledge, demote/reweight Instruction |
| MMLU-Pro flat + IFBench GO | Do not launch combined; investigate Knowledge |
| Both flat/ambiguous | Ship only quant-drift / conformance tooling for now |

## After a GO (next validation, not part of this run)
One same-family ladder answers "do the axes detect scale within a family?", NOT "does the index
rank the broader ecosystem?" After a clean GO, add 1–2 OFF-FAMILY anchor models at similar sizes
to confirm the index is not merely detecting Qwen-family scaling. Do not claim ecosystem-wide
validity from this campaign alone.

## Analysis artifacts
- `python -m localbench.probe --runs runs/campaign-*.json --labels runs/campaign-labels.json
  --suite-dir suite/v1 --out runs/campaign-discrimination.json` (per-axis verdict + CI-bound spread).
- Supplementary paired-bootstrap table (per-model accuracy + 95% CI + cap-hit rate; adjacent-delta
  and 9B−0.8B paired CIs; monotonicity) for the pre-registered GO/KILL evaluation above.
