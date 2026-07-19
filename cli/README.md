# local-bench-ai

CLI benchmark runner for [local-bench.ai](https://local-bench.ai) — a community quality
leaderboard for local AI setups. It benchmarks GGUF models served by llama.cpp (or any
OpenAI-compatible endpoint), scores them on the six-axis Local Intelligence Index
(Agentic, Knowledge, Instruction-Following, Tool calling, execution-verified Coding, Math),
and packs signed, reproducible result bundles you can submit for maintainer review.

## Quickstart

```bash
pip install "local-bench-ai[hf]"   # Python 3.11+

# 1. Fetch the complete six-axis suite (hash-verified)
localbench fetch-suite --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms

# 2. Cache the tokenizer/chat template for offline identity
localbench cache-tokenizer <hf-model-id>

# 3. Run all six axes; explicitly consent to restricted model-generated code execution
localbench bench <catalog-model-or-hf-repo> \
  --llama-server-path <path-to-llama-server> \
  --allow-untrusted-code

# 4. Advanced managed-harness path
localbench bench \
  --runtime llama.cpp --server-bin <path-to-llama-server> \
  --model-file <model.gguf> --model-id <model-slug> \
  --hf-model-id <hf-model-id> \
  --suite suite-v1-full-exec-6axis-v1 --bench all \
  --wsl-venv-python <managed-wsl-python> \
  --appworld-root <managed-appworld-root> \
  --lane bounded-final-v2 --profile auto --tier standard \
  --allow-untrusted-code \
  --ctx 32768 --seed 1234 --out runs/my-bench

# 5. Submit for maintainer review (nothing auto-publishes)
localbench submit run --run runs/my-bench
```

Full six-axis execution requires the AppWorld harness (`localbench setup-agentic`) and Docker.
`--allow-untrusted-code` acknowledges the warning that model-generated code executes in a
restricted container. Before model download, the CLI actively verifies its non-root,
network-disabled, read-only, capability-free, seccomp-filtered, resource-bounded sandbox; missing
consent or an unenforceable control fails the coding axis closed. Existing result bundles with
pending coding artifacts can be completed with `localbench grade-coding --allow-untrusted-code`.
Safetensors/vLLM execution is a separate maintainer-operated lane documented in
[`docs/benchmark-build/vllm-maintainer-runbook.md`](../docs/benchmark-build/vllm-maintainer-runbook.md);
it does not change the public llama.cpp/GGUF path.

The site's [submit page](https://local-bench.ai/submit) generates these commands for your
exact model and runtime, including the full identity flag set for bring-your-own-server
runs. Publishable bounded-final-v2 runs require a 32k server context.

## What makes rows trustworthy

- Suites are hash-pinned releases; sampler settings are pinned (greedy, seeded).
- Coding is BigCodeBench-Hard, executed locally in a network-disabled, digest-pinned Docker
  sandbox with no host mounts; coding and agentic verdicts are carried as client-reported evidence
  for review.
- Every number on the board links to a receipt with the full run manifest.
- Nothing ranks without maintainer review.

Methodology: <https://local-bench.ai/methodology>
