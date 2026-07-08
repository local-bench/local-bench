Historical record: this describes Local Intelligence Index v2.1, superseded by index-v3.0 (see local-bench.ai/methodology). Kept unchanged as the v2.1 methodology record.

# Scoring methodology - Local Intelligence Index v2.1

Status: 2026-06-28. The implementation source of truth is the axis registry in `cli/src/localbench/scoring/axes.py` and the benchmark module registry in `cli/src/localbench/scoring/benchmark_registry.py`.

## Purpose

local-bench ranks local model setups by a repeatable, modular capability profile. The score should answer: "for this local model, quant, runtime, and settings, where does it sit across useful local capabilities, and which capability explains the result?"

The scalar index sorts. The axis profile diagnoses.

## Headline Weights

| Axis | Weight | Default signal |
|---|---:|---|
| Agentic | 50% | AppWorld-C funnel / harness result |
| Knowledge | 15% | MMLU-Pro |
| Instruction-Following | 15% | IFBench |
| Tool-calling | 10% | TC-JSON v1 |
| Coding | 10% | LiveCodeBench proxy |

The current formula is:

`Index = 0.50 Agentic + 0.15 Knowledge + 0.15 Instruction + 0.10 Tool-calling + 0.10 Coding`

Rows are ranked only when all headline axes are present. Partial rows can still appear as diagnostics, but they do not receive a ranked Local Intelligence Index.

## Candidate Modules

The registry can expose additional modules without changing the headline score:

- Math: opt-in until the item set is sufficiently discriminating and license-safe for public distribution.
- Long-context: opt-in until runtime cost, scoring, and local relevance are proven.
- Coding-exec / BigCodeBench-Hard: opt-in until execution sandboxing, reproducibility, and cost controls are hardened.

Candidate modules can graduate only through a versioned scorecard change.

## Scoring Rules

- Each bench reports raw accuracy and chance-corrected score where applicable.
- Axis scores are deterministic from frozen artifacts and submitted outputs.
- Composite aggregation uses the published axis weights for the scorecard version.
- Missing headline axes make a row unranked rather than implicitly zero.
- Confidence intervals should be reported from bootstrap or paired bootstrap methods where item-level data is available.
- Run-to-run repeatability and item-generalization uncertainty should remain separate concepts.

## Governance

- `scorecard-v2.1` locks the current headline weights and ranked-axis set.
- `suite/v1/suite.json` locks item-set membership for local default runs.
- `cli/src/localbench/scoring/benchmark_registry.py` decides which modules are default, opt-in, or out-of-band.
- Any weight change, axis promotion, or candidate graduation must bump the scorecard version and update the site methodology.
