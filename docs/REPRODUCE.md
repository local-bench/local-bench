# Reproducing a local-bench run

Updated 2026-07-04. The active headline is **Local Intelligence Index v2.1**:

```text
0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.10 Coding
```

Weights and axis membership are defined in `cli/src/localbench/scoring/axes.py`. Runnable module defaults are defined in `cli/src/localbench/scoring/benchmark_registry.py`.

## Prerequisites

- Python 3.11+ and the CLI: `pip install local-bench-ai` (or from a source checkout: `pip install -e cli`)
- A GGUF model plus llama.cpp for the pinned `bench` path, or an OpenAI-compatible
  chat endpoint for the bring-your-own `run --endpoint` path
- For ranked local runs: capped-thinking lane settings, temperature 0, enough context for the selected modules
- For AppWorld-C: the AppWorld agentic extra and sandbox setup
- For BigCodeBench-Hard: Docker sandbox setup; this remains opt-in

## 0. Start Safety Monitors

Before starting a benchmark campaign, start a monitor loop for the machine that will run it. The monitor writes JSONL records and exits with code `2` when the campaign should abort.

Local RTX 5090:

```powershell
localbench-monitor local `
  --label rtx-5090 `
  --target-name-contains "RTX 5090" `
  --disk-path <home>\local-bench `
  --out <home>\local-bench\runs\monitors\rtx-5090.jsonl
```

Michael-owned Vast RTX 6000 Pro host, read-only guard from the local machine:

```powershell
localbench-monitor vast-host `
  --label vast-rtx6000-pro `
  --ssh-target michael@<vast-host> `
  --machine-id <vast-machine-id> `
  --target-gpu-uuid <live-unrented-gpu-uuid> `
  --protected-gpu-uuid <live-renter-gpu-uuid> `
  --protected-min-memory-mib <current-renter-memory-floor> `
  --expected-available-gpus 1 `
  --out <home>\local-bench\runs\monitors\vast-rtx6000-pro.jsonl
```

The Vast monitor samples `nvidia-smi`, disk headroom, and read-only Vast occupancy metadata over SSH. Use `--occupancy "<live-vast-occupancy>"` only when supplying captured status manually instead of `--machine-id`. It must not be used as permission to start a host-side benchmark. Prefer a 1x self-rented Vast instance on Michael's own machine; if direct host-side execution is ever explicitly approved, keep this monitor running and bind the benchmark process to the live unrented GPU UUID only.

## 1. Fetch and inspect the public suite

```bash
localbench fetch-suite \
  --site https://local-bench.ai \
  --suite suite-v1-text-code-agentic-5axis-v1 \
  --accept-suite-terms

localbench suite inspect --suite suite-v1-text-code-agentic-5axis-v1
```

`fetch-suite` verifies the public suite manifest and prints the cached suite
directory. Keep that path for `submit run --suite-dir`.

## 2. Preferred GGUF path: launch the server with `bench`

```bash
localbench bench \
  --runtime llama.cpp \
  --model-file <model.gguf> \
  --model-id <model-slug> \
  --ctx 32768 \
  --seed 1234 \
  --out runs/my-bench
```

Use this path when you want the strongest provenance: the CLI launches the
llama.cpp server with pinned serving flags, then writes a run directory.

## 3. Bring your own OpenAI-compatible endpoint

```bash
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model <model-name-the-server-reports> \
  --lane capped-thinking \
  --tier standard \
  --publishable \
  --sampler-seed 1234 \
  --out runs/my-run.json
```

Use this path for LM Studio, ollama, vLLM, or any other OpenAI-compatible
server. `--bench all` resolves from the benchmark module registry. If a module
is unavailable, the run records that axis as not measured instead of fabricating
a score.

## 4. Submit a finished run

```bash
localbench submit run \
  --run runs/my-run.json \
  --suite-dir <cached-suite-dir-shown-by-fetch-suite>
```

On first use, `submit run` creates `~/.localbench/submitter_ed25519.pem`; that
public key is the leaderboard identity. The maintainer reviews every submission
before anything publishes.

## 5. Coding modules

The standard Coding axis uses `lcb`, an execution-free LiveCodeBench output-prediction proxy. It is fast enough for regular local submissions.

The heavier code-generation benchmark remains opt-in:

```bash
localbench code \
  --endpoint http://localhost:8080/v1 \
  --model   <model-name> \
  --image   bigcodebench/bigcodebench-evaluate@sha256:<digest> \
  --tier    standard \
  --out     runs/my-coding-exec.json
```

BigCodeBench-Hard should be treated as a diagnostic or expansion module until its sandbox lane is fully hardened and cheap enough for routine runs.

## 6. Build board and site data

```bash
localbench board --no-check-parity
python web/build_data.py
```

The board and web build derive weights from the registry. Ranked rows require all current headline axes; partial rows still display measured axes but are not rank-comparable.

## 7. Compare runs

```bash
localbench compare runs/q8.json runs/q4.json --out cmp.json
```

Comparisons are meaningful only within the same suite, scorecard, lane, and module coverage. Report paired deltas and confidence intervals rather than treating a small point gap as a universal ranking.
