## Verdict

**Endorse the direction, but tighten the claim.** The canonical path should be `localbench bench` launching the serving process itself, not LM Studio. The current seam is already shaped for this: `localbench run` is endpoint-agnostic, the local provider is a passthrough to OpenAI-compatible llama.cpp/vLLM-style servers, and the current weakness is exactly that model/runtime fields are hand-typed while the run record is forced to `external-endpoint`.  

**Refinement:** make the orchestrator **artifact-first**, not “server auto-download first.” The canonical flow should be:

`resolve immutable model artifact → hash exact artifact/snapshot → launch pinned runtime with explicit argv/env → verify endpoint facts → run suite → preserve logs/evidence → tear down owned process tree`.

For the two lanes:

**llama.cpp / `llama-server` as GGUF primary is correct.** It matches the GGUF quant ecosystem, runs natively on Windows CUDA, exposes OpenAI-compatible chat completions, supports parallel decoding/continuous batching/tool use, and exposes useful verification endpoints such as `/health`, `/v1/models`, and `/props`. ([GitHub][1])

**vLLM as secondary for HF-native FP4/FP8/BF16/AWQ/GPTQ is correct.** Do not make it the primary unless you want to de-emphasize GGUF/local-user reality. vLLM is powerful but it drags in WSL2/Linux, Python, PyTorch, CUDA/Triton/FlashInfer/flash-attn, and more moving parts; that is acceptable for NVFP4/FP8/BF16 lanes, not for the canonical GGUF lane. vLLM’s own docs say Blackwell-class GPUs need CUDA 12.8+ and that vLLM ships CUDA-built binaries/wheels whose exact CUDA variant matters. ([vLLM][2])

**Containers:** use them where practical, but do not pretend containers solve everything. A pinned image digest is the strongest serving-build artifact for vLLM/WSL2/Docker. For native Windows llama.cpp, a pinned binary ZIP/executable SHA256 plus `llama-server --version`, DLL hashes, and build metadata is probably the practical canonical path. The highest trust tier should require either a blessed binary digest or a container digest; a user-built binary with the same `--version` is not enough.

---

## Non-negotiable design gates

1. **`localbench bench` must force `config.concurrency=1` for the headline reproducibility lane.** Current `OrchestrateConfig.concurrency` defaults to 4, which is hostile to reproducibility for GPU serving. 

2. **Resume must be server-fingerprint-safe.** Current resume checks model/suite/tier/lane/provider, but the run segment stores `server_fingerprint: None`. That is not safe once serving is orchestrated; a resumed run must reject any changed server/model/runtime fingerprint. 

3. **`model.file_sha256` cannot stay singular-only for vLLM.** GGUF has one main file; vLLM/HF models are snapshots. Add `model.snapshot_merkle_sha256` and per-file hashes, while keeping `model.file_sha256` for GGUF. The current manifest’s model identity is file-based and already treats missing file hashes as publish-blocking.  

4. **Do not raise trust tier just because you launched a subprocess.** Raise it only when you launched the process, recorded exact argv/env, hashed exact model artifact(s), captured runtime build identity, verified endpoint-reported model/properties, and proved teardown.

---

## Canonical pinned config: llama.cpp lane

### Recommended headline command shape

Use `-m <local_exact_gguf>` after a pre-download and hash step. Avoid `-hf` for publishable rows.

```powershell
llama-server.exe `
  --model "<ABSOLUTE_PATH_TO_EXACT_MODEL.gguf>" `
  --alias "<LOCALBENCH_MODEL_ID>" `
  --host 127.0.0.1 `
  --port <ALLOCATED_PORT> `
  --api-key "<RANDOM_RUN_KEY>" `
  --ctx-size <SUITE_CONTEXT_TOKENS> `
  --n-gpu-layers all `
  --device CUDA0 `
  --split-mode none `
  --main-gpu 0 `
  --fit off `
  --parallel 1 `
  --no-cont-batching `
  --flash-attn on `
  --cache-type-k f16 `
  --cache-type-v f16 `
  --no-context-shift `
  --batch-size 2048 `
  --ubatch-size 512 `
  --threads <PINNED_INT> `
  --threads-batch <PINNED_INT> `
  --numa <PINNED_VALUE_OR_OMIT_WITH_EXPLICIT_NULL> `
  --seed <PINNED_INT> `
  --jinja `
  --reasoning off `
  --reasoning-format none `
  --no-webui `
  --no-agent `
  --log-file "<RUN_DIR>\serve.log"
```

For `--flash-attn`, choose `on` only if the pinned build and model pass preflight. Otherwise set `off`. The forbidden value for a publishable row is `auto`, because llama.cpp documents Flash Attention as `on|off|auto` with default `auto`. ([GitHub][1])

### llama.cpp flags ranked by score impact

| Rank | Pin + record                                                                                    | Why it matters                                                                                                                                                                                                                     |
| ---: | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    1 | `--model`, `--alias`, extracted GGUF metadata digest, tokenizer digest, chat-template digest    | Wrong artifact or prompt template changes the benchmark, not just the serving stack. llama.cpp’s OpenAI chat endpoint says models need supported templates for optimal use and otherwise default ChatML may be used. ([GitHub][1]) |
|    2 | `--ctx-size`, all RoPE/YaRN flags, `--no-context-shift`                                         | Context length, RoPE scaling, and context shift can alter long-context items and truncation behavior. `--ctx-size` defaults to `0` = loaded from model, and RoPE/YaRN can default from model metadata. ([GitHub][1])               |
|    3 | `--parallel 1`, `--no-cont-batching`, client concurrency `1`                                    | `--parallel` defaults to auto and continuous batching defaults enabled; both can alter scheduling and GPU numerics. ([GitHub][1])                                                                                                  |
|    4 | `--cache-type-k`, `--cache-type-v`                                                              | KV cache dtype changes quality; default is f16, but q8/q4/q5 variants exist and must be a separate leaderboard lane if used. ([GitHub][1])                                                                                         |
|    5 | `--flash-attn on/off`, never `auto`                                                             | Different attention kernels can produce small numerical changes that flip greedy choices near ties.                                                                                                                                |
|    6 | `--n-gpu-layers`, `--device`, `--split-mode`, `--main-gpu`, `--fit off`                         | `--n-gpu-layers` defaults auto and `--fit` defaults on, meaning unset memory-sensitive args may be adjusted to fit VRAM. That is unacceptable for a “regenerate from config alone” claim. ([GitHub][1])                            |
|    7 | `--batch-size`, `--ubatch-size`                                                                 | Defaults are 2048 and 512; changing them changes prompt processing/kernel paths and memory pressure. ([GitHub][1])                                                                                                                 |
|    8 | `--threads`, `--threads-batch`, `--numa`, CPU affinity/env                                      | Mostly performance/stability, but CPU fallback or hybrid CPU/GPU paths can affect timings, timeouts, and occasionally numerics.                                                                                                    |
|    9 | `--jinja`, `--reasoning`, `--reasoning-format`, `--chat-template`, `--chat-template-kwargs`     | This is especially dangerous for Qwen-style thinking. Your current run path injects `enable_thinking=False` for local answer-only, but the code comment says llama.cpp/Ollama ignore that passthrough while vLLM uses it.          |
|   10 | `--mmap`/`--no-mmap`, `--mlock`, `--warmup`, `--api-key`, `--no-webui`, `--no-agent`, `--tools` | Mostly reproducibility/security/operational stability. llama.cpp’s server has built-in tools/agent/web UI flags; keep them off for benchmark serving. ([GitHub][1])                                                                |

### llama.cpp defaults that silently hurt reproducibility

The dangerous llama.cpp defaults are `--ctx-size 0`, `--flash-attn auto`, `--n-gpu-layers auto`, `--fit on`, `--parallel -1 auto`, `--cont-batching enabled`, `--reasoning auto`, model-template fallback behavior, and `-hf` quant fallback. `-hf <repo>:<quant>` is convenient, but llama.cpp documents that the quant is optional, defaults to `Q4_K_M`, and may fall back to the first file if that quant does not exist; for a public board row that is too implicit. ([GitHub][1])

---

## Canonical pinned config: vLLM lane

### Recommended headline command shape

Run this **inside WSL2** or inside a pinned Linux container. Do not run the benchmark on Windows while only the server is inside WSL2 unless you add a Linux-side supervisor and treat Windows as a thin launcher.

```bash
export CUDA_VISIBLE_DEVICES=0
export PYTHONHASHSEED=0
export VLLM_BATCH_INVARIANT=1

vllm serve "<LOCAL_SNAPSHOT_DIR_OR_HF_ID>" \
  --host 127.0.0.1 \
  --port <ALLOCATED_PORT> \
  --api-key "<RANDOM_RUN_KEY>" \
  --served-model-name "<LOCALBENCH_MODEL_ID>" \
  --revision "<FULL_HF_COMMIT_SHA>" \
  --tokenizer-revision "<FULL_HF_COMMIT_SHA>" \
  --code-revision "<FULL_HF_COMMIT_SHA_OR_NULL>" \
  --trust-remote-code false \
  --tokenizer "<LOCAL_SNAPSHOT_DIR_OR_HF_ID>" \
  --tokenizer-mode hf \
  --config-format hf \
  --generation-config vllm \
  --dtype bfloat16 \
  --quantization <nvfp4|fp8|awq|gptq|none> \
  --max-model-len <SUITE_CONTEXT_TOKENS> \
  --gpu-memory-utilization 0.90 \
  --kv-cache-dtype bfloat16 \
  --max-num-seqs 1 \
  --max-num-batched-tokens <PINNED_INT> \
  --scheduling-policy fcfs \
  --enforce-eager \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1 \
  --data-parallel-size 1 \
  --disable-log-stats
```

For FP8/NVFP4 models, `--quantization` and `--dtype` should be chosen per model family, but not left implicit. vLLM defaults `--dtype` to `auto`; `--quantization None` means vLLM first checks `quantization_config` in model config and otherwise uses `dtype`; `--max-model-len` is auto-derived if unspecified and can auto-fit to memory for `-1/auto`. ([vLLM][3])

### vLLM flags ranked by score impact

| Rank | Pin + record                                                                                                 | Why it matters                                                                                                                                                                                                                                                    |
| ---: | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    1 | HF `revision`, `tokenizer-revision`, `code-revision`; snapshot file Merkle hash                              | Branch/tag/default revisions are not reproducible. vLLM allows branch/tag/commit for these; unspecified uses default. ([vLLM][3])                                                                                                                                 |
|    2 | `--served-model-name`, `/v1/models` response, tokenizer/chat-template/generation-config digests              | The model name in responses is controlled by `--served-model-name`; if omitted it follows `--model`. The run should assert this matches `config.model`. ([vLLM][3])                                                                                               |
|    3 | `--generation-config vllm`                                                                                   | vLLM defaults to loading generation config from the model path; a model `generation_config.json` can set server-wide output limits or sampler behavior. For a benchmark, localbench owns sampling, so this should be disabled or explicitly recorded. ([vLLM][3]) |
|    4 | `--max-model-len`                                                                                            | If unspecified, it is derived from model config; auto can choose the largest length that fits in GPU memory. That can change long-context scoring and admission behavior. ([vLLM][3])                                                                             |
|    5 | `--kv-cache-dtype`                                                                                           | `auto` uses model dtype; choices include fp8 and nvfp4, and some models default to fp8. This is score-impacting and must define separate lanes if quantized KV is used. ([vLLM][3])                                                                               |
|    6 | `--dtype`, `--quantization`                                                                                  | Weight/activation dtype and quantization path change quality/performance. Do not rely on `auto` or config inference for publishable rows. ([vLLM][3])                                                                                                             |
|    7 | `--max-num-seqs 1`, client concurrency `1`, `VLLM_BATCH_INVARIANT=1`                                         | vLLM states reproducibility is not guaranteed by default; online mode requires batch invariance for reproducibility. ([vLLM][4])                                                                                                                                  |
|    8 | `--max-num-batched-tokens`, chunked prefill settings, scheduler policy                                       | vLLM docs explicitly say default max batched tokens/max seqs are convenience defaults and real usage should set them in engine config. ([vLLM][3])                                                                                                                |
|    9 | `--gpu-memory-utilization` or `--kv-cache-memory-bytes`                                                      | Default is 0.92; changing it changes KV capacity and may alter whether requests fit, chunk, or fail. ([vLLM][3])                                                                                                                                                  |
|   10 | `--enforce-eager` / CUDA graph policy, attention backend, cascade/sliding-window flags                       | CUDA graph/eager and attention implementations usually affect speed, but they can also affect numerics. Pin, record, and separate “strict” vs “throughput” profiles if needed.                                                                                    |
|   11 | `--trust-remote-code`, model implementation, load format, LoRA/speculative decoding flags, tool parser flags | Any of these can change code paths or semantics. `trust_remote_code=true` should require full code revision and code hash.                                                                                                                                        |

### vLLM defaults that silently hurt reproducibility

The defaults to avoid are `--dtype auto`, `--quantization None` with config inference, unspecified `--revision`/`--tokenizer-revision`/`--code-revision`, `--max-model-len` auto, `--generation-config auto`, `--kv-cache-dtype auto`, default `--gpu-memory-utilization 0.92`, unset `--max-num-seqs`, tokenizer/chat-template auto behavior, and any implicit remote code. vLLM also has API/frontend flags for tool choice, chat templates, prompt token details, fingerprint mode, host/port/API key, and renderer workers; record the full resolved `vllm serve --help` version and actual argv. ([vLLM][3])

---

## Provenance spec to add

The current manifest already captures required model identity, runtime identity, sampling, endpoint-reported model, hardware via `nvidia-smi`, and a `determinism_policy` slot. That is a good start, but it is not enough for orchestrated serving.   

Add a nested serving block, for example:

```json
{
  "serving": {
    "runtime": "llama.cpp",
    "verification_level": "orchestrated-pinned-artifacts-v1",
    "launch": {
      "argv": ["..."],
      "cwd": "...",
      "env_allowlist": {
        "CUDA_VISIBLE_DEVICES": "0",
        "LLAMA_ARG_*": "none present unless recorded",
        "VLLM_BATCH_INVARIANT": "1"
      },
      "host": "127.0.0.1",
      "port": 49152,
      "api_key_sha256": "..."
    },
    "artifact": {
      "kind": "native-binary|container",
      "container_image_digest": null,
      "executable_sha256": "...",
      "dll_or_so_hashes": {
        "ggml-cuda.dll": "...",
        "cudart64_*.dll": "...",
        "cublas64_*.dll": "..."
      },
      "version_stdout": "...",
      "source_repo": "ggml-org/llama.cpp",
      "source_commit": "...",
      "source_tag": "...",
      "build_flags": "...",
      "help_text_sha256": "..."
    },
    "resolved_runtime": {
      "ctx_len_configured": 32768,
      "parallel_slots": 1,
      "continuous_batching": false,
      "kv_cache_quant": "k=f16,v=f16",
      "flash_attention": "on",
      "rope_scaling": "model-default|none|linear|yarn",
      "reasoning": "off",
      "chat_template_digest": "..."
    },
    "readiness_evidence": {
      "health_200_at": "...",
      "models_response_sha256": "...",
      "props_response_sha256": "...",
      "reported_model": "...",
      "smoke_chat_sha256": "..."
    },
    "teardown_evidence": {
      "owned_process_tree": ["pid..."],
      "terminated": true,
      "exit_code": 0,
      "gpu_pids_after": []
    }
  }
}
```

For vLLM, add:

```json
{
  "runtime_packages": {
    "python": "...",
    "vllm": "...",
    "vllm_commit": "...",
    "torch": "...",
    "torch_cuda": "...",
    "triton": "...",
    "flash_attn": "...",
    "flashinfer": "...",
    "cuda_driver": "...",
    "cuda_runtime": "...",
    "nvidia_smi": "..."
  },
  "model_snapshot": {
    "hf_repo": "...",
    "hf_revision_sha": "...",
    "snapshot_merkle_sha256": "...",
    "files": [
      {"path": "config.json", "sha256": "..."},
      {"path": "model-00001-of-000xx.safetensors", "sha256": "..."},
      {"path": "tokenizer.json", "sha256": "..."},
      {"path": "tokenizer_config.json", "sha256": "..."},
      {"path": "chat_template.jinja", "sha256": "..."},
      {"path": "generation_config.json", "sha256": "..."}
    ]
  }
}
```

For GGUF, also dump and hash `gguf_metadata.json`, because the tokenizer/template may be embedded in the GGUF rather than provided as a separate tokenizer file.

---

## Determinism story: be honest

The defensible public claim is:

> **Same-stack, greedy, single-slot reproducibility is attempted and evidenced; bitwise GPU reproducibility across drivers, GPUs, runtime builds, or batching conditions is not claimed.**

Do not claim “deterministic” without qualifiers. vLLM explicitly says it does not guarantee reproducibility by default, online serving needs batch invariance, and even with reproducibility settings vLLM only claims reproducibility on the same hardware and same vLLM version. ([vLLM][4]) PyTorch likewise states complete reproducibility is not guaranteed across releases, commits, platforms, or CPU/GPU even with identical seeds. ([PyTorch Documentation][5])

For headline rows, use:

```json
{
  "policy_id": "gpu-greedy-single-slot-v1",
  "claim": "best-effort same-stack reproducibility; not bitwise cross-stack determinism",
  "client": {
    "temperature": 0,
    "top_k": 1,
    "seed": 1234,
    "concurrency": 1
  },
  "server": {
    "parallel_slots": 1,
    "continuous_batching": false,
    "vllm_max_num_seqs": 1,
    "vllm_batch_invariant": true,
    "llama_cont_batching": false
  },
  "scope": [
    "same model artifact hash",
    "same runtime binary/container digest",
    "same GPU architecture",
    "same driver/runtime family",
    "same serve flags",
    "same localbench suite hash"
  ],
  "known_limits": [
    "GPU floating-point non-associativity",
    "kernel/library changes",
    "driver changes",
    "batching/scheduler changes",
    "timeout/VRAM pressure effects"
  ]
}
```

**Force serialization for canonical scoring.** That means localbench client concurrency `1`, llama.cpp `--parallel 1 --no-cont-batching`, and vLLM `--max-num-seqs 1` plus `VLLM_BATCH_INVARIANT=1` when supported. vLLM’s batch-invariance feature is beta, requires NVIDIA compute capability 8.0+, and is enabled with `VLLM_BATCH_INVARIANT=1`; it also intentionally disables some optimizations and may cost performance. ([vLLM][6])

Allow a separate `--determinism throughput` profile later, but do not use it for headline leaderboard rows unless the row explicitly carries variance evidence.

---

## Serving build identity and pinning

### llama.cpp

Record all of these:

* `llama-server --version` stdout; docs say it shows version and build info. ([GitHub][1])
* `llama-server.exe` SHA256.
* Hashes of all adjacent runtime DLLs: `ggml*.dll`, `ggml-cuda*.dll`, `llama.dll`, CUDA runtime, cuBLAS/cuDNN if dynamically loaded.
* `--list-devices` stdout.
* Full command argv.
* `--help` text SHA256 for the pinned binary.
* Build source commit SHA, tag, CMake flags, CUDA arch flags, compiler version.
* For container lane: image digest, not image tag.

**Pin to commit + artifact digest, not release tag alone.** Release tags are useful labels, but a board row should be reproducible from a content digest. The best native-Windows story is “blessed local-bench llama.cpp build artifact SHA256 + upstream commit SHA.” The best Linux story is “container image digest + upstream commit SHA.” llama.cpp itself documents Docker server and CUDA server examples, so containerized llama.cpp is viable on Linux/WSL, but native Windows still needs binary hashing. ([GitHub][1])

### vLLM

Highest trust: container image digest plus `pip freeze`/package inventory from inside the container.

Record:

* `vllm --version` or `python -c 'import vllm; print(vllm.__version__)'`.
* vLLM source commit if installed from commit wheel.
* Python version.
* Torch version, `torch.version.cuda`, Torch git version if available.
* Triton, flash-attn, FlashInfer, xFormers, NCCL versions if installed.
* `nvidia-smi` driver and CUDA runtime view.
* Wheel filenames and SHA256 if not using a container.
* Full environment allowlist.

vLLM docs support installing wheels for a specific commit via a full commit hash URL, and Blackwell-class support depends on CUDA wheel/runtime choices, so “vLLM version” alone is not enough. ([vLLM][2])

---

## Model pull provenance

**Use pre-download + hash for publishable rows.** Do not use `llama-server -hf` as the canonical path.

For GGUF:

```bash
hf download <repo> <filename.gguf> --revision <FULL_40_CHAR_COMMIT_SHA> --local-dir <cache>
sha256sum <filename.gguf>
llama-server -m <absolute_file_path> ...
```

Hugging Face’s download API defaults to latest `main`, while `revision` can pin a branch/tag/PR/commit; when using a commit hash, the docs require the full-length hash. ([Hugging Face][7]) That is exactly why `hf_revision_sha` must be full SHA, not a tag, not `main`, and not a short commit.

Record:

```json
{
  "model": {
    "source": "hf",
    "repo_id": "...",
    "revision_sha": "full commit sha",
    "filename": "exact.gguf",
    "file_size_bytes": 123,
    "file_sha256": "...",
    "quant_label": "UD-Q4_K_XL",
    "format": "GGUF",
    "gguf_metadata_sha256": "...",
    "tokenizer_digest": "...",
    "chat_template_digest": "..."
  }
}
```

For vLLM:

Use `snapshot_download(repo_id, revision=<full_sha>)`, hash the entire snapshot with a stable Merkle tree, and record every file that can affect serving: `config.json`, all `safetensors`, tokenizer files, chat template, generation config, quantization config, and any remote-code files if `trust_remote_code=true`.

---

## Lifecycle and teardown design

### Readiness

For both lanes:

1. Allocate a loopback port. Do not use fixed 8080/8000. Bind a socket to port 0, close, launch, and retry on bind failure; or run a tiny supervisor that owns allocation.
2. Launch with stdout/stderr tee’d to `serve.log`.
3. Poll `/health` until ready. llama.cpp documents 503 while loading and 200 once ready. ([GitHub][1])
4. Poll `/v1/models`; assert the model id equals `--alias`/`--served-model-name`. llama.cpp says `/v1/models` returns the loaded model and `--alias` controls the id. ([GitHub][1])
5. For llama.cpp, GET `/props` and record `total_slots`, `model_path`, `chat_template`, and `build_info`; docs identify those fields and tie `total_slots` to `--parallel` and `model_path` to `-m`. ([GitHub][1])
6. Run a smoke `/v1/chat/completions` with `max_tokens=1`, temp 0, and the same model name.
7. Optional but strongly recommended: hash `/tokenize` and `/apply-template` results for a canonical prompt, because template/tokenizer drift is a top score-risk.

### Windows teardown

Use a Windows Job Object, not ad hoc PID kill.

* Create Job Object.
* Set `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
* Start `llama-server` in the job.
* Ensure handles are non-inheritable except where intended.
* Do not allow breakaway.
* On `finally`, Ctrl-Break or terminate gracefully, then close/terminate the job.
* Poll `nvidia-smi --query-compute-apps=pid,process_name,used_memory` until no owned PID remains.
* If any owned PID or VRAM allocation remains, mark the run `teardown_uncertain=true` and fail publishability.

Microsoft documents that processes can be assigned to a job, child processes are associated by default, `TerminateJobObject` terminates all processes in the job, and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` terminates associated processes when the last job handle closes. ([Microsoft Learn][8])

### WSL2/vLLM teardown

A process group is necessary but not sufficient if Windows kills only `wsl.exe`. The robust design is:

* Prefer running the entire `localbench bench --runtime vllm` inside WSL2.
* Use `subprocess.Popen(..., start_new_session=True)` so the Linux child gets its own session/process group; Python documents that `start_new_session=True` calls `setsid()` and `process_group` maps to `setpgid()`. ([Python documentation][9])
* Kill the process group: SIGTERM, wait, SIGKILL.
* Add a tiny Linux supervisor wrapper with `prctl(PR_SET_PDEATHSIG, SIGKILL)` or heartbeat monitoring so the server dies if the orchestrator dies.
* If using Docker in WSL2, record container id and use `docker rm -f <id>` as the final containment kill.
* Poll Linux `nvidia-smi` and Windows-side `nvidia-smi` after teardown. vLLM can leave worker processes if only the API server PID is killed.

The claim should be “guaranteed for the process tree/container we own under normal OS semantics,” not “guaranteed under kernel hang, driver wedging, power loss, or malicious breakaway.”

---

## Trust-tier and verification-level naming

Use explicit, boring names. I would implement:

```text
serving_verification_level:
  external-endpoint
  orchestrated-process-v1
  orchestrated-pinned-artifacts-v1
  maintainer-reproduced-v1
```

Raise to **`orchestrated-process-v1`** when localbench launched the process, captured argv/env, verified `/health` and `/v1/models`, and tore it down.

Raise to **`orchestrated-pinned-artifacts-v1`** only when all of these are true:

* Exact model artifact or snapshot hash is present.
* Runtime binary SHA256 or container image digest is present.
* Runtime version/build output is present.
* Command argv and environment allowlist are present.
* Endpoint-reported model matches requested model.
* Resolved runtime properties match pinned config.
* Serve logs are attached.
* Teardown evidence is clean.
* No resume segment used a different server fingerprint.

Reserve **`maintainer-reproduced-v1`** for an independent rerun from the recorded config that matches score/output acceptance criteria.

What still makes an orchestrated run untrustworthy:

* Operator patched the binary but spoofed `--version`; mitigated only by blessed artifact digest.
* Operator patched localbench/scorer or edited result JSON; mitigated by repo commit/dirty tree plus server-side verification, but not eliminated.
* Hidden LoRA/control vector/speculative decoder/tool parser.
* Model artifact hash does not cover all files.
* Tokenizer/chat template differs from benchmark prompt renderer.
* WSL2/Docker/driver/PyTorch/Triton/FlashInfer differences.
* Resume stitched together different servers.
* GPU nondeterminism flips greedy tokens.
* Timeouts/truncation caused by VRAM pressure or thermal/power throttling.

---

## One command or two?

Use **one command with runtime adapters**:

```bash
localbench bench --runtime llama.cpp ...
localbench bench --runtime vllm ...
```

Do not create separate top-level commands. The whole point is parallel provenance, comparable run records, and reuse of the endpoint-agnostic `run_localbench` seam. The provider already treats local serving as a passthrough to arbitrary OpenAI-compatible servers, so the new code should be an outer lifecycle/provenance wrapper that ultimately calls the existing run loop. 

Example GGUF command:

```bash
localbench bench \
  --runtime llama.cpp \
  --model-ref "hf://<repo>@<FULL_SHA>#<exact-file.gguf>" \
  --model-id "<board-model-id>" \
  --tier standard \
  --bench all \
  --ctx 32768 \
  --determinism strict
```

Example vLLM command:

```bash
localbench bench \
  --runtime vllm \
  --model-ref "hf://nvidia/Qwen3.6-27B-NVFP4@<FULL_SHA>" \
  --model-id "qwen3.6-27b-nvfp4" \
  --tier standard \
  --bench all \
  --ctx 32768 \
  --determinism strict
```

For vLLM on Windows: either require the command to be run inside WSL2, or make the Windows CLI a thin launcher that runs the entire localbench process inside WSL2 and copies out the result bundle. Do **not** start a WSL2 server from Windows and run the suite from Windows as the canonical path; that splits process ownership, paths, env, teardown, and provenance.

---

## Top gotchas ranked by score impact

1. **Prompt rendering/tokenizer/chat-template mismatch.** This is the biggest embarrassment risk. llama.cpp warns that only models with supported chat templates are optimal with `/v1/chat/completions`; otherwise default ChatML can apply. ([GitHub][1]) For Qwen-style models, your own code currently relies on `chat_template_kwargs={"enable_thinking": False}` for answer-only local runs, but notes llama.cpp ignores that field. 

2. **Context truncation and context mutation.** `--ctx-size`, vLLM `--max-model-len`, sliding window, RoPE/YaRN, and context shift can change long-context scores. Your code already has RULER truncation detection via prompt-token estimates; make that publish-blocking for long-context rows. 

3. **KV-cache quantization.** f16/bf16 KV should be the quality lane. q8/q4/fp8/nvfp4 KV should be separate cache-quant lanes, because quality can move.

4. **Dynamic batching/concurrency.** llama.cpp continuous batching defaults enabled and `--parallel` defaults auto; vLLM defaults are built for throughput, not reproducibility. ([GitHub][1])

5. **Model artifact drift.** HF `main`, tags, optional quant labels, “first file” fallback, and multi-file snapshots are all traps. Full revision SHA + exact file/snapshot hash is mandatory. ([GitHub][1])

6. **Generation config leakage.** vLLM’s default `--generation-config auto` can load model-supplied generation config and even set server-wide output-token limits. Use `--generation-config vllm` or record and justify the exact loaded config. ([vLLM][3])

7. **AppWorld output cap and reasoning mode.** The source comment says official AppWorld-C scored runs use 3072 max output tokens per turn because the lower default truncates verbose reasoning models into harness-dominated failure. Keep that invariant in the new command. 

8. **Resume with changed server.** Current resume safety does not include server fingerprint. Once serving is orchestrated, resume must reject any mismatch in model hash, runtime digest, argv, env, ctx, KV dtype, parallelism, or chat template.

9. **Flash attention / CUDA graph / cascade attention numerics.** These are usually small numerical differences, but greedy decoding is chaotic around near-tie logits. Pin and record; never leave “auto” for publishable rows.

10. **Hidden LoRA/control vectors/speculative decoding/tools.** llama.cpp exposes LoRA/control-vector/speculative/tool/agent features; vLLM exposes LoRA/tool parser/speculative-style options. For benchmark serving, default-deny all of them unless they are explicitly part of the model identity. ([GitHub][1])

11. **`--fit`/auto offload/mmap/VRAM pressure.** llama.cpp `--fit on` can adjust unset args to fit device memory; vLLM memory utilization/KV sizing controls admission and offload. These are not just performance knobs when timeouts and truncation affect scores. ([GitHub][1])

12. **WSL2 zombie VRAM.** vLLM worker processes can survive if only the parent/API PID is killed. Treat unexplained post-run GPU memory as a failed teardown, not a warning.

---

## Build recommendation for Codex

Have Codex build `localbench bench`, but fail closed:

* No immutable model revision/hash → non-publishable.
* No runtime binary/container digest → at most `orchestrated-process-v1`, not pinned-artifact.
* `--parallel >1`, client concurrency >1, continuous batching enabled, or vLLM `max-num-seqs >1` → not headline reproducibility lane.
* Any `auto` for score-impacting knobs → non-publishable unless the resolved value is captured from runtime evidence.
* Resume server fingerprint mismatch → hard error.
* Dirty localbench tree or missing dependency-lock hash → publish-blocking unless maintainer override.
* Teardown uncertain → publish-blocking.

That gives you a defensible board story: **not “we made GPU inference deterministic,” but “we made serving configuration artifact-pinned, endpoint-verified, reproducible enough to regenerate and audit, with determinism limits explicitly recorded.”**

[1]: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp/tools/server/README.md at master · ggml-org/llama.cpp · GitHub"
[2]: https://docs.vllm.ai/en/stable/getting_started/installation/gpu/ "GPU - vLLM"
[3]: https://docs.vllm.ai/en/stable/cli/serve/ "vllm serve - vLLM"
[4]: https://docs.vllm.ai/en/latest/usage/reproducibility/ "Reproducibility - vLLM"
[5]: https://docs.pytorch.org/docs/2.12/notes/randomness.html "Reproducibility — PyTorch 2.12 documentation"
[6]: https://docs.vllm.ai/en/latest/features/batch_invariance/ "Batch Invariance - vLLM"
[7]: https://huggingface.co/docs/huggingface_hub/en/guides/download "Download files from the Hub · Hugging Face"
[8]: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects "Job Objects - Win32 apps | Microsoft Learn"
[9]: https://docs.python.org/3/library/subprocess.html "subprocess — Subprocess management — Python 3.14.6 documentation"

