# Reproducing a local-bench run

local-bench is a **frozen, reproducible** suite: anyone can run suite-v1.2 against their own
endpoint and get scores comparable to ours (same items, same scorers, same lane). Methodology:
`docs/foundations/methodology-lock/METHODOLOGY-v1.2-LOCKED.md`.

## Prerequisites
- Python 3.11+; install the CLI: `pip install -e cli` (or `pipx install localbench` once published).
- A running **OpenAI-compatible** chat endpoint serving your model (llama.cpp `llama-server`, vLLM,
  Ollama, LM Studio, …).
- For the KLD quant-drift step only: a built llama.cpp **`llama-perplexity`** binary + the GGUF weights.

## 1. Fetch the frozen suite
```
localbench fetch-suite \
  --suite core-text-v1 \
  --accept-suite-terms
```
This verifies the bundled Core Text v1 suite and caches it under your user cache. No `--source`
is required for a normal `pip`/`pipx` install.

## 2. Run the task suite
```
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model   <model-name-the-server-reports> \
  --lane    capped-thinking \
  --tier    standard \
  --out     runs/my-run.json
```
This drives your endpoint, server-scores every response, writes a manifest, and saves the run JSON.
`--bench` defaults to `all`; pass e.g. `--bench mmlu_pro,ifbench` for a subset.

**What makes it reproducible**
- **Fixed item sets**, pinned by sha256 in `suite/v1/suite.json` (+ `itemsets.lock.json`). Same suite
  version → same questions. `--max-items N` takes a **deterministic first-N slice** per bench, so two
  runs (e.g. a quant pair) see identical items.
- **Decoding is deterministic**: temperature 0. The **Local Intelligence Index** (`v1 · Core Text (Knowledge + Instruction)`) is HEADLINE-only, shows the Knowledge / Instruction profile beside the composite, and every score carries a bootstrap CI.
- **The manifest records provenance**: model file hash, runtime + version, KV-cache quant, context length,
  sampling, lane, and the item-set hashes — so a run is self-describing.

**Serve the locked lane (METHODOLOGY §1).** Configure the *server* for the headline lane:
reasoning-ON, server reasoning-budget **8192**, `max_tokens` ceiling **16384**, **f16 KV** (no KV quant),
**≥64k** context, **≥12k tokens/slot**. The CLI `--max-tokens` can cap per-item for a bounded local
context window. Cross-lane scores never merge — keep `--lane capped-thinking` for headline comparability.

## 3. Compare two runs (e.g. a quant pair)
```
localbench compare runs/q8.json runs/q4.json --out cmp.json
```
Paired over identical items → repeatability CI, paired quant-delta, generalization CI, and the **weakest
headline axis** (METHODOLOGY §5). Deltas are reported "on suite-v1.2 items ± paired CI", never as a
universal percent.

## 4. KLD quant-drift (distribution drift, NOT a task score)
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
`--reference-label "Q8 (proxy)"` — the Q8≈BF16 proxy was validated on Gemma-12B only, so report the number as
"drift vs Q8 proxy," NOT as a global "near-lossless" claim. KLD is **drift from full precision — lower is more
faithful, NOT a task score** (METHODOLOGY §6); always show it beside accuracy + churn + VRAM + speed.

## 5. Coding-exec axis (opt-in, sandboxed code EXECUTION)
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
Prereqs: Docker installed. A **fail-closed preflight** runs first: Mac/Windows pass on the Docker-Desktop VM
boundary; on Linux it auto-selects `--runtime runsc` (gVisor) when present, and **refuses to run** on rootful
bare-Linux Docker with neither gVisor nor rootless (install gVisor or use rootless Docker, or pass
`--allow-unsafe-sandbox` to override — not recommended). It also rejects runc below the CVE-2024-21626 floor.
The container is locked down by default (`--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt
no-new-privileges`, swap off, bounded tmpfs, `--init`, `--log-driver none`, nofile/fsize/core ulimits, non-root,
bounded output) — see `docs/foundations/methodology-lock/CODING-EXEC-MODULE-SPEC.md`. Each task runs in its own
subprocess; the trusted runner computes pass/fail from exit codes (never self-reported). Coding-exec is a
**separate exec lane** with its own score; it is a *candidate* until a discrimination run earns it a headline slot.
Math and Agentic follow the same candidate-axis rule. A full Overall intelligence tier is earned only after
candidate axes are validated and promoted.

## 6. Build the site data
```
<cli-venv>/python web/build_data.py
```
Reads `web/data_sources.json` (+ `web/model_catalog.json`) → `web/public/data/{index,models,runs}.json`.
Local Intelligence Index (`v1 · Core Text (Knowledge + Instruction)`) weights come from the single registry
(`localbench.scoring.axes`); no weights are hardcoded in the web build.

**Experimental Agentic column (separate, 0% Index weight).** `web/build_data.py` also runs the
agentic aggregation as a final, additive step that writes only `web/public/data/agentic.json` — it
reads the AppWorld-C funnel runs in `cli/runs/agentic/*.scored.run*.json`, averages each model's
`agentic_success_rate` across its runs, joins to the board slug, and the leaderboard renders it as a
preview column. It does **not** flow through the board/scorecard pipeline and is **never** folded into
the Index. Run it standalone with `<cli-venv>/python web/build_agentic.py`. New scored runs → re-run →
the column updates.

## Notes
- **Anchors** (frontier "vs GPT-5.5/Opus/Gemini" runs) are $-gated and run separately; they are not part
  of the local repro.
- **Suite identity** is the sha256-hashed `suite/v1/suite.json`. Scores are comparable only within a suite
  version.
