**VERDICT:** **SOUND-WITH-FIXES** (The core "Geekbench for Local AI" wedge is highly defensible, but your current suite is bloated, your scorer is likely broken, and you are flying blind on quant-degradation until you run a properly powered paired test).

Here are the forced decisions to lock the methodology.

---

### 1. THE WEDGE: Is quant-degradation a sound foundation?
**Recommendation:** Yes, but it is a *feature*, not the whole product. The product stands on "verified local quality vs. frontier" alone. If the wedge is thin, pivot the marketing, not the product.
**Reasoning:** Quantization degradation is heavily model-size dependent and architecture-dependent. A 27B model has enough parameter redundancy to absorb Q4 compression; an 8B model often does not. Furthermore, "Reasoning ON" masks quant degradation because models use extra test-time compute (longer CoT) to recover from precision loss. 
**What would change my mind:** If the minimal experiment (detailed below) shows < 2% degradation across *all* sizes (8B to 32B) at Q4_K_M, the wedge is dead.

### 2. SATURATION/FLOORING: Keep / Reweight / Drop?
**Recommendation:** **DROP** Coding and Agentic. **SWAP** Math items. Do **NOT** build difficulty-stratification.
**Reasoning:** 
*   *Coding (LCB Output-Pred)* is saturated because it's a reading comprehension test, not a coding test. 
*   *Agentic (BFCL-AST)* is saturated because AST checkers only verify syntax (did it output a JSON with the right keys?), not semantic correctness. 
*   *Math* is floored because OlymMATH-hard is designed to break frontier models; locals will always score 0. 
*   Difficulty-stratification is a massive over-engineering trap for a solo dev. 
**Fix:** Swap Math to a uniform sample of MATH-500 (levels 1-5). Drop Coding and Agentic entirely for v1.1. 

### 3. SCOPE: Is a 6-axis suite right for launch?
**Recommendation:** No. It is severely over-engineered. Ship a **3-axis suite**.
**Reasoning:** You have burned a week on bugs for 6 axes. Every axis you add multiplies harness maintenance, scorer brittleness, and user compute time. Local users will not wait 4 hours for a benchmark to run. 
**What would change my mind:** If you had a team of 3 engineers to maintain the programmatic checkers and execution sandboxes. You don't.

### 4. LANE: Is reasoning-ON-only the right single lane?
**Recommendation:** Yes, keep it Reasoning-ON-only.
**Reasoning:** You must benchmark how users actually run the models. With the release of DeepSeek-R1 and QwQ, the local meta is entirely reasoning-focused. An answer-only lane is a nice-to-have that doubles the compute burden and complicates the leaderboard. 
**What would change my mind:** If users overwhelmingly demand standard instruction-following speeds, but your wedge is *quality*, not speed.

### 5. VALIDITY TRAPS WE'RE STILL MISSING (See Top 5 Risks below)
**Recommendation:** Your biggest immediate threat is scorer brittleness masquerading as model performance (both false positives and false negatives). 

### 6. COMPOSITE: How to weight and report?
**Recommendation:** **Equal-weight geometric mean**, normalized to a frozen baseline model (e.g., Llama-3-8B-Instruct-FP16 = 100). Single composite for the leaderboard, radar chart for the profile.
**Reasoning:** Arithmetic means are vulnerable to extreme outliers in a single axis. Geometric means penalize models that completely fail one axis (which is what users care about—no glaring weaknesses). 
**Fix the code mess:** Delete the weights from `suite.json` and the web build. The Python runtime `DOMAIN_WEIGHTS` is the sole source of truth. The web build must fetch this dynamically or read it from the results payload.

---

### TOP 5 RISKS YOU ARE NOT SEEING (Ranked)

**1. The "93.8% MMLU-Pro" Impossibility (False Positives)**
*   *The Risk:* You noted Qwen3.6-27B hit 93.8% on MMLU-Pro after the truncation fix. **This is statistically impossible.** Frontier SOTA (GPT-4o/Claude 3.5) is ~75-80% on MMLU-Pro. Your regex/scorer is broken and is granting false positives (e.g., if the model outputs "The answer is not A, but B", your regex might just trigger on the first capital letter it sees).
*   *The Test:* Manually inspect 50 "correct" MMLU-Pro logs from the 27B run. I guarantee you will find the scorer marking incorrect answers as correct.

**2. Scorer Brittleness Masquerading as "Flooring" (False Negatives)**
*   *The Risk:* Your Math axis is floored (~0). While OlymMATH is hard, ~0 is suspicious. Local models often fail to output the exact `\boxed{}` format required by programmatic checkers, especially when reasoning is ON (they ramble).
*   *The Test:* Run a weak model (e.g., Llama-3-8B) on 20 Math items. Manually read the outputs. Did it get the math right but fail the regex? If yes, your scorer is the floor, not the model.

**3. The 8192 Token Trap**
*   *The Risk:* 8192 is not a "graceful" budget for modern reasoning models. DeepSeek-R1-32B routinely thinks for 16k-24k tokens. If you cap at 8192, you will truncate the exact models that local users are most excited about right now.
*   *The Test:* Run DeepSeek-R1-Distill-Qwen-32B on 50 hard Math items. Measure the token distribution. If >10% hit the 8192 cap, you must raise the budget to 16k or 32k.

**4. KV Cache Mismatch with Reality**
*   *The Risk:* You mandate KV cache f16. No local user runs 64k context on a 32GB card with f16 KV cache—it eats ~10GB of VRAM just for the cache, forcing them to use smaller quants for the model weights. You are benchmarking a configuration nobody uses.
*   *The Test:* Calculate VRAM usage for a 32B model at Q4_K_M + 64k context + f16 KV cache. It will OOM or heavily swap on a 5090. You must allow Q8 KV cache.

**5. Contamination Blindness**
*   *The Risk:* MMLU-Pro is heavily contaminated in recent local models. You are measuring memorization, not knowledge.
*   *The Test:* Compare performance on MMLU-Pro vs. a private/newer dataset (e.g., GPQA-Diamond). If the delta is massive, flag the model on the leaderboard for suspected contamination.

---

### THE WEDGE: Explicit Go/No-Go & Minimal Experiment

**Go/No-Go Rule:** If the Q4_K_M vs FP16 delta is **< 2.0%** on the 8B model, the quant-degradation wedge is dead. Pivot marketing to "Verified Local Quality vs Frontier."

**Minimal Clean Experiment Design:**
*   **Models:** Llama-3.1-8B-Instruct (to test the vulnerable small-size) AND Qwen-2.5-32B-Instruct (to test the robust mid-size).
*   **Quants:** FP16 (Baseline) vs. Q4_K_M. (Drop Q6, Q3, Q2 for this test. Q4_K_M is the community standard. If it doesn't degrade there, the wedge narrative fails).
*   **Item Count (n):** **1,000 items** (Pool Knowledge and IFBench).
    *   *Math:* To detect a 3% drop (MDE) from a 70% baseline with 80% power (alpha=0.05), you need ~1,000 items. Your previous n=40 could only detect a 17.5% drop, which is why your results were non-monotonic noise.
*   **Statistical Test:** **McNemar's Test** for paired nominal data. Do *not* use independent T-tests. You are running the exact same prompts on both quants; you must measure how many items flipped from Correct->Incorrect vs Incorrect->Correct.

---

### WHAT YOU MUST CUT TO SHIP FASTER

If you have to ship in 2 weeks, **CUT:**
1.  **Coding Axis (LCB):** Saturated, execution-free is useless, execution is unsafe. Cut it.
2.  **Agentic Axis (BFCL):** AST checkers are gamed. Cut it.
3.  **Long-Context Axis (RULER-32k):** Takes exponentially longer to run, will cause users to abort the CLI. Park it for v2.0.
4.  **Difficulty-Stratification:** Delete the design docs. It's a distraction.

**Your Defensible Launch Suite (v1.1):**
1.  **Knowledge:** MMLU-Pro (400 items) — *Fix your regex scorer first!*
2.  **Instruction-Following:** IFBench (Constraint checkers).
3.  **Math:** MATH-500 (Uniform sample of 150 items, levels 1-5).

This 3-axis suite is fast, safe to run locally, highly discriminative, and actually achievable for a solo builder in two weeks. Lock it in.