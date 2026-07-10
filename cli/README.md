# local-bench-ai

CLI benchmark runner for [local-bench.ai](https://local-bench.ai) — a community quality
leaderboard for local AI setups. It benchmarks GGUF models served by llama.cpp (or any
OpenAI-compatible endpoint), scores them on the six-axis Local Intelligence Index
(Agentic, Knowledge, Instruction-Following, Tool calling, execution-verified Coding, Math),
and packs signed, reproducible result bundles you can submit for maintainer review.

## Quickstart

```bash
pip install "local-bench-ai[hf]"   # Python 3.11+

# 1. Fetch the static suite used by the public path below (hash-verified)
localbench fetch-suite --site https://local-bench.ai \
  --suite suite-v1-static-exec-5axis-v1 --accept-suite-terms

# 2. Cache the tokenizer/chat template for offline identity
localbench cache-tokenizer <hf-model-id>

# 3. Public path today: run the five non-agentic axes (measured/static, not full-index eligible)
localbench bench <catalog-model-or-hf-repo> --static-only \
  --llama-server-path <path-to-llama-server>

# 4. Managed-harness path: fetch the full suite, then launch the pinned server
localbench fetch-suite --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms

localbench bench \
  --runtime llama.cpp --server-bin <path-to-llama-server> \
  --model-file <model.gguf> --model-id <model-slug> \
  --hf-model-id <hf-model-id> \
  --suite suite-v1-full-exec-6axis-v1 --bench all \
  --wsl-venv-python <managed-wsl-python> \
  --appworld-root <managed-appworld-root> \
  --lane bounded-final-v2 --profile auto --tier standard \
  --ctx 32768 --seed 1234 --out runs/my-bench

# 5. Submit for maintainer review (nothing auto-publishes)
localbench submit run --run runs/my-bench
```

Full six-axis execution currently requires managed AppWorld configuration. Until the managed
runtime is public, use one-shot `--static-only` to run the other five axes without agentic setup.
Safetensors/vLLM execution is a separate maintainer-operated lane documented in
[`docs/benchmark-build/vllm-maintainer-runbook.md`](../docs/benchmark-build/vllm-maintainer-runbook.md);
it does not change the public llama.cpp/GGUF path.

The site's [submit page](https://local-bench.ai/submit) generates these commands for your
exact model and runtime, including the full identity flag set for bring-your-own-server
runs. Publishable bounded-final-v2 runs require a 32k server context.

## What makes rows trustworthy

- Suites are hash-pinned releases; sampler settings are pinned (greedy, seeded).
- Coding is BigCodeBench-Hard, re-executed by the maintainer's sandbox verifier before it
  can rank; community agentic results are labeled self-reported.
- Every number on the board links to a receipt with the full run manifest.
- Nothing ranks without maintainer review.

Methodology: <https://local-bench.ai/methodology>
