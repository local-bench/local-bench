# `localbench check`

`localbench check` compares one local GGUF artifact with the pinned reference for
its model family. It does not produce an absolute cross-family score. The useful
output is the paired difference: what the candidate kept, lost, gained, or changed
relative to the reference on the fixed `check-set-v1` edition.

## Basic use

```text
localbench check model-Q5_K_M.gguf --parent qwen36-27b-reference-v1
```

The command requires a signed local reference-edition bundle for a real run. A
reference edition pins the family, reference artifact, tokenizer, prompt template,
check-set edition, and execution edition. Candidate and reference results are only
paired when those editions match.

`--dry-run` uses deterministic fixture generations and never loads a model:

```text
localbench check model-Q5_K_M.gguf --parent dry-run-reference-v1 --dry-run --out check-dry-run
```

Useful flags:

- `--parent ID` records explicit lineage and permits exact-quant classification.
- `--reference-bundle PATH` loads an immutable signed reference edition.
- `--reference-public-key HEX` selects the trusted bundle signer.
- `--out DIR` creates a new run directory.
- `--resume DIR` explicitly resumes that exact plan. There is no automatic resume.
- `--dry-run` executes the whole pipeline with deterministic fixtures and zero GPU.

## Run directory

A completed run contains immutable generation rows (`items.jsonl`), offline grades,
paired measures and intervals, the artifact-class verdict, KLD status, controlled
performance measurements, naturalistic per-item telemetry, the complete check
record, and `receipt.json`. The receipt hashes every run artifact so offline copies
can be checked for accidental or deliberate changes.

Infrastructure failures invalidate the run or require explicit resume. Model and
protocol failures score wrong. The command never reruns an item because of its
outcome and never reduces the denominator.

## Editions and verdicts

Exact quants use the fidelity vocabulary: `reference-faithful`, `drift`, `degraded`,
`broken`, or `inconclusive`. Fine-tunes, distillations, and merges instead receive a
four-state per-area delta profile: resolved gain, resolved loss, practical
equivalence, or unresolved. Unsupported areas are excluded only by reference-family
policy; a capability missing only from the candidate is a failure.

KLD is separate from the verdict. It is reported as `in-band`, `out-of-band`, or
`unavailable`, and is unavailable when the pinned reference weights are not local.

## Draft manifest

The bundled manifest is deliberately marked `"draft": true`. Its selections,
authored state machines, sanity gates, hashes, policies, and preregistration are
complete, but the edition is not frozen until content review accepts it. A draft
manifest is suitable for deterministic dry-run and review; it must not be presented
as a frozen public edition.
