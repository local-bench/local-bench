# local-bench

Community quality leaderboard for local AI setups. The headline score is the **Local Intelligence Index v2.1**: a modular, repeatable benchmark suite weighted as 50% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, and 10% Coding.

The standard run stays practical for local hardware: MMLU-Pro, IFBench, TC-JSON v1, and the lightweight LiveCodeBench output-prediction coding proxy run through the normal HTTP path; AppWorld-C is the agentic lane. Heavier modules such as BigCodeBench-Hard, long-context, and math remain opt-in or diagnostic until their lanes are hardened.

## Layout

- `cli/` - Python benchmark runner, scoring registry, board builder, and submission client
- `suite/` - versioned suite definitions, item sets, prompts, and scorers
- `web/` - leaderboard site and static data projection
- `docs/` - reproduction notes, methodology history, licensing, and threat model

## Quickstart

```bash
pip install local-bench-ai   # installs the `localbench` command (Python 3.11+)

localbench fetch-suite \
  --site https://local-bench.ai \
  --suite suite-v1-text-code-agentic-5axis-v1 \
  --accept-suite-terms

# strongest provenance: the CLI launches the pinned llama.cpp server itself
localbench bench \
  --runtime llama.cpp --model-file <model.gguf> --model-id <model-slug> \
  --ctx 32768 --seed 1234 --out runs/my-bench

# or bring your own OpenAI-compatible server (LM Studio, ollama, vLLM, ...)
localbench run \
  --endpoint http://localhost:8080/v1 --model <name-your-server-reports> \
  --lane capped-thinking --tier standard \
  --publishable --sampler-seed 1234 --out runs/my-run.json

localbench submit run --run runs/my-run.json
# suite auto-resolved from your fetched cache; --suite-dir to override
```

Submissions are identified by an Ed25519 key generated on first submit — no
account, no email. Nothing publishes without maintainer review; see
https://local-bench.ai/submit for the full loop and what the trust labels mean.
Working from source instead: `pip install -e cli`.

## Status

Pre-launch methodology work (2026-06). Active scoring source of truth: `cli/src/localbench/scoring/axes.py` plus `cli/src/localbench/scoring/benchmark_registry.py`.
