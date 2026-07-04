# Scorer fit-for-purpose validation — 2026-06-16

*Gate for #54: be CERTAIN the suite is fit-for-purpose before any local re-run. This closes the
SCORER half of that gate. Content (knowledge keys) + the reasoning lane are the other two halves (below).*

## Headline (answers Michael's "no way a 27B is near frontier")

He was right. The "27B ≈ frontier" result was a **scoring artifact**, not a real tie. On the
math axis the local models' entire "signal" was **false positives**, and once removed the axis
shows the large gap you'd expect.

**The smoking gun (from the actual run data):** every local model's "correct" olympiad-math item
was a non-answer credited by accident:
- **Truncation FPs** — the model hit the token cap mid-derivation (`finish_reason=length`), never
  produced a final answer, and the scorer's *last-number-in-the-text* fallback grabbed a stray
  scratch number that happened to match. 7/7 of Qwen-27B's "correct" math items were this. 4/6 of
  Gemma-12B's were too.
- **math_verify over-acceptance** — the loose equivalence check credited numerically-different
  boxed answers: `\boxed{2}` vs gold `2√2−1` (=1.83), and `[-1,1]` (closed) vs gold `(-1,1)` (open).
  This was Gemma's other 2.

## Fix (committed `29fb89e`, branch `suite/v1-quant-wedge`, cli/ only)

1. **math_symbolic `_equivalent`** now does **strict local parse/equivalence FIRST**; `math_verify`
   is only a fallback when the local parser can't represent a side. Kills the over-acceptances.
2. **Bare last-number fallback suppressed on `finish_reason=="length"`** — a truncated output's
   trailing number is not an answer. A genuine `\boxed{}`/marked answer still counts even when
   truncated. `finish_reason` is threaded `_scoring._score_response → verify_math`.
3. **MCQ bold fallback** (`mcq.py`): a bold letter now only counts if it **ends** the response
   ("…the answer is **C**"); a bold letter mid-prose ("weighing **G** here") is reasoning, not an
   answer. End-of-sentence bold preserved.

Red-green tests for all three; **full cli suite 496 passed**.

## Measured impact (re-scoring the stored runs — no re-run needed)

| Model | Math before → after | Note |
|---|---|---|
| Qwen3.6-27B Q4 | 5.9% → **0.0%** | all 7 were `finish=length` |
| Qwen3.6-27B Q8 | 5.0% → **0.0%** | |
| Qwen3.6-27B Q6 | 8.4% → **0.8%** | |
| Qwen3.6-27B Q3 | 5.9% → **0.8%** | |
| Qwen3.6-27B Q2 | 4.2% → **0.0%** | |
| Gemma-12B Q4 | 5.0% → **0.0%** | incl. the 2 over-acceptances (052, 070) |
| **GPT-5.5 (frontier)** | 40.0% → **40.0%** | unchanged — genuine boxed answers |
| **Gemini 3.1 (frontier)** | 50.0% → **40.0%** | −1: one real truncation FP removed |

**Fixed math axis ≈ 40% frontier vs ≈ 0% local — a ~40-point gap.** That is the discrimination the
fake tie was hiding. MCQ: only local `finish=length` bold FPs removed (supergpqa-022/023/003/035);
**all three frontier MCQ runs unchanged**; zero `finish=stop` flips, so no genuine answers were lost.

## Disposition of every red-team finding

| # | Finding | Verdict | Action |
|---|---|---|---|
| 1 | math truncation + over-acceptance FPs | **REAL, critical** | **FIXED** (`29fb89e`) |
| 4 | MCQ bold-anywhere FP | **REAL, minor** | **FIXED** (`29fb89e`) |
| — | BFCL JSON booleans deflated frontier | REAL | already fixed (`0e67ede`) |
| 2 | IFBench `?!` interrobang | **NOT a bug** | faithful AI2 port — the `count:punctuation` fixture *requires* all six marks **plus** an interrobang; "fixing" it makes the FAIL fixture pass. Leave as-is. |
| 3 | IFBench word-position counts punctuation | **NOT a bug** | deliberate `punctuation_tokens` port; "fixing" diverges from official IFBench. Leave as-is. |
| 5 | chance-correction fixed 0.1 vs per-item 1/n | real, ~0.5pp | **DEFER** — collides with the live `site-overhaul` scoring-authority refactor's byte-identity gate. Do it there, or after it lands. |
| 6 | LCB quoting / RULER wrappers / BFCL fences | theoretical | #56. Deflation (false-NEGATIVE) class — only *widens* the frontier lead, so it doesn't change the conclusion. Do before the re-run. |

## The other two halves of #54 (still open — bigger, gated on you)

The scorers are now sound. Two fit-for-purpose problems remain before a trustworthy re-run:

1. **Knowledge-axis CONTENT (#53).** Independent of scorers: ~36% of the SuperGPQA items have bad
   answer keys (both frontier anchors agree on a non-gold answer), which compresses the top of the
   knowledge axis. You chose **Replace SuperGPQA → MMLU-Pro** (MIT, expert-cleaned). This is a build
   (download, fixed stratified item set, wire as a bench, validate keys), not a scorer tweak.
2. **The reasoning LANE.** The locals were run **answer-only** (and still over-reasoned into the cap,
   which is *why* they truncated). You decided **reasoning-for-all (capped-thinking)**. That requires
   re-running the locals with thinking enabled and a calibrated cap — i.e. GPU + a methodology pass on
   per-lane token budgets.

**Bottom line:** the suite mis-measured because of one critical scorer bug (now fixed) + bad knowledge
keys + a lane mismatch. The scorer half is done and proven. The re-run should NOT happen until the
knowledge swap + lane are also settled.
