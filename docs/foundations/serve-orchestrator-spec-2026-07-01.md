# `localbench bench` serve-orchestrator — build spec (2026-07-01)

## Why / goal
Today's benchmark runs are served by hand in the LM Studio GUI → not reproducible. Build a NEW
`localbench bench` command that makes the benchmark **repeatable and provenance-complete**: it
launches the serving process itself with pinned config, verifies the endpoint, runs the existing
suite, captures serving provenance from the process it launched, and tears the process tree down
deterministically. This is the canonical path an external user (and Michael as submission #0) runs.

**This build = the llama.cpp/GGUF lane only.** vLLM is a defined adapter interface + a deferred
stub tonight (see §9). Design rationale (READ IT) is `docs/foundations/serve-orchestrator-oracle-verdict-2026-07-01.md`
(GPT-5.5 Pro red-team). This spec is the authority where it and the verdict differ.

## Authoritative sources — READ, do NOT change
- Existing run loop (WRAP, don't rewrite): `cli/src/localbench/orchestrate.py` (`run_localbench`,
  `OrchestrateConfig`). It is already endpoint-agnostic and hits an OpenAI-compatible server at
  `config.endpoint`. The new command is an OUTER lifecycle/provenance wrapper that ultimately calls
  `run_localbench`.
- Manifest/provenance: `cli/src/localbench/manifest.py` (`ManifestContext`, `collect_manifest`).
  It ALREADY has slots for `runtime_name/version/kv_cache_quant/ctx_len_configured/parallel_slots/
  build_flags/runtime_backend/cuda_version` + `model_file`/`model_family`/`quant_label`/`model_format`/
  `tokenizer_file`/`chat_template_file` + `determinism_policy`. Today those are hand-typed CLI flags;
  the orchestrator MUST populate them from the launched server instead.
- Provider passthrough: `cli/src/localbench/providers/_openai.py` (the `local` provider).
- Existing submit path (do NOT duplicate): `cli/src/localbench/submissions/*` + `localbench submit`.
  `localbench bench` produces the result_bundle_v1 on disk; submission is the SEPARATE existing
  `localbench submit` flow. Do not build submission into `bench`.
- Suite resolver: `cli/src/localbench/suite_resolver.py`, `fetch-suite`.

## The command
```
localbench bench
  --runtime llama.cpp                         # (vllm = deferred stub tonight)
  --model-file "<ABS_PATH.gguf>"              # tonight's primary input: an already-local GGUF
    | --model-ref "hf://<repo>@<FULL_40CHAR_SHA>#<exact-file.gguf>"   # auto-pull path (see §4)
  --model-id "<board-model-id>"               # the alias / served-model-name
  --server-bin "<home>\llamacpp\b9852\llama-server.exe"     # pinned binary (default discoverable via env LOCALBENCH_LLAMA_SERVER)
  --ctx 32768
  --determinism strict                        # strict = headline reproducibility lane (default)
  --tier standard|quick
  --bench all
  --lane answer-only                          # forwarded to run_localbench
  --seed 1234
  --suite core-text-v1 [--suite-source <fetched-suite-dir> | --suite-dir <dir>]
  --out <run-dir>
  [--resume <run-dir>]
```
`--determinism strict` is the only supported profile for a publishable row; a future
`--determinism throughput` may exist but is out of scope and must be refused for publishable rows.

## The artifact-first flow (implement in this order)
1. **Resolve + hash the model artifact.** From `--model-file` (hash the local GGUF) or `--model-ref`
   (pre-download the exact revision, then hash — §4). Compute: `file_sha256`, `file_size_bytes`,
   `gguf_metadata_sha256` (dump GGUF metadata to JSON and hash it — tokenizer/template may be embedded
   in the GGUF), `tokenizer_digest`, `chat_template_digest`. NEVER use `-hf` auto-pull for a
   publishable row (§4).
2. **Capture serving-build identity.** `llama-server --version` stdout; SHA256 of `llama-server.exe`
   and adjacent runtime DLLs (`ggml*.dll`, `ggml-cuda*.dll`, `llama.dll`, `cudart64_*.dll`,
   `cublas64_*.dll`); `--list-devices` stdout; SHA256 of `--help` text; the resolved source commit/tag
   (record b-tag `b9852` + commit `fd1a05791` for the installed build; discover from `--version`).
3. **Launch the server pinned**, inside a Windows Job Object (§6), on an allocated loopback port
   with a random per-run api-key, stdout+stderr tee'd to `<run-dir>/serve.log`. Exact argv in §5.
4. **Verify readiness** (§6): `/health` 503→200; `/v1/models` id == alias; GET `/props` record
   `total_slots`,`model_path`,`chat_template`,`build_info`; smoke `/v1/chat/completions` `max_tokens=1`
   temp 0; hash `/tokenize` + `/apply-template` of a canonical prompt. Assert `total_slots == 1` and
   `model_path` matches the resolved artifact.
5. **Run the suite.** Build `OrchestrateConfig` (§7) with the strict-lane enforcement + the
   auto-populated runtime/model provenance, pointing `endpoint` at the launched server; call
   `run_localbench`.
6. **Assemble serving provenance** (§8) into the bundle: the `serving` block, `determinism_policy`,
   the earned `serving_verification_level` + `trust_tier`. Apply the fail-closed gates (§10).
7. **Tear down** the owned process tree (§6) and record teardown evidence. Guaranteed via `finally`.

## §5 — llama.cpp pinned argv (strict lane)
Build argv explicitly; NEVER leave a score-impacting knob at its `auto` default. From the verdict:
```
llama-server.exe
  --model "<ABS_EXACT.gguf>"
  --alias "<model-id>"
  --host 127.0.0.1 --port <ALLOCATED> --api-key "<RANDOM_RUN_KEY>"
  --ctx-size <ctx>                 # NEVER 0 (=load-from-model)
  --n-gpu-layers 999               # all; NEVER auto
  --device CUDA0 --main-gpu 0 --split-mode none
  --fit off                        # NEVER on (auto-adjusts unset args to fit VRAM)
  --parallel 1 --no-cont-batching  # serialize for reproducibility
  --flash-attn on                  # on|off ONLY, NEVER auto; preflight-verify, else off
  --cache-type-k f16 --cache-type-v f16
  --cache-ram 0 --ctx-checkpoints 32 --checkpoint-min-step 8192
  --no-context-shift
  --batch-size 2048 --ubatch-size 512
  --threads <PINNED> --threads-batch <PINNED>
  --seed <seed>
  --jinja --reasoning none --reasoning-format none
  --no-webui --no-agent
  --log-file "<run-dir>\serve.log"
```
Forbidden-for-publishable defaults to guard against: `--ctx-size 0`, `--flash-attn auto`,
`--n-gpu-layers auto`, `--fit on`, `--parallel` auto, continuous-batching enabled, `--reasoning auto`,
model chat-template fallback, and `-hf` quant fallback. Record the fully-resolved argv verbatim.

Flag names must be validated against the pinned binary's `--help` (b9852). If a flag name differs in
b9852, use the binary's actual spelling and record the resolved argv; do not silently drop a pinned
knob — if a required knob is unavailable, fail closed (non-publishable) with a clear reason.

## §6 — lifecycle, teardown, readiness
- **Port:** bind a socket to port 0, read the assigned port, close, launch, retry on bind failure.
  Do not hardcode 8080/8000.
- **Windows Job Object (ctypes, no new dependency):** `CreateJobObjectW` →
  `SetInformationJobObject(JobObjectExtendedLimitInformation, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)` →
  start `llama-server` (CREATE_SUSPENDED or normal) → `AssignProcessToJobObject` → resume. On
  `finally`: graceful stop then `TerminateJobObject`, then close the job handle. This also fixes the
  flagged supervisor follow-up (CTRL_BREAK/TerminateProcess can orphan grandchildren) — reuse/extend
  the same mechanism if `supervisor.py` is involved.
- **Teardown evidence:** after kill, poll `nvidia-smi --query-compute-apps=pid,used_memory
  --format=csv,noheader` until no owned PID remains (timeout ~30s). If an owned PID or its VRAM
  remains → `teardown_evidence.terminated=false`, set `teardown_uncertain=true` → publish-blocking.
- **Readiness probe:** poll `/health` (llama.cpp returns 503 while loading, 200 ready) up to a startup
  timeout (~180s, configurable); then `/v1/models` (assert `id==alias`); GET `/props`; smoke chat.
  On any readiness failure: tear down, fail the run with a clear reason.

## §7 — wire to `run_localbench` (strict-lane enforcement)
Construct `OrchestrateConfig` with:
- `endpoint` = `http://127.0.0.1:<port>/v1`, `api_key` = the random run key, `model` = `--model-id`.
- `concurrency = 1` (HARD — the verdict's #1 gate; the default 4 is hostile to reproducibility).
- `sampler_temperature = 0.0`, `sampler_top_k = 1`, `sampler_seed = <seed>` (greedy, the known
  temp-0≠greedy llama.cpp defect fix). Keep existing per-lane behavior otherwise.
- `provider = "local"`, `lane` = `--lane`.
- The runtime/model provenance fields (`runtime_name="llama.cpp"`, `runtime_version=<b-tag/commit>`,
  `kv_cache_quant="k=f16,v=f16"`, `ctx_len_configured=<ctx>`, `parallel_slots=1`, `build_flags=<...>`,
  `runtime_backend="cuda"`, `cuda_version=<from cudart/driver>`, `model_file=<abs gguf>`,
  `model_family`, `quant_label`, `model_format="GGUF"`, `tokenizer_file`/`chat_template_file` if
  extracted) — populated from the launched server, NOT hand-typed.
- `determinism_policy = "gpu-greedy-single-slot-v1"`.
- Suite: the site-released suite when submitting (via `--suite-source`/fetched dir); otherwise the
  local suite for a smoke.
Then the OUTER wrapper augments the produced bundle with the serving block + upgraded tier (§8). Pick
the minimal-diff wiring: preferred is threading a `serving_context` object into `OrchestrateConfig` →
`ManifestContext` so the bundle is written once with the serving block and the run_record's
`serving_verification_level`/`trust_tier` are set from it (replacing the hardcoded
`"external-endpoint"` at orchestrate.py ~L589). A read-back-and-rewrite is acceptable if cleaner.

## §8 — serving provenance block (add to the bundle)
Add a nested `serving` object (verdict schema, verbatim shape):
```json
{"serving": {
  "runtime": "llama.cpp",
  "verification_level": "orchestrated-pinned-artifacts-v1",
  "launch": {"argv": ["..."], "cwd": "...", "env_allowlist": {"CUDA_VISIBLE_DEVICES": "0"},
             "host": "127.0.0.1", "port": 49152, "api_key_sha256": "..."},
  "artifact": {"kind": "native-binary", "container_image_digest": null,
               "executable_sha256": "...", "dll_or_so_hashes": {"ggml-cuda.dll": "...", "cudart64_13.dll": "...", "cublas64_13.dll": "..."},
               "version_stdout": "...", "source_repo": "ggml-org/llama.cpp", "source_commit": "fd1a05791", "source_tag": "b9852",
               "build_flags": "...", "help_text_sha256": "..."},
  "resolved_runtime": {"ctx_len_configured": 32768, "parallel_slots": 1, "continuous_batching": false,
                       "kv_cache_quant": "k=f16,v=f16", "flash_attention": "on", "rope_scaling": "model-default",
                       "reasoning": "off", "chat_template_digest": "..."},
  "readiness_evidence": {"health_200_at": "...", "models_response_sha256": "...", "props_response_sha256": "...",
                         "reported_model": "...", "smoke_chat_sha256": "..."},
  "teardown_evidence": {"owned_process_tree": ["pid..."], "terminated": true, "exit_code": 0, "gpu_pids_after": []}
}}
```
Plus `determinism_policy` = the `gpu-greedy-single-slot-v1` object from the verdict (client
temp0/top_k1/seed/concurrency1; server parallel1/no-cont-batching; scope + known_limits). Also dump
+ hash `gguf_metadata.json` alongside the run.

## §9 — vLLM adapter (DEFERRED tonight)
Define a runtime-adapter interface (e.g. `RuntimeAdapter` with `resolve_model`, `launch`,
`readiness`, `build_identity`, `teardown`) so llama.cpp is one implementation. Provide a `vllm`
adapter STUB that raises `NotImplementedError("vLLM lane deferred — see spec §9")`. Do NOT build vLLM
serving, WSL2 handoff, or snapshot-merkle hashing tonight — but leave the model-identity schema able
to carry `snapshot_merkle_sha256` + per-file hashes (nullable) so vLLM slots in later.

## §10 — fail-closed publishability gates (verdict "Build recommendation")
Compute publishability + `serving_verification_level` from evidence, defaulting to LEAST-privileged:
- No immutable model revision/hash → non-publishable.
- No runtime binary digest → at most `orchestrated-process-v1` (NOT pinned-artifacts).
- `parallel > 1`, client `concurrency > 1`, continuous batching enabled → not the headline lane.
- Any `auto` for a score-impacting knob whose resolved value was NOT captured from runtime evidence →
  non-publishable.
- Resume server-fingerprint mismatch → hard error (§11).
- Dirty localbench tree or missing dependency-lock hash → publish-blocking (maintainer override only).
- `teardown_uncertain` → publish-blocking.
Tier ladder + criteria are in the verdict "Trust-tier" section — implement those exact names:
`external-endpoint → orchestrated-process-v1 → orchestrated-pinned-artifacts-v1 → maintainer-reproduced-v1`.
`bench` earns `orchestrated-pinned-artifacts-v1` only when ALL of: model artifact hash present, runtime
binary SHA256 present, version/build output present, argv+env allowlist present, endpoint-reported
model == requested, resolved runtime props == pinned config, serve log attached, teardown clean, and no
resume segment used a different server fingerprint. Otherwise `orchestrated-process-v1`.

## §11 — server-fingerprint-safe resume
The current resume invariant (`_validate_resume_campaign`) checks model/suite/tier/lane/provider but
stores `server_fingerprint: None`. Extend it: compute a server fingerprint =
hash(model_file_sha256, runtime executable_sha256, resolved argv, env allowlist, ctx, kv dtype,
parallel_slots, flash_attn, chat_template_digest). Persist it in `campaign.json` + each run segment.
On `--resume`, REJECT (hard error) any mismatch. Update the segment record to carry the real
fingerprint (not `None`).

## Guardrails (HARD)
- Branch `codex/local-bench-online-backend`. Work on top of current HEAD.
- `cli/runs/board/board_v1.json` BYTE-IDENTICAL — print `git hash-object cli/runs/board/board_v1.json`
  before and after; MUST stay `3d058e6074bd781cc488c03255904b5f9599e37e`.
- Do NOT touch any `web/` route, any secret, or the suite JSON files. No deploy, no push, NO git
  commit — leave ALL changes uncommitted for Claude's review. Smallest correct change.
- Keep `uv run --project cli pytest` GREEN. Add unit tests; do not weaken existing ones.
- `hf` auto-pull may need `huggingface_hub` in the cli env — if you add it to `cli/pyproject.toml`,
  keep it optional/lazy-imported so `--model-file` works without it and existing tests don't change.

## Tests (no real GPU/network)
Unit tests with mocked subprocess + mocked httpx (`MockTransport`) covering:
- argv construction for the strict lane (asserts every pinned flag present; asserts no `auto`).
- serving-build-identity assembly (mock `--version`/`--help`/file hashes).
- readiness parsing (`/health` 503→200 sequence, `/v1/models` id-assert, `/props` capture, smoke).
- serving provenance block assembly + `determinism_policy` shape.
- fail-closed gates: each failing precondition yields the right tier / non-publishable + reason.
- server-fingerprint resume: mismatch → hard error; match → proceeds.
- teardown logic with mocked Job Object + mocked `nvidia-smi` (residual PID → teardown_uncertain).
- Job Object ctypes wrapper: unit-test the wrapper's argument marshalling (mock `ctypes.windll`); the
  real kill path is validated live by Claude's serve-smoke, not in CI.

## Acceptance / evidence (report back)
- Files changed + the new command wiring (how `bench` wraps `run_localbench`).
- Exact `uv run --project cli pytest` command + pass/fail counts (+N new tests, none weakened).
- `git hash-object cli/runs/board/board_v1.json` (expect `3d058e60…`).
- The fully-resolved strict-lane argv it would launch for a Gemma-12B GGUF (printed, not run).
- What is ready for Claude to drive the live serve-smoke + first Gemma-12B run, and any flag-name
  adjustments made against the b9852 `--help`.
- Confirm: no push, no commit, no web/secret/board/suite changes.
