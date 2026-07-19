# local-bench-ai

CLI benchmark runner for [local-bench.ai](https://local-bench.ai) — a community quality
leaderboard for local AI setups. It benchmarks GGUF models served by llama.cpp (or any
OpenAI-compatible endpoint), scores them on the five-axis Local Intelligence Index
(Agentic, Knowledge, Instruction-Following, execution-verified Coding, Math — with
call-formatting and long-context tracked as unweighted diagnostics), and packs signed,
reproducible result bundles that publish to the board immediately on submission.

## Quickstart

```bash
pip install "local-bench-ai[hf]"   # Python 3.11+

# 1. Fetch the complete benchmark suite (hash-verified)
localbench fetch-suite --site https://local-bench.ai \
  --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms

# 2. Cache the tokenizer/chat template for offline identity
localbench cache-tokenizer <hf-model-id>

# 3. Run the full suite; explicitly consent to restricted model-generated code execution
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

# 5. Submit — complete runs publish to the board immediately, attributed to you
localbench submit run --run runs/my-bench
```

Full-suite execution requires the AppWorld harness (`localbench setup-agentic`) and Docker.
The agentic harness currently provisions its sandboxed appliance from a **Windows host with
managed WSL2** (`setup-agentic` fails fast elsewhere); Linux-native host support is tracked
as a roadmap item. The other axes run wherever llama.cpp and Docker do.
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
  sandbox with no host mounts; coding and agentic verdicts are carried as client-reported
  evidence and labeled as such on the board.
- Every number on the board links to a receipt with the full run manifest.
- Complete runs publish and rank immediately, attributed to the submitter; maintainers
  moderate post-hoc and can suppress rows that fail scrutiny.

Methodology: <https://local-bench.ai/methodology>
