# local-bench

Community quality leaderboard for local AI setups. The headline score is the **Local Intelligence Index v2.1**: a modular, repeatable benchmark suite weighted as 50% Agentic, 15% Knowledge, 15% Instruction-Following, 10% Tool calling, and 10% Coding.

The standard run stays practical for local hardware: MMLU-Pro, IFBench, TC-JSON v1, and the lightweight LiveCodeBench output-prediction coding proxy run through the normal HTTP path; AppWorld-C is the agentic lane. Heavier modules such as BigCodeBench-Hard, long-context, and math remain opt-in or diagnostic until their lanes are hardened.

## Layout

- `cli/` - Python benchmark runner, scoring registry, board builder, and submission client
- `suite/` - versioned suite definitions, item sets, prompts, and scorers
- `web/` - leaderboard site and static data projection
- `docs/` - reproduction notes, methodology history, licensing, and threat model

## Quickstart

```bash
pipx install localbench
localbench fetch-suite --suite core-text-v1 --accept-suite-terms
localbench run \
  --endpoint http://localhost:8080/v1 \
  --model <model-name> \
  --lane capped-thinking \
  --tier standard \
  --out runs/my-run.json
```

`fetch-suite` currently verifies the installable minimal public bundle. The full repo `suite/v1` contains the broader modular suite, including the coding proxy and opt-in expansion benches.

## Status

Pre-launch methodology work (2026-06). Active scoring source of truth: `cli/src/localbench/scoring/axes.py` plus `cli/src/localbench/scoring/benchmark_registry.py`.
