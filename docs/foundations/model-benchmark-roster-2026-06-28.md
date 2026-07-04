# Model Benchmark Roster - 2026-06-28

Status: draft planning slate. This file records the model and quant campaigns to review before starting new benchmark runs.

Scoring contract: Local Intelligence Index v2.1, as documented in `docs/scoring-methodology.md`.

Headline campaign axes:

- Agentic: `appworld_c`
- Knowledge: `mmlu_pro`
- Instruction-following: `ifbench`
- Tool-calling: `tc_json_v1`
- Coding: `lcb`

## Operating Principles

Each approved model/quant/runtime row should be run as one serial campaign across all headline axes. Do not run multiple benchmark jobs on the same GPU at the same time.

The roster is designed to answer three questions:

1. Quant performance: how does the same model change across Q4, Q6, Q8, or equivalent GGUF quant tiers?
2. Distillation/tuning delta: how does a derivative model perform against its parent or nearest base model at the same quant tier?
3. Runtime practicality: how much speed, memory, and stability is gained or lost for each local setup?

Capability score and runtime performance should remain separate published signals. A faster quant is not inherently better unless its capability loss is acceptable.

## Storage And Cleanup Rules

Benchmark outputs are the durable artifact, not the downloaded model files. Keep receipts, manifests, raw generations, score JSON, logs, hardware/runtime provenance, and checksums. Delete or evict model binaries unless they are explicitly marked for near-term reuse.

### Preflight Storage Record

Before each campaign, record:

- Model repository, exact quant filename, and expected download size.
- Local path or cache location used for the model.
- Whether the model is `retain_after_run: true` or `retain_after_run: false`.
- Free disk space before download.
- Expected transient storage for draft/MTP models, tokenizer files, temporary shards, and converted GGUFs.

### Retention Policy

Default retention is `retain_after_run: false`.

Keep only:

- The current pilot model until the next successful full campaign is complete.
- A small number of active baseline models needed for immediate matched comparisons.
- Any model explicitly approved as a long-lived local baseline.

Do not keep:

- Failed or partial downloads.
- Duplicate quant files for the same model.
- Temporary conversion directories.
- Unused MTP draft models after the runtime-variant run is complete.
- Vast rental model caches after the campaign artifacts have been copied home.

The preferred permanent record is the source URL, exact filename, file size, checksum, runtime config, and score artifacts. Re-downloadable model weights should not be treated as archival data.

### Post-Campaign Cleanup Checklist

After each campaign:

1. Stop the model server and confirm no benchmark/model process is still holding GPU memory.
2. Confirm the run has produced the full artifact set: manifest, receipt, raw outputs, scores, logs, hardware provenance, runtime config, and checksum.
3. Copy or sync Vast artifacts back to the local project before deleting remote files.
4. Delete campaign-local model binaries unless `retain_after_run: true`.
5. Delete partial downloads, temporary shards, conversion workdirs, and MTP draft binaries unless explicitly retained.
6. Record free disk space after cleanup.
7. Mark cleanup status in the campaign notes as `complete`, `retained-by-policy`, or `blocked`.

Never delete benchmark result artifacts as part of model cleanup. If disk pressure requires deleting outputs, archive or compress them first and record what moved.

### RTX 5090 Local Cleanup

Use a single known model cache or staging directory per campaign. Avoid scattering GGUFs across Downloads, repo folders, LM Studio caches, Ollama caches, and ad hoc scratch paths.

For local runs, keep the working set small: the active model, its immediate comparison partner, and any explicitly approved baseline. Everything else should be removed after the corresponding campaign artifacts are verified.

### RTX 6000 Pro Vast Cleanup

Vast instances are disposable. Treat the rental disk as scratch.

Before releasing a Vast instance:

- Confirm every run artifact has been copied back locally.
- Confirm no model server or benchmark process is running.
- Remove downloaded model weights, draft models, temporary conversion outputs, and cache directories from the rental disk.
- Capture final disk usage and cleanup status in the campaign notes.

Do not rely on a Vast instance retaining state for later runs unless the next run is already scheduled and the retained files are listed in the campaign notes.

## Vast Rental Operating Model

The Vast machine is a remote campaign runner, not a second source of truth. The local repo remains the system of record.

### Michael-Owned Vast Host Safety Gate

The RTX 6000 Pro "Vast" target is not always a disposable third-party rental. When using Michael's own Vast Host, it may be listed and may have an active renter. The host-safety rule overrides every benchmark objective:

**Never interrupt, inspect, restart, slow down, or otherwise degrade a current renter.**

Historical Vast Host notes indicate one sticky tenant on GPU1 and GPU0 idle/free at the time of the previous review, but that state is not durable. Before any future run, re-check live Vast state and GPU occupancy from metadata only. Do not assume GPU indexes, container ids, or occupancy from prior notes.

Preferred path for benchmark work on Michael's own host:

1. Use Vast's normal scheduling path by creating a 1x GPU instance on Michael's own machine, or a Vast CLI free own-machine instance where available.
2. Let Vast assign the available non-rented GPU. Do not manually attach to a GPU from the host OS if Vast can schedule the instance.
3. Run benchmarks inside that self-rented instance/container workspace, not directly on the host filesystem.
4. Pull artifacts from the instance/container workspace using the artifact-transfer process below.
5. End only the self-rented benchmark instance after artifacts and cleanup are verified. Do not terminate, reboot, or delist the host as part of benchmark cleanup.

Only start a self-rented host run if all of these are true:

- The machine has exactly one unrented GPU available for a 1x GPU job.
- Vast exposes a valid 1x offer or approved own-machine/free-instance path for the machine.
- The active renter remains on their assigned GPU/container with normal memory, utilization, and temperature behavior.
- Free disk is above the campaign floor before model download. Minimum floor is 50 GB; prefer 100 GB+ for large GGUF campaigns.
- Fan, power-limit, Vast daemon, Docker, IP watchdog, and renter logging services are healthy before the run.

Abort before benchmark start if GPU assignment is ambiguous, the machine has no 1x availability, both GPUs are occupied, or a benchmark container would need host-side privileges that could affect the renter.

Direct host-side execution is a fallback only after explicit approval. If approved, it must be stricter than the self-rent path:

- Prevent new rentals before starting while preserving any current renter.
- Bind the benchmark container/process to the confirmed non-rented GPU UUID only, using `CUDA_VISIBLE_DEVICES` and Docker GPU device constraints where applicable.
- Use a clearly labelled owned benchmark container and workspace.
- Refuse to start if any foreign/non-owned benchmark container is detected on the target GPU.
- Run a guard supervisor that watches rented GPU memory, temperature, utilization, disk headroom, and Vast offer/rental changes.
- Stop only the owned benchmark container on abort. Never touch renter containers or host services.

Prohibited while any renter is active:

- No stopping, restarting, killing, execing into, reading logs from, or copying data out of renter containers.
- No Docker daemon, Vast daemon, NVIDIA driver, kernel, GRUB, network, fan-control, power-limit, or IP-watchdog changes.
- No `apt upgrade`, driver install, CUDA install, kernel update, firmware update, or machine-wide self-test.
- No global GPU configuration changes that could affect the rented GPU.
- No price, min-bid, relist, default-job, or maintenance-window changes without explicit approval.
- No benchmark process on the rented GPU, even briefly.

Thermal and reliability guard:

- Preserve the current host power-limit policy; do not raise GPU power limits for benchmark speed.
- Watch the rented GPU for abnormal temperature, throttling/protection flags, memory movement, or utilization changes attributable to the benchmark run.
- Abort the benchmark if the renter GPU exceeds 85C, reports throttling/protection flags, loses its expected memory allocation, or shows any sustained degradation plausibly caused by the benchmark.
- Keep model downloads, extraction, scoring, and cleanup away from renter data and system directories.
- Keep `localbench-monitor vast-host` running during any approved Vast host campaign. It must use live GPU UUIDs and metadata-only renter state, and it exits with code `2` when the campaign should abort.

This safety gate is based on the operator's local Vast Host runbooks (private, outside this repo) and Vast's hosting guidance that running client contracts must be honored. Vast's own documentation recommends testing a host by renting your own machine or using the CLI to create a free instance on your own machine, which is the preferred pattern for benchmark work here: <https://docs.vast.ai/host/hosting-overview>.

### Paths

Use these paths unless a campaign note explicitly overrides them:

- Remote workspace: `/workspace/local-bench`
- Remote run root: `/workspace/local-bench/runs/campaigns/<campaign_id>/`
- Remote bundle root: `/workspace/local-bench/artifact-bundles/`
- Local raw import root: `<home>\local-bench\runs\imports\vast\<campaign_id>\`
- Local reviewed Vast receipt lane: `<home>\local-bench\cli\runs\vast\`

`runs/` is intentionally ignored by git and should hold raw imported bundles, logs, raw outputs, and scratch material. Reviewed public receipt JSON can be promoted into `cli/runs/vast/*.json`, which is the tracked Vast receipt lane already used by the repo.

### Campaign Identity

Every Vast run gets a campaign id:

`vast-<model_slug>-<quant_or_runtime>-<yyyymmdd-hhmm>`

Use the same campaign id in:

- run directory name
- manifest
- receipt
- score JSON
- log filenames
- transfer bundle
- cleanup note

Do not stitch results from different campaign ids into one ranked row.

### Provisioning Checklist

Before a Vast benchmark starts:

1. Confirm the instance GPU is the intended RTX 6000 Pro target.
2. Record `nvidia-smi`, driver version, CUDA/runtime versions, disk free space, RAM, CPU, OS image, and instance id.
3. Clone or sync the repo to `/workspace/local-bench`.
4. Record the git commit, dirty state, scorecard version, suite SHA, and benchmark command.
5. Set a single model cache/staging location for the campaign and record it.
6. Confirm SSH access from the local Windows machine before starting a long run.

### Artifact Bundle

At the end of a Vast campaign, create one transfer bundle containing only durable benchmark artifacts:

- campaign manifest
- run receipt
- raw model outputs
- score JSON
- logs
- hardware/runtime provenance
- checksums
- cleanup note

Do not include GGUF/model weights, Hugging Face cache, llama.cpp cache, Ollama blobs, conversion scratch, virtualenvs, or build directories.

Suggested remote bundle command, adjusted per campaign:

```bash
cd /workspace/local-bench
mkdir -p artifact-bundles
tar --zstd -cf "artifact-bundles/<campaign_id>.tar.zst" \
  --exclude="*.gguf" \
  --exclude="models" \
  --exclude=".cache" \
  --exclude="hf-cache" \
  --exclude="ollama" \
  --exclude=".venv" \
  "runs/campaigns/<campaign_id>"
sha256sum "artifact-bundles/<campaign_id>.tar.zst" > "artifact-bundles/<campaign_id>.tar.zst.sha256"
```

If the remote image does not have `zstd`, use `tar -czf "<campaign_id>.tar.gz"` instead and record the compression method.

### Pulling Artifacts Home

Pull from the local Windows machine after the bundle and checksum exist on Vast.

Preferred direct pull with OpenSSH `scp`:

```powershell
$CampaignId = "<campaign_id>"
$HostName = "<vast_host_or_ip>"
$Port = "<ssh_port>"
$Remote = "root@${HostName}:/workspace/local-bench/artifact-bundles/${CampaignId}.tar.zst"
$RemoteSha = "root@${HostName}:/workspace/local-bench/artifact-bundles/${CampaignId}.tar.zst.sha256"
$LocalDir = "<home>\local-bench\runs\imports\vast\$CampaignId"
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
scp -P $Port $Remote $LocalDir
scp -P $Port $RemoteSha $LocalDir
```

Alternative when `rsync` is available:

```bash
rsync -av --partial --progress -e "ssh -p <ssh_port>" \
  root@<vast_host_or_ip>:/workspace/local-bench/artifact-bundles/<campaign_id>.tar.zst* \
  /c/Users/Michael/local-bench/runs/imports/vast/<campaign_id>/
```

### Local Verification After Pull

After transfer:

1. Verify the bundle hash locally.
2. Extract into `runs/imports/vast/<campaign_id>/extracted/`.
3. Confirm the manifest, receipt, scores, raw outputs, logs, and provenance are present.
4. Confirm no model binaries were included in the bundle.
5. Compare campaign id across manifest, receipt, directory, and filenames.
6. Promote only reviewed receipt JSON into `cli/runs/vast/*.json`.
7. Rebuild or refresh site data only after the receipt is accepted.

PowerShell hash check:

```powershell
Get-FileHash "<home>\local-bench\runs\imports\vast\<campaign_id>\<campaign_id>.tar.zst" -Algorithm SHA256
Get-Content "<home>\local-bench\runs\imports\vast\<campaign_id>\<campaign_id>.tar.zst.sha256"
```

### Vast Release Gate

Do not destroy or release the Vast instance until:

- local hash verification passes
- local extraction succeeds
- run artifacts are readable locally
- the cleanup note says whether any remote model files were retained or deleted
- the user has enough information to reproduce the run from source URL, quant filename, checksum, runtime config, command, and commit

After the release gate passes, clean remote caches and model weights, then terminate the rental. If the next campaign will run immediately on the same instance, record the retained files and reason before keeping anything.

## Quant Ladder Standard

For a core model family, target at least:

- Practical local quant: Q4 or equivalent
- Middle quality/performance quant: Q6 or equivalent
- Near-lossless local quant: Q8 or best practical equivalent

For derivatives, run matched quant tiers first. Full quant ladders for every derivative should only happen once the matched-quant comparison proves the derivative is strategically useful.

## Wave 0 - Pilot

| Family | Model | Initial quant | Target hardware | Purpose |
|---|---|---:|---|---|
| Gemma 4 12B QAT | `unsloth/gemma-4-12B-it-qat-GGUF` | `UD-Q4_K_XL` | RTX 5090 | Fastest full v2.1 proof run and first clean ranked row |

Pilot rule: run official scoring without speculative decoding or MTP unless it is explicitly stamped as a separate runtime variant and validated for answer equivalence.

## Wave 1 - Gemma 4 12B Family

| Comparison | Models | Target quants | Target hardware | Reason |
|---|---|---|---|---|
| QAT quant preservation | Gemma 4 12B IT QAT vs Gemma 4 12B IT regular | Q4-ish, Q6-ish, Q8-ish where available | RTX 5090 | Show whether QAT preserves quality at practical local quant levels |
| Coding/tuned delta | Gemma 4 12B Coder Fable5 vs Gemma 4 12B base | Matched high quant first, then Q4/Q6 if useful | RTX 5090 | Separate coding tune gains from quant effects |

## Wave 2 - Qwen 3.6 27B Family

| Comparison | Models | Target quants | Target hardware | Reason |
|---|---|---|---|---|
| Quant ladder | Qwen 3.6 27B main/instruct | Q4, Q6, Q8 | RTX 5090 | High-value general local baseline |
| Distillation delta | Qwopus or other Qwen 3.6 27B derivative | Matched Q4, Q6, Q8 where available | RTX 5090 | Measure derivative lift or regression at equal quant tier |
| Optional floor | Same family | Q3 or lower only if needed | RTX 5090 | Show the quality cliff for very compressed local use |
| Quant-format / runtime variant | Qwen 3.6 27B NVFP4 (`nvidia/Qwen3.6-27B-NVFP4`) vs the GGUF base ladder | NVFP4 (4-bit Blackwell FP4) vs Q4/Q6/Q8 | RTX 5090 (Blackwell, native FP4) | Official NVIDIA Blackwell-native FP4 quant; isolates FP4-vs-GGUF capability and runtime practicality. Requires a vLLM or TensorRT-LLM serving path (NOT llama.cpp/GGUF); stamp as a separate runtime row and match the instruct/base tier to the GGUF ladder |

## Wave 3 - Vast RTX 6000 Pro Campaigns

The RTX 6000 Pro is currently a Vast rental target. Treat it as a controlled campaign environment: one model at a time, fixed runtime config, full provenance capture, and no parallel benchmark jobs.

| Family | Models | Target quants | Reason |
|---|---|---|---|
| Qwen 3.6 35B A3B | Base/instruct plus available tuned or distilled variants | Q4, Q6, Q8 | Larger MoE family comparison |
| Qwen Coder | Qwen3 Coder Next and nearest base comparator | Q4, Q6, Q8 where practical | Coding specialist comparison |
| Ornith 35B | Ornith 1.0 35B and nearest base comparator | Q4, Q6, Q8 | Current site candidate needing clean agentic and coding axes |
| Gemma 4 31B | IT/QAT variants where available | Q4, Q6, Q8 where practical | Larger Gemma family comparison |

## Wave 4 - Stretch Candidates

| Model family | Target quants | Hardware | Reason |
|---|---|---|---|
| Qwen3 Next 80B A3B Instruct | Q4 first, Q6 only if budget allows | RTX 6000 Pro Vast | High-end MoE comparison |
| Qwen3 Next 80B A3B Thinking | Q4 first | RTX 6000 Pro Vast | Reasoning-heavy high-end comparison |
| GPT OSS 20B | One strong GGUF quant first | RTX 5090 or RTX 6000 Pro | Strategic open-weight comparator |
| GPT OSS 120B | Q4 only | RTX 6000 Pro Vast | Expensive strategic stretch |
| Devstral / Mistral Small 24B class | Q4/Q6/Q8 if selected | RTX 5090 | Secondary local ecosystem baseline |

## Defer

- Full small-model catalog sweeps until the five-axis campaign is proven and automated.
- Full quant ladders for every derivative until matched-quant comparisons show the derivative is worth deeper coverage.
- Large rental-heavy models that require special serving until the Vast campaign procedure is stable.

## Open Decisions

1. Confirm whether Wave 0 uses only `UD-Q4_K_XL` first or immediately includes a second higher-quality QAT quant.
2. Confirm the exact Qwopus or Qwen 3.6 27B derivative repository to include.
3. Decide whether speculative decoding/MTP is excluded from official rows or published as a stamped runtime variant.
4. Decide the first Vast rental batch size before starting RTX 6000 Pro runs.
5. Decide a local model-cache size cap and a small allowlist of long-lived retained baseline models.
6. Confirm the NVFP4 serving path (vLLM or TensorRT-LLM with Blackwell FP4 support) and answer-equivalence stamping before scheduling the Qwen 3.6 27B NVFP4 row; it does not run under llama.cpp/GGUF, so it is a distinct runtime lane from the rest of the roster.

## Popularity Research Findings - Hugging Face And r/LocalLLaMA

Research date: 2026-06-28.

Popularity should influence the backlog, but it should not override the family-first comparison design. Popular models become useful benchmark candidates when they create a clear comparison lane: quant ladder, derivative-vs-base, agentic/tool-calling contrast, coding contrast, or hardware practicality contrast.

### Hugging Face Signals

Hugging Face's GGUF download sort is a strong local-run signal. The GGUF page showed high download counts for Gemma 4, Qwen 3.6, Qwen 3.6 MTP, Qwen 3.6 35B A3B, and community derivatives. Notable entries included Unsloth Gemma 4 12B IT, Gemma 4 26B A4B, Gemma 4 31B, Qwen 3.6 27B, Qwen 3.6 27B MTP, Qwen 3.6 35B A3B, and Qwopus 3.6 27B Coder MTP.

Hugging Face text-generation download and like sorts also support adding GPT OSS and high-end frontier-open families to the backlog. `openai/gpt-oss-20b` and `openai/gpt-oss-120b` both show high likes and download visibility, while DeepSeek R1/V3/V4, Llama 3.x, Mistral 7B, Qwen 3.x, and GLM appear as broad popularity anchors.

### r/LocalLLaMA Signals

r/LocalLLaMA discussion supports the existing Qwen and Gemma emphasis, but adds three important caveats:

1. Qwopus is polarizing. Some users report better project-level coding behavior than base Qwen 3.6 27B, while others report looping or long-context instability. That makes it a high-value benchmark target, not an assumed upgrade.
2. Gemma 4 QAT and MTP are attractive for speed, but official scoring should separate model quality from speculative decoding/runtime acceleration.
3. Devstral Small 2 24B, GPT OSS 20B, GLM Flash-class models, and Kimi/DeepSeek large models recur as practical or aspirational local candidates. They belong in the backlog, but only some fit the 5090/RTX 6000 Pro campaign budget.

## Popularity-Driven To-Do List

| Priority | Candidate | Comparison lane | Hardware | Action |
|---|---|---|---|---|
| Add to Wave 1.5 | GPT OSS 20B | Agentic/tool-calling and general local baseline | RTX 5090 first | Add one official row after Gemma and Qwen pilot rows; expand to quant ladder only if local GGUF/runtime is stable |
| Add to Wave 1.5 | Devstral Small 2 24B Instruct | Coding and agentic coding contrast against Qwen/Gemma | RTX 5090 | Add Q4/Q6 first; consider Q8 only if runtime remains practical |
| Add to Wave 2 | Qwopus 3.6 27B Coder MTP GGUF | Distilled/tuned Qwen 3.6 27B matched-quant comparison | RTX 5090 | Run matched Q5/Q6 tier first, then Q4/Q8 if behavior is stable |
| Add to Wave 2 | Qwen 3.6 27B MTP GGUF | Runtime variant of base Qwen 3.6 27B | RTX 5090 | Treat as stamped runtime variant, not the same row as non-MTP |
| Add to Wave 3 | Gemma 4 26B A4B IT and QAT | Gemma MoE/QAT quant-ladder comparison | RTX 6000 Pro preferred | Add Q4/Q6 first; Q8 only if rental budget allows |
| Add to Wave 3 | Qwen 3.6 35B A3B MTP | Runtime variant of Qwen 3.6 35B A3B | RTX 6000 Pro Vast | Run only after non-MTP base ladder is clean |
| Add to Wave 4 | GLM Flash / GLM 5.x local quant | Coding and general high-end local comparison | RTX 6000 Pro Vast | Add one practical quant once a stable GGUF/runtime path is confirmed |
| Add to Wave 4 | Kimi K2 / K2 Thinking local quant | Large local/rental stretch | RTX 6000 Pro Vast or larger rental | Keep as stretch; likely expensive and runtime-specific |
| Add to Wave 4 | DeepSeek R1/V3/V4 local quant | High-popularity large-model anchor | RTX 6000 Pro Vast or larger rental | Benchmark only if serving path is stable and rental time is justified |
| Add to calibration queue | Llama 3.1 8B Instruct | Legacy popular baseline | RTX 5090 | One Q4 row is enough unless the site needs a small-model ladder |
| Add to calibration queue | Qwen 3 14B / Qwen 3 8B | Small/medium popular Qwen baseline | RTX 5090 | One Q4 and one Q6 row for calibration |
| Watchlist | Qwythos, Qwable, Heretic, HauhauCS uncensored derivatives | Community derivative popularity | Mixed | Do not prioritize until license, safety posture, and use-case value are clear |

## Revised Approval Slate

Approve the benchmark backlog in this order:

1. Gemma 4 12B QAT pilot: `UD-Q4_K_XL`.
2. Gemma 4 12B QAT vs Gemma 4 12B regular: Q4/Q6/Q8 where available.
3. Gemma 4 12B Coder Fable5 matched-quant comparison.
4. Qwen 3.6 27B base ladder.
5. Qwopus 3.6 27B Coder matched-quant comparison.
6. GPT OSS 20B single practical local row.
7. Devstral Small 2 24B Q4/Q6 coding comparison.
8. Qwen 3.6 35B A3B base ladder on Vast.
9. Qwen Coder Next ladder on Vast.
10. Ornith 35B ladder on Vast.
11. Gemma 4 26B A4B and/or Gemma 4 31B ladder on Vast.
12. Stretch rental rows: GLM, Kimi, DeepSeek, GPT OSS 120B.

## Source Notes

- Hugging Face GGUF model listing, sorted by downloads: https://huggingface.co/models?library=gguf&sort=downloads
- Hugging Face text-generation listing, sorted by downloads: https://huggingface.co/models?pipeline_tag=text-generation&sort=downloads
- Hugging Face text-generation listing, sorted by likes: https://huggingface.co/models?pipeline_tag=text-generation&sort=likes
- Gemma 4 12B QAT GGUF: https://huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF
- Gemma 4 12B IT GGUF: https://huggingface.co/unsloth/gemma-4-12b-it-GGUF
- Gemma 4 12B Coder Fable5 GGUF: https://huggingface.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
- Gemma 4 26B A4B IT GGUF: https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF
- Qwen 3.6 27B GGUF: https://huggingface.co/unsloth/Qwen3.6-27B-GGUF
- Qwen 3.6 27B MTP GGUF: https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF
- Qwen 3.6 27B NVFP4 (NVIDIA, Blackwell-native FP4; vLLM/TensorRT-LLM, not GGUF): https://huggingface.co/nvidia/Qwen3.6-27B-NVFP4
- Qwen 3.6 35B A3B GGUF: https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF
- Qwopus 3.6 27B Coder MTP GGUF: https://huggingface.co/Jackrong/Qwopus3.6-27B-Coder-MTP-GGUF
- GPT OSS 20B: https://huggingface.co/openai/gpt-oss-20b
- GPT OSS 120B: https://huggingface.co/openai/gpt-oss-120b
- r/LocalLLaMA Qwopus discussion: https://www.reddit.com/r/LocalLLaMA/comments/1u1y3i5/how_useful_is_qwopus_compared_to_qwen36_27b/
- r/LocalLLaMA Qwen 3.6 27B quant discussion: https://www.reddit.com/r/LocalLLaMA/comments/1u9wryg/which_is_the_best_qwen_36_27b_quant_gguf_for/
- r/LocalLLaMA Qwopus release thread: https://www.reddit.com/r/LocalLLaMA/comments/1u3zdda/jackrongqwopus3627bcodermtp/
- r/LocalLLaMA Gemma 4 QAT MTP speed thread: https://www.reddit.com/r/LocalLLaMA/comments/1typjmc/120_toks_on_12gb_vram_with_gemma_4_12b_qat_mtp/
- r/LocalLLaMA Gemma 4 26B A4B GGUF benchmarks: https://www.reddit.com/r/LocalLLaMA/comments/1sqrl1l/gemma_4_26ba4b_gguf_benchmarks/
- r/LocalLLaMA GPT OSS 20B agent thread: https://www.reddit.com/r/LocalLLaMA/comments/1mrsoug/gptoss20b_is_in_the_sweet_spot_for_building_agents/
- r/LocalLLaMA GPT OSS comparison thread: https://www.reddit.com/r/LocalLLaMA/comments/1qxuqhe/is_their_a_model_better_than_gptoss_yet/
- r/LocalLLaMA Devstral Small 2 thread: https://www.reddit.com/r/LocalLLaMA/comments/1t06hif/youre_sleeping_on_devstral_small_2_24b_instruct/
