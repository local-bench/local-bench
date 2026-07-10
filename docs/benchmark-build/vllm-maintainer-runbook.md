# vLLM maintainer serving lane

This is a maintainer-operated path for immutable Hugging Face safetensors snapshots that cannot be
served by the public llama.cpp/GGUF path. It launches a pinned vLLM installation inside WSL2 while
the Windows CLI runs the benchmark against WSL localhost forwarding. It is not an appliance or a
supported community provisioning flow.

## Prerequisites

- A named WSL2 distribution with NVIDIA GPU access.
- A WSL virtual environment containing the intended, pinned vLLM build. Keep that environment
  unchanged for the campaign; localbench records its executable SHA256, version output, help-text
  digest, GPU, driver, and CUDA identity.
- A model revision expressed as `hf://<namespace>/<repo>@<full-40-character-commit-sha>`. Branches,
  tags, `latest`, and file fragments are rejected. The Windows-side download is materialized without
  symlinks and every snapshot file is hashed into a deterministic snapshot identity.
- Explicit managed AppWorld paths when the selected suite includes the agentic axis.

Do not run the rehearsal while another scheduled GPU workload owns the device.

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
  --ctx 32768 --seed 1234 --out runs/<run-name>
```

`--vllm-bin /absolute/wsl/path/to/vllm` may replace `--vllm-venv` when the executable is managed
directly. There are no machine-specific path defaults.

The lane binds only `127.0.0.1`, forces client concurrency and `--max-num-seqs` to one, exports
`VLLM_BATCH_INVARIANT=1`, pins model/KV/state-cache dtypes and the NVFP4 quantization loader, disables prefix
caching and chunked prefill, and prevents repository generation-config overrides. The snapshot's
`chat_template.jinja` is passed explicitly.

## Completion checks

The command is complete only when the result records `runtime: vllm`, reports the requested model,
includes the snapshot Merkle hash and per-file hashes, includes the runtime/device identity and
serve-log hash, and records a clean teardown. Teardown targets only the WSL session leader and its
recorded descendants. A residual owned GPU PID marks the result non-publishable; never recover with
a process-name sweep.
