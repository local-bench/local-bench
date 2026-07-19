# Reproducing a local-bench run

Updated 2026-07-19. The active headline is **Local Intelligence Index** (`index-v4.2 | 25/22.5/22.5/22.5/7.5`):

```text
0.25 Agentic + 0.225 Knowledge + 0.225 Instruction + 0.225 Coding + 0.075 Math
```

The five-axis ranked profile is Agentic / Knowledge / Instruction / Coding / Math. Agentic is AppWorld task-goal completion on the fixed 96-task subset (data key `tool_use`); BFCL v3 multi-turn base is a frozen, unweighted diagnostic. BigCodeBench-Hard execution is the ranked Coding axis. The LiveCodeBench proxy (`lcb`) is a legacy diagnostic only and is never pooled into the ranked index. Season-1 rows keep their `index-v3.0 | 40/15/15/10/15/5` scale as history.

## Prerequisites

- Python 3.11+ and the CLI: `pip install "local-bench-ai[hf]==0.2.3"` (or from a source checkout: `pip install -e cli`)
- An OpenAI-compatible chat endpoint for the `run --endpoint` path, or a GGUF model plus llama.cpp for the CLI-launched `bench` path
- A 32768-token configured context window for publishable `bounded-final-v2` runs
- Exactly one model identity flag: `--hf-model-id <hf-model-id>` when you know the exact tokenizer repo, or `--gguf-repo-only` when no exact HF tokenizer repo is available
- A pre-cached tokenizer when using `--hf-model-id`; `cache-tokenizer` verifies the tokenizer can load offline before the run starts

## 1. Fetch and inspect the public suite

```bash
pip install "local-bench-ai[hf]==0.2.3"

localbench fetch-suite \
  --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 \
  --accept-suite-terms

localbench suite inspect --suite suite-v1-full-exec-6axis-v1
```

`fetch-suite` verifies the public suite manifest and prints the cached suite
directory. Keep that path for `submit run --suite-dir`.

## 2. Cache tokenizer and choose identity

Use this path when you know the exact Hugging Face tokenizer repo for the served model:

```bash
localbench cache-tokenizer <hf-model-id>
```

Then pass `--hf-model-id <hf-model-id>` to `run` or `bench`. If no exact HF tokenizer repo is available, skip `cache-tokenizer` and pass `--gguf-repo-only` instead. Publishable `bounded-final-v2` runs fail fast unless exactly one of those identity flags is present.

## 3. Preferred path: bring your own OpenAI-compatible endpoint

```bash
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model <served-model-name> \
  --hf-model-id <hf-model-id> \
  --ctx-len-configured 32768 \
  --lane bounded-final-v2 \
  --profile auto \
  --tier standard \
  --publishable \
  --sampler-seed 1234 \
  --out runs/my-run.json
```

The endpoint must actually be served with at least a 32768-token context window. `--ctx-len-configured 32768` records that configured context for the publishable run.

## 4. Optional GGUF path: launch llama.cpp with `bench`

```bash
localbench bench \
  --runtime llama.cpp \
  --model-file <model.gguf> \
  --model-id <model-slug> \
  --ctx 32768 \
  --lane bounded-final-v2 \
  --profile auto \
  --hf-model-id <hf-model-id> \
  --tier standard \
  --seed 1234 \
  --out runs/my-bench
```

Use the same identity rule here: replace `--hf-model-id <hf-model-id>` with `--gguf-repo-only` only when no exact HF tokenizer repo is available. `bench` uses `--ctx 32768` to launch the server with the required context window.

## 5. Submit a finished run

```bash
localbench submit run \
  --run runs/my-run.json \
  --suite-dir <cached-suite-dir-shown-by-fetch-suite>
```

If you used the optional `bench` path, submit the `--out` path from that command instead.

On first use, `submit run` creates `~/.localbench/submitter_ed25519.pem`; that
public key is the leaderboard identity. The maintainer reviews every submission
before anything publishes.

## 6. Coding axis

The ranked Coding axis is BigCodeBench-Hard with verifier-side execution. The submitted bundle carries code artifacts; self-reported execution verdicts are displayed only as diagnostics and never rank.

`lcb`, the old LiveCodeBench output-prediction proxy, remains legacy diagnostic data only and is never pooled into any ranked index (index-v3.0 or index-v4.x).

## 7. Build board and site data

```bash
localbench board --no-check-parity
python web/build_data.py
```

The board and web build derive weights from the registry. Ranked rows require all current headline axes; partial rows still display measured axes but are not rank-comparable.

## 8. Compare runs

```bash
localbench compare runs/q8.json runs/q4.json --out cmp.json
```

Comparisons are meaningful only within the same suite, scorecard, lane, and module coverage. Report paired deltas and confidence intervals rather than treating a small point gap as a universal ranking.
