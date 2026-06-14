# Leg B — quant wedge: pipeline validated, ladder blocked by local serving (2026-06-15)

**Outcome of the autonomous run:** the full benchmark pipeline is proven end-to-end on real local
hardware, and a complete single-setup **scorecard** for Qwen3.6-27B Q4_K_M is delivered (below). The
multi-rung quant **ladder** (q4 vs q6 vs q8) is **blocked by a local-serving constraint, not by the
pipeline** — diagnosis + the unblock path are in §3. This needs a Michael decision before proceeding.

## 1. What works (validated this run)
Everything except loading >1 quant of one base model:
- **Thinking suppression** for a reasoning model — `reasoning_effort=none` forwarded to the local
  provider (new feature, committed `db878c1`). Without it Qwen3.6 burns its whole budget on hidden
  reasoning; with it, clean answer-only output.
- **Bounded-context generation** — `--max-tokens` run-level cap (new feature, committed `b6b5198`),
  needed because LM Studio splits the loaded context across `--parallel` slots (the non-obvious root
  cause of a wall of HTTP-400 "context exceeded" errors; `--parallel 2` at -c 8192 = 4096/slot).
- **The run + paired-delta `compare`** — validated; produces signed per-axis deltas with bootstrap CIs.
- 467 tests green throughout.

## 2. The delivered result — Qwen3.6-27B Q4_K_M single-setup scorecard
- **Setup:** lmstudio-community **Q4_K_M** (15.4 GB GGUF) · RTX 5090 (32 GB) · LM Studio (llama.cpp).
- **Operating point:** answer-only, thinking suppressed · -c 8192, 2 parallel slots · gen cap 2048 ·
  temperature 0 · N=80/bench (amo=39, the full set) · suite-v1, identical frozen items.

| axis | bench | chance-corrected | malformed (n_extraction_failures) |
|---|---|---|---|
| Knowledge | supergpqa | **44.4%** | 11 / 80  (13.8%) |
| Instruction | ifbench | **55.0%** | 0 / 80 |
| Agentic | bfcl | **88.8%** | 0 / 80 |
| Math | olymmath_hard | 7.5% | 0 / 80 |
| Math | amo | 2.6% | 0 / 39 |
| **Composite** | | **39.7%** | |

- **Reliability:** **0 infra errors** across all 359 items. Malformed output occurs only on knowledge
  (13.8%) — the model's MCQ answer didn't parse 11×; this is exactly the kind of signal the quant
  ladder is meant to track (low bits break *format* before *capability*).
- **Speed (5090, manifest-qualified):** 107.8 completion tok/s · 56 min wall for 359 items · 445k total
  tokens. (Per Michael's note, completion time is recorded per item + per run.)
- **Math floors** under answer-only (olympiad math needs reasoning, which we suppressed for a clean fast
  signal). Math here is a format/robustness probe, not a capability axis — see caveat in §4.
- Raw run: `runs/quant-q36-q4_k_m.json` (gitignored measured artifact).

## 3. Why the multi-quant ladder is blocked (and how to unblock)
Goal: load q4 / q6 / q8 of the **same base model** with the **same operating point**, swapping only the
bit-width. On this machine, via the available tooling, that is currently unreachable:

| approach | result |
|---|---|
| LM Studio `lms load "qwen/qwen3.6-27b"` | loads only the model's *selectedVariant* (Q4_K_M) |
| `lms load "...@q6_k"` / `@q8_0` | rejected — "model not found" |
| `lms load "F:\...\Qwen3.6-27B-Q6_K.gguf"` (abs path) | rejected — treated as a key, not a file |
| `lms load "lmstudio-community/.../Q6_K.gguf"` (indexed id) | rejected |
| `lms get "...@q6_k" -y` to re-select | "already downloaded"; selectedVariant stays q4 |
| only non-interactive escape | `lms get ... --select` (an arrow-key TUI — can't script, needs the GUI) |
| bundled `llama-server.exe` standalone | exits 53 (missing runtime DLLs / env outside LM Studio) |
| bartowski single-file Q6_K_L (distinct key, loads) | loads, but its embedded template ignores the reasoning controls → **full thinking** (60s+/item) → a different operating point than the suppressed Q4 → comparison confounded, not a fair wedge |

Net: LM Studio's catalog **groups same-repo quants under one key and only loads the default**, and the
bundled llama-server won't run detached. So no two same-base quants with matched suppression are
loadable tonight.

**Unblock paths (pick one — needs Michael):**
1. **vLLM in WSL2** (already set up for qwen-bench) — load each GGUF in turn, set
   `chat_template_kwargs={"enable_thinking": false}` (vLLM honors this reliably) → clean same-source
   q4/q6/q8 ladder with matched suppression. Best science. ~3 rungs × ~1 h. *Caveat:* confirm the
   installed vLLM build supports the `qwen35` GGUF arch; 128k-context tiers won't fit a 27B on 32 GB
   (q8 ladder at -c 8192 is fine).
2. **LM Studio GUI** — Michael selects each variant via the model loader (the only thing that drives
   `--select`), then the pipeline runs unchanged.
3. **Direct per-quant HF downloads into distinct folders** — may dodge the catalog grouping so each
   gguf gets its own loadable key. Cheapest to try; uncertain.

The pipeline is 100% ready; only the multi-quant **serving** is gated.

## 4. Caveats / notes
- Math floors under answer-only (suppressed reasoning). For a math-capability signal, add a
  capped-thinking math lane later; for the quant *robustness* signal, answer-only is the right lane.
- Timing is 5090-specific (manifest-qualified), not portable.
- On-box quant ceiling is q8_0 (26.6 GB); fp16 (54 GB) needs a rented GPU.
- Scoring uses the pre-hardening bootstrap; the red-team's cluster-robust/equivalence-margin fixes are
  on a separate branch pending Michael's merge-scope decision (signal is robust to either).
