# Reproducing a local-bench run

Updated 2026-06-28. The active headline is **Local Intelligence Index v2.1**:

```text
0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool calling + 0.10 Coding
```

Weights and axis membership are defined in `cli/src/localbench/scoring/axes.py`. Runnable module defaults are defined in `cli/src/localbench/scoring/benchmark_registry.py`.

## Prerequisites

- Python 3.11+ and the CLI: `pip install -e cli`
- An OpenAI-compatible chat endpoint serving the model
- For ranked local runs: capped-thinking lane settings, temperature 0, enough context for the selected modules
- For AppWorld-C: the AppWorld agentic extra and sandbox setup
- For BigCodeBench-Hard: Docker sandbox setup; this remains opt-in

## 1. Inspect the suite

```bash
localbench suite inspect --suite-dir suite/v1
```

The full repo suite includes MMLU-Pro, IFBench, TC-JSON v1, LCB, AppWorld-C membership, math, long-context, BFCL, and BigCodeBench-Hard. The installable `core-text-v1` bundle is still the smaller public bundle and does not yet include every modular itemset.

## 2. Run the standard modules

```bash
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model   <model-name-the-server-reports> \
  --suite-dir suite/v1 \
  --lane    capped-thinking \
  --tier    standard \
  --out     runs/my-run.json \
  --accept-suite-terms
```

`--bench all` resolves from the benchmark module registry. With the full repo suite it runs MMLU-Pro, IFBench, TC-JSON v1, LCB, and the AppWorld-C agentic attempt. If a module is unavailable, the run records that axis as not measured instead of fabricating a score.

## 3. Coding modules

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

## 4. Build board and site data

```bash
localbench board --no-check-parity
python web/build_data.py
```

The board and web build derive weights from the registry. Ranked rows require all current headline axes; partial rows still display measured axes but are not rank-comparable.

## 5. Compare runs

```bash
localbench compare runs/q8.json runs/q4.json --out cmp.json
```

Comparisons are meaningful only within the same suite, scorecard, lane, and module coverage. Report paired deltas and confidence intervals rather than treating a small point gap as a universal ranking.
