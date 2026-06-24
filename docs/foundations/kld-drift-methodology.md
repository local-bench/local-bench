# KLD quant-drift lane — methodology (oracle-informed)

Date: 2026-06-23. Source: GPT-5.5 Pro (oracle) consult `kld-drift-approach`, weighed
against our locked methodology (METHODOLOGY-v1.2-LOCKED.md). **KLD is a DIAGNOSTIC — never
folded into the headline composite.**

## Decisions

1. **Reference = Q8_0 PROXY**, labeled as proxy (not "lossless"). Do NOT block on a 54 GB
   BF16 download. Ordering across Q2→Q3→Q4 is stable (quant error dwarfs Q8 reference
   error); Q6-vs-Q8 is the most proxy-sensitive comparison; Q8 itself must be shown as
   "reference", not "0 drift = lossless".
   - *Optional proxy validation:* download BF16 for a SMALL slice (25–50k tok) only; keep
     the Q8 proxy if `median KL(BF16||Q8) < 10–20% of median KL(Q8||Q4)` AND
     `same-top-p(BF16,Q8) > ~99.5%`. Else use BF16 for published Qwen numbers or label
     "Q8-relative only".

2. **Corpus = build `localbench-kld-calib-v1`** (frozen + hashed), NOT wikitext-only.
   Wikitext-2 alone has weak construct validity for our reasoning/instruction benchmark.
   Mixture (~250–500k tokens min, ~1M ideal; ≥100k/slice if q99 is published):
   - **40% task-prompt slice** — frozen MMLU-Pro + IFBench prompt renderings (system/user
     formatting, answer instructions). Matches our input distribution.
   - **40% reference-completion slice** — Q8_0 (or BF16) teacher-forced continuations on a
     fixed prompt sample, incl. reasoning-style text + final answers. Measures drift on the
     model's own capped-thinking/answer distribution.
   - **20% generic prose slice** — wikitext-2-raw. Keeps continuity with llama.cpp/PPL
     convention; also the smoke-test slice.

3. **KLD type = task-conditional, TEACHER-FORCED** — generate fixed reference traces once,
   then score every quant on the SAME tokens/contexts. Do NOT use answer-token-only KLD
   (path-dependent: once a quant takes a different token path, positions stop comparing the
   same conditional distribution → mixes drift with trajectory divergence).

4. **Public drift stats = median KLD + q99 KLD + same-top-p + task churn** (paired vs Q8).
   - NOT mean KLD (heavy-tailed; a few pathological contexts dominate) — mean stays in JSON.
   - NOT "effective bits lost" (non-standard, architecture-dependent, gameable).
   - `same-top-p` (reads positively: "keeps the reference top token X% of the time") over
     raw token-flip; show flip = `100 − same-top-p` in a tooltip only.

5. **Run params:** context **2048–4096** (NOT 64k — unnecessary for weight-quant drift,
   bloats logits files/runtime), fixed `--ppl-stride`, deterministic chunking, **f16 KV**
   (match headline methodology; keep weight-quant vs KV-quant as separate experiments).

6. **Run INSIDE WSL** (native `llama-perplexity`); do not have Windows Python exec a Linux
   ELF (our original blocker). Record full provenance (manifest below).

7. **SMOKE GATE (mandatory):** `Q8 vs Q8` must give ≈0 KLD / ~100% same-top-p before the
   ladder. If not, STOP — it indicates path/corpus/tokenizer/base-logits/parser bug.

## Complementary diagnostics (already in our locked methodology)
- **Task churn** (central): paired vs Q8, decomposed right→wrong / wrong→right /
  correct-but-different-form / per-axis (Knowledge vs Instruction).
- **Compute & termination drift:** tokens-to-answer ratio vs Q8, answer-cap hit rate,
  termination rate, tok/s, effective VRAM.
- JS divergence / logit cosine / RMS prob-shift / ECE: expert JSON fields only, not primary.

## Provenance manifest (required per run)
`reference_type, reference_model_sha256, quant_model_sha256, llama_cpp_commit,
llama_perplexity_path, corpus_sha256, corpus_id, context, stride, ngl, flash_attn,
kv_cache_type, gpu_name, driver, cuda_version, base_logits_sha256, command_line,
parser_version`

## Coherence with the Q4 accuracy plateau
- **Corroborates:** KLD monotone Q2>Q3>Q4>Q6>Q8; biggest drop Q3→Q4 (matches the IFBench
  jump / accuracy knee); Q4 KLD still > Q6/Q8 but task score/churn/termination close →
  *"Q4 is the accuracy knee; Q6/Q8 buy distributional fidelity, not measured Core Text
  accuracy."*
- **Contradicts:** Q4 shows Q3-like drift on task-conditioned slices + high q99 + high churn
  while the composite is flat only via cancellation (right→wrong ≈ wrong→right) or MMLU-Pro
  saturation hiding IF failures → *"Q4 tied on composite but not behaviorally stable; prefer
  Q6 for repeatability/exact phrasing."*
- Most likely: KLD keeps improving Q4→Q6→Q8 while composite is flat — this does NOT
  contradict the plateau; it is the "accuracy masks drift" story. Do NOT claim "reasoning
  recovered the drift" without a paired-flip analysis.

## Go-forward (P6, after the gemma ladder)
1. Unblock in WSL (corpus prep + native `llama-perplexity`).
2. Build + hash `localbench-kld-calib-v1` (40/40/20 mixture above).
3. Q8-vs-Q8 smoke (≈0 KLD / ~100% same-top-p).
4. Run Q2/Q3/Q4/Q6 vs Q8_0 proxy; show Q8 as "reference".
5. (Optional) BF16 small-slice proxy validation.
6. Publish median + q99 + same-top-p + churn + runtime.
7. Frame: "Q4 = accuracy knee; drift keeps falling above Q4; KLD is a fidelity diagnostic,
   not a task score."

Full oracle transcript: oracle session `kld-drift-approach` (browser, gpt-5.5-pro, 2026-06-23).
