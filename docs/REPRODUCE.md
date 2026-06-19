# Reproducing a local-bench run

local-bench is a **frozen, reproducible** suite: anyone can run suite-v1.2 against their own
endpoint and get scores comparable to ours (same items, same scorers, same lane). This is the
one-command path. Methodology: `docs/foundations/methodology-lock/METHODOLOGY-v1.2-LOCKED.md`.

## Prerequisites
- Python 3.11+; install the CLI: `pip install -e cli` (or `pipx install localbench` once published).
- A running **OpenAI-compatible** chat endpoint serving your model (llama.cpp `llama-server`, vLLM,
  Ollama, LM Studio, …).
- For the KLD quant-drift step only: a built llama.cpp **`llama-perplexity`** binary + the GGUF weights.

## 1. Run the task suite (one command)
```
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model   <model-name-the-server-reports> \
  --lane    capped-thinking \
  --tier    standard \
  --out     runs/my-run.json
```
This pulls the frozen item sets, drives your endpoint, server-scores every response, writes a manifest,
and saves the run JSON. `--bench` defaults to `all`; pass e.g. `--bench mmlu_pro,ifbench` for a subset.

**What makes it reproducible**
- **Fixed item sets**, pinned by sha256 in `suite/v1/suite.json` (+ `itemsets.lock.json`). Same suite
  version → same questions. `--max-items N` takes a **deterministic first-N slice** per bench, so two
  runs (e.g. a quant pair) see identical items.
- **Decoding is deterministic**: temperature 0. The composite is HEADLINE-only (Knowledge + Instruction;
  see METHODOLOGY §3) and every score carries a bootstrap CI.
- **The manifest records provenance**: model file hash, runtime + version, KV-cache quant, context length,
  sampling, lane, and the item-set hashes — so a run is self-describing.

**Serve the locked lane (METHODOLOGY §1).** Configure the *server* for the headline lane:
reasoning-ON, server reasoning-budget **8192**, `max_tokens` ceiling **16384**, **f16 KV** (no KV quant),
**≥64k** context, **≥12k tokens/slot**. The CLI `--max-tokens` can cap per-item for a bounded local
context window. Cross-lane scores never merge — keep `--lane capped-thinking` for headline comparability.

## 2. Compare two runs (e.g. a quant pair)
```
localbench compare runs/q8.json runs/q4.json --out cmp.json
```
Paired over identical items → repeatability CI, paired quant-delta, generalization CI, and the **weakest
headline axis** (METHODOLOGY §5). Deltas are reported "on suite-v1.2 items ± paired CI", never as a
universal percent.

## 3. KLD quant-drift (distribution drift, NOT a task score)
Replaces the ad-hoc shell script with a committed, tested tool. Two-pass llama-perplexity: the reference
dumps its logits once, each quant is scored against them.
```
localbench kld \
  --llama-perplexity ~/llama.cpp/build/bin/llama-perplexity \
  --reference   ~/models/gemma-4-12b-it-BF16.gguf \
  --quant Q8_0=~/models/gemma-4-12b-it-Q8_0.gguf \
  --quant Q4_K_M=~/models/gemma-4-12b-it-Q4_K_M.gguf \
  --quant Q3_K_M=~/models/gemma-4-12b-it-Q3_K_M.gguf \
  --calib       ~/kld/calib.txt \
  --model-label gemma-4-12b-it \
  --reference-label BF16 \
  --out         runs/gemma-kld.json
```
Emits a `localbench-kld-v1` drift record: per-quant median + q99 KLD + Same-top-p (+ optional **churn** if
you pass `--churn-reference run-bf16.json --churn-quant Q4_K_M=run-q4.json`). The calib corpus is hashed
into the record. For big models where FP16 won't fit, use the **Q8 proxy** as the reference and set
`--reference-label "Q8 (proxy)"` (validated near-lossless). KLD is **drift from full precision — lower is
more faithful, NOT a task score** (METHODOLOGY §6); always show it beside accuracy + churn + VRAM + speed.

## 4. Coding-exec axis (opt-in, sandboxed code EXECUTION)
The credible coding axis (red-team verdict: judge-free proxies measure code *reasoning*, not *generation*).
The user's model generates code; it runs against BigCodeBench-Hard's unit tests inside a hardened, network-
isolated Docker container **on the user's machine** (we never execute it on our infra). Opt-in.
```
localbench code \
  --endpoint http://localhost:8080/v1 \
  --model   <model-name> \
  --image   bigcodebench/bigcodebench-evaluate@sha256:<digest> \   # digest-pin before a ranked run
  --tier    standard \
  --out     runs/my-coding-exec.json
```
Prereqs: Docker installed (Docker Desktop on Mac/Windows gives a VM boundary; on Linux add `--runtime runsc`
for gVisor). The container is locked down by default (`--network none`, `--read-only`, `--cap-drop ALL`,
`--security-opt no-new-privileges`, swap off, bounded tmpfs, `--init`, non-root, bounded output) — see
`docs/foundations/methodology-lock/CODING-EXEC-MODULE-SPEC.md`. Each task runs in its own subprocess; the
trusted runner computes pass/fail from exit codes (never self-reported). Coding-exec is a **separate exec
lane** with its own score; it is a *candidate* until a discrimination run earns it a headline slot.

## 5. Build the site data
```
<cli-venv>/python web/build_data.py
```
Reads `web/data_sources.json` (+ `web/model_catalog.json`) → `web/public/data/{index,models,runs}.json`.
Composite weights come from the single registry (`localbench.scoring.axes`); no weights are hardcoded in
the web build.

## Notes
- **Anchors** (frontier "vs GPT-5.5/Opus/Gemini" runs) are $-gated and run separately; they are not part
  of the local repro.
- **Suite identity** is the sha256-hashed `suite/v1/suite.json`. Scores are comparable only within a suite
  version.
