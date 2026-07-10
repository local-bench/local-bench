# vLLM maintainer serving lane

This is a maintainer-operated path for immutable Hugging Face safetensors snapshots that cannot be
served by the public llama.cpp/GGUF path. It launches a pinned vLLM installation inside WSL2 while
the Windows CLI runs the benchmark against WSL localhost forwarding. It is not an appliance or a
supported community provisioning flow.

## Prerequisites

- A named WSL2 distribution with NVIDIA GPU access.
- A WSL virtual environment containing the intended, pinned vLLM build. Keep that environment
  unchanged for the campaign. The server must report vLLM 0.24 or newer. Localbench records the
  exact server-reported package version, a dependency-lock digest from that virtual environment,
  the launcher SHA256, help-text digest, GPU, driver, and CUDA identity.
- A model revision expressed as `hf://<namespace>/<repo>@<full-40-character-commit-sha>`. Branches,
  tags, `latest`, and file fragments are rejected. The Windows-side download is materialized without
  symlinks and every snapshot file is hashed into a deterministic snapshot identity.
- Explicit managed AppWorld paths when the selected suite includes the agentic axis.

Do not run the rehearsal while another scheduled GPU workload owns the device.

## Required preflight

Run this checklist before the expensive suite. A dirty checkout makes the result non-publishable.
In particular, move or stash `scratchpad/`; merely leaving it untracked is dirty.

```powershell
git status --short
if ($LASTEXITCODE -ne 0 -or (git status --short)) { throw "clean git tree required" }
```

Run the two-start canary against the same immutable ref and environment, with zero benchmark items:

```powershell
uv run --project cli localbench bench `
  --runtime vllm `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --wsl-distro <distro-name> `
  --vllm-venv /absolute/wsl/path/to/vllm-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --wsl-venv-python /absolute/wsl/path/to/appworld-python `
  --appworld-root /absolute/wsl/path/to/appworld-root `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --max-items 0 --seed 1234 --out runs/<run-name>-preflight
```

Inspect `runs/<run-name>-preflight/localbench-run.json` and echo these values for the maintainer
record. Confirm them before continuing: execution profile
`generic_think_tags_8192_v1`; server-reported vLLM version at least 0.24; non-empty venv
dependency-lock hash; matching tokenizer and applied-template hashes; parsed weights/KV/CUDA-graph
memory allocations; deterministic-kernel log evidence; and `two_start_canary_passed: true`.
Any missing value is a failed preflight, even if the server answered requests.

## Run

```powershell
uv run --project cli localbench bench `
  --runtime vllm `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --wsl-distro <distro-name> `
  --vllm-venv /absolute/wsl/path/to/vllm-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --wsl-venv-python /absolute/wsl/path/to/appworld-python `
  --appworld-root /absolute/wsl/path/to/appworld-root `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --seed 1234 --out runs/<run-name>
```

`--vllm-bin /absolute/wsl/path/to/vllm` may replace `--vllm-venv` when the executable is managed
directly. There are no machine-specific path defaults.

The immutable model ref automatically supplies `hf_model_id` and `hf_revision`; separate overrides
are accepted only when they match it. The lane resolves the model's real bounded-final profile and
refuses the known Qwen lane if it falls back to answer-only.

The lane binds only `127.0.0.1`, forces client concurrency and `--max-num-seqs` to one, exports
`VLLM_BATCH_INVARIANT=1`, keeps BF16 model/KV cache while following Qwen's published float32 Mamba
SSM-state dtype, pins the NVFP4 quantization loader, disables prefix caching and chunked prefill, and
prevents repository generation-config overrides. The default maximum model length comes from the
resolved 8192-class execution profile; use `--vllm-max-model-len` only as a reviewed explicit
override. GPU memory utilization remains 0.92. The snapshot's `chat_template.jinja` is passed and
verified through a tokenizer/template probe.

## Completion checks

The command is complete only when the result records `runtime: vllm`, reports the requested model,
includes the requested repository and 40-character revision plus snapshot Merkle/per-file hashes,
includes the runtime/device/dependency-lock identity and non-null serve-log hash, records parsed
determinism and memory evidence, and records a clean teardown. Teardown refreshes the token-owned
process tree and verifies command-line/executable identity before signalling. A residual owned GPU
PID marks the result non-publishable; never recover with a process-name sweep. The CLI prints
`NOT PUBLISHABLE` with the exact blockers whenever any required evidence cannot be verified.
