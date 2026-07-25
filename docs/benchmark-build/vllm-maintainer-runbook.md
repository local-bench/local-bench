# Maintainer serving lanes: vLLM and SGLang

This is a maintainer-operated path for immutable Hugging Face safetensors snapshots that cannot be
served by the public llama.cpp/GGUF path. It launches a pinned vLLM or SGLang installation inside WSL2 while
the Windows CLI runs the benchmark against WSL localhost forwarding. It is not an appliance or a
supported community provisioning flow.

## Prerequisites

- A named WSL2 distribution with NVIDIA GPU access.
- A WSL virtual environment containing the intended, pinned vLLM build. Keep that environment
  unchanged for the campaign. The server must report vLLM 0.24 or newer. Localbench records the
  exact server-reported package version, a dependency-lock digest from that virtual environment,
  the launcher SHA256, help-text digest, GPU, driver, and CUDA identity.
- For SGLang, a separate unchanged WSL virtual environment containing exactly SGLang 0.5.13
  (tag `v0.5.13`, commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`). The lane rejects
  every other package version. The official pinned references are the
  [server arguments](https://github.com/sgl-project/sglang/blob/v0.5.13/docs/advanced_features/server_arguments.md),
  [deterministic-inference guide](https://github.com/sgl-project/sglang/blob/v0.5.13/docs/advanced_features/deterministic_inference.md),
  and [HTTP endpoint source](https://github.com/sgl-project/sglang/blob/v0.5.13/python/sglang/srt/entrypoints/http_server.py).
  Localbench hashes every file recorded by the installed `sglang` distribution and requires that
  package-tree identity together with the matching version reported by `/server_info`.
- A model revision expressed as `hf://<namespace>/<repo>@<full-40-character-commit-sha>`. Branches,
  tags, `latest`, and file fragments are rejected. The Windows-side download is materialized without
  symlinks and every snapshot file is hashed into a deterministic snapshot identity.
- On Windows the agentic axis uses the managed appliance; do not pass `--wsl-venv-python` /
  `--appworld-root` (the lane rejects them). On Linux hosts supply the explicit managed AppWorld
  paths when the selected suite includes the agentic axis.
- A CUDA toolkit inside the WSL distribution (`nvcc` on PATH or `/usr/local/cuda`).
  GDN/DeltaNet kernels JIT-compile at runtime; driver libraries alone are not enough. The launch
  script exports `CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}` and prepends its `bin`.
- Precache the tokenizer/chat template before the first offline introspection:
  `uv run --project cli localbench cache-tokenizer <namespace>/<repo>`.

Do not run the rehearsal while another scheduled GPU workload owns the device.

## Determinism policies

The vLLM lane selects one of two named policies from the snapshot's architecture
(`text_config`-aware `layer_types` inspection):

- `vllm-batch-invariant-v1` — architectures vLLM supports under `VLLM_BATCH_INVARIANT=1`.
  Evidence: launch export, env allowlist, live `/proc` environ probe, and the affirmative
  batch-invariant kernel log line.
- `vllm-gdn-structural-single-slot-eager-v1` — GDN/linear-attention hybrids (e.g. Qwen3.6),
  which vLLM refuses to initialise batch-invariant. Claim: *empirically reproducible across
  clean process starts under structural single-slot execution on the recorded stack; not
  batch-invariant*. The lane pins `--enforce-eager`, `--gdn-prefill-backend triton`,
  `--attention-backend TRITON_ATTN`, `--linear-backend cutlass`, FlashInfer autotune and Mamba
  stochastic rounding off, `--jit-monitor-mode warn` (error mode is fatal on the first request:
  vLLM's warmup does not cover every shape — instead provenance requires ZERO JIT-during-inference
  events in the scored phase), zero multimodal limits (text-only lane;
  reclaims the vision-encoder profiling budget), plus `PYTHONHASHSEED=0`,
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`, the FLA_* precision pins, and per-start empty
  Triton/Inductor caches. This policy is version-allowlisted (exactly vLLM 0.25.1); any other
  version refuses to run.

Under either policy the two-start canary now runs a token-level matrix — rendered input lengths
128, 64, 65 (GDN chunk boundary), 8192, 16384, 26624, and near-`ctx`, each generating 64 tokens
with logprob token evidence — with within-lifetime repeats and a short A/B/A state-isolation
check. Start A qualifies and tears down; **start B must match start A token-for-token (and, for
GDN, select identical Triton autotune configurations from a cold cache) and then stays alive as
the scoring server.** One bounded relaunch retry is permitted for start B; the retry is recorded.
After the scored suite, post-score sentinel canaries must reproduce start B's pre-score outputs.

Migration note: 0.4.9 changes the vLLM server fingerprint/resume identity (the
`flash_attention` component is now the policy label). vLLM runs started under 0.4.8 cannot be
`--resume`d under 0.4.9.

## Required preflight

Run this checklist before the expensive suite. A dirty checkout makes the result non-publishable.
In particular, move or stash `scratchpad/`; merely leaving it untracked is dirty.

```powershell
git status --short
if ($LASTEXITCODE -ne 0 -or (git status --short)) { throw "clean git tree required" }
```

Run the two-start canary against the same immutable ref and environment, with a minimal item
count (the baked worker rejects `--max-items 0`; use `1`):

```powershell
uv run --project cli localbench bench `
  --runtime vllm `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --hf-model-id <namespace>/<repo> `
  --wsl-distro <distro-name> `
  --vllm-venv /absolute/wsl/path/to/vllm-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --max-items 1 --seed 1234 --out runs/<run-name>-preflight
```

Inspect `runs/<run-name>-preflight/localbench-run.json` and echo these values for the maintainer
record. Confirm them before continuing: execution profile
`generic_think_tags_8192_v1`; server-reported vLLM version at least 0.24 (exactly 0.25.1 for the
GDN policy); non-empty venv dependency-lock hash; matching tokenizer and applied-template hashes;
parsed weights/KV memory evidence; `determinism.policy_id` matching the model's architecture;
policy evidence (batch-invariant kernel line, or GDN resolved-backend affirmations + matching
autotune manifests); and `two_start_canary_passed: true` with the full canary matrix present.
Any missing value is a failed preflight, even if the server answered requests. Note the profile
enforces a context floor of 26624; pass `--ctx 32768` for 32k-class snapshots.

## Run

```powershell
uv run --project cli localbench bench `
  --runtime vllm `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --hf-model-id <namespace>/<repo> `
  --wsl-distro <distro-name> `
  --vllm-venv /absolute/wsl/path/to/vllm-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --seed 1234 --out runs/<run-name>
```

`--vllm-bin /absolute/wsl/path/to/vllm` may replace `--vllm-venv` when the executable is managed
directly. There are no machine-specific path defaults.

The immutable model ref automatically supplies `hf_model_id` and `hf_revision`; separate overrides
are accepted only when they match it. The lane resolves the model's real bounded-final profile and
refuses the known Qwen lane if it falls back to answer-only.

The lane binds only `127.0.0.1`, forces client concurrency and `--max-num-seqs` to one, applies
the selected determinism policy's env pins (batch-invariant: `VLLM_BATCH_INVARIANT=1`; GDN: the
structural-single-slot pin set above), keeps BF16 model/KV cache while following Qwen's published
float32 Mamba SSM-state dtype, pins the NVFP4 quantization loader, disables prefix caching and
chunked prefill, and prevents repository generation-config overrides. The default maximum model
length comes from the resolved 8192-class execution profile; use `--vllm-max-model-len` only as a
reviewed explicit override. GPU memory utilization remains 0.92. The snapshot's
`chat_template.jinja` is passed and verified through a tokenizer/template probe. Server startup is
given up to 30 minutes before readiness fails (large snapshots pay ~2 minutes of weight loading
over 9P plus first-start JIT).

## Completion checks

The command is complete only when the result records `runtime: vllm`, reports the requested model,
includes the requested repository and 40-character revision plus snapshot Merkle/per-file hashes,
includes the runtime/device/dependency-lock identity and non-null serve-log hash, records parsed
determinism and memory evidence, records the requested run seed, and records a clean teardown.
Each canary start must also produce certain, GPU-clean teardown evidence. Teardown refreshes the token-owned
process tree and verifies command-line/executable identity before signalling. A residual owned GPU
PID marks the result non-publishable; never recover with a process-name sweep. The CLI prints
`NOT PUBLISHABLE` with the exact blockers whenever any required evidence cannot be verified.

## SGLang 0.5.13 lane

SGLang has a documented batch-invariance mode; this lane uses its exact
`--enable-deterministic-inference` flag with the documented deterministic `triton` attention
backend. Temperature zero alone is insufficient according to the official guide. The lane also
sets server and client concurrency to one, disables the radix cache, overlap scheduling, and
pins chunked prefill at 2048 tokens and CUDA graph batch size to one, and uses
`--sampling-defaults openai` so model
generation defaults cannot silently change sampling.

Run the same clean-tree check above, then run the required two-start canary with zero benchmark
items:

```powershell
uv run --project cli localbench bench `
  --runtime sglang `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --wsl-distro <distro-name> `
  --sglang-venv /absolute/wsl/path/to/sglang-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --wsl-venv-python /absolute/wsl/path/to/appworld-python `
  --appworld-root /absolute/wsl/path/to/appworld-root `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --max-items 0 --seed 1234 --out runs/<run-name>-preflight
```

Before the scored run, inspect the preflight bundle and require all of the following: resolved
profile `generic_think_tags_8192_v1`; server-reported and environment package version `0.5.13`;
non-empty dependency-lock and Python-interpreter hashes; matching snapshot-covered template hash;
`server_reported_config.enable_deterministic_inference: true`; `attention_backend: triton`;
`max_running_requests: 1`; `max_total_num_tokens` at least the configured context; computed memory
fit true; and `two_start_canary_passed: true`. Any absent or mismatched fact is a failed preflight.

The scored command is identical except for the output directory and omission of `--max-items 0`:

```powershell
uv run --project cli localbench bench `
  --runtime sglang `
  --model-ref hf://<namespace>/<repo>@<full-40-character-commit-sha> `
  --model-id <model-slug> `
  --wsl-distro <distro-name> `
  --sglang-venv /absolute/wsl/path/to/sglang-venv `
  --suite suite-v1-full-exec-6axis-v1 --bench all `
  --wsl-venv-python /absolute/wsl/path/to/appworld-python `
  --appworld-root /absolute/wsl/path/to/appworld-root `
  --lane bounded-final-v2 --profile auto --tier standard `
  --determinism-canary --seed 1234 --out runs/<run-name>
```

`--sglang-python /absolute/wsl/path/to/python` may replace `--sglang-venv`. The default context is
the resolved 8192-class execution-profile requirement; `--sglang-max-model-len` is a reviewed
explicit override. The lane uses the snapshot's NVFP4/compressed-tensors configuration, BF16 model
and KV-cache data, 2048-token chunked prefill, and requests a 0.80 static-memory fraction. For the
Qwen3.6 target, SGLang's v0.5.13 VLM adjustment resolves that request to 0.7398125. The static fit
contains weights, KV, and hybrid/Mamba state pools; a separate non-static fit reserves activation
and CUDA-graph memory using the v0.5.13 heuristic. It then independently requires the live
`/server_info.max_total_num_tokens` capacity to cover the configured context. Template provenance
is earned only when locally rendering the pinned snapshot template/tokenizer produces exactly the
same token IDs as the server's `/v1/tokenize` response.

Completion requires `runtime: sglang`, exact package/tag/commit and dependency-lock identity,
requested repository plus 40-character revision and snapshot Merkle/per-file hashes, non-null serve
log hash, the server-reported resolved configuration above, and clean token-owned process-group
teardown. Both canary teardowns must also be certain and GPU-clean. Determinism provenance is scoped
to SGLang and records the requested run seed. The same PID start-time, interpreter identity,
descendant refresh, and no-name-sweep rules as the vLLM lane apply.
