# First benchmark acceptance checklist - 2026-06-29

This checklist defines the gates before a first benchmark result is publishable, and before online submission/pipeline work may resume. It intentionally does not change `suite/v1/suite.json` or silently publish around the pending lane-spec defect.

## Gate A - Publish gate

The result is trustworthy enough to show only when all P0 items pass.

1. **Lane/sampler frozen** - Record lane name and all lane-defining params: hardware class, runtime, context length, capping policy, sampler sequence, `top_k`, `temperature`, seed, batch size, prompt-cache, slot count, flash-attn, KV precision, RoPE, stop tokens, max tokens, and timeout. Do not publish a first result under ambiguous `temperature=0`-only settings unless it is clearly labelled non-final/calibration-only.
2. **Model-system identity complete** - Record model name and source, model-file SHA256, GGUF/quant metadata, quantization type, tokenizer hash, chat-template hash, runtime engine/version/commit, build flags, GPU/VRAM, driver, CUDA/runtime versions, and OS.
3. **Runner and scorer provenance pinned** - Record repo commit, dirty-tree status, CLI/package versions, lockfile hash, runner/scorer config hashes, extractor version, suite manifest hash, and scorecard id. Block publish if the tree is dirty, unless a patch hash is attached that reconstructs the run.
4. **Complete artifact bundle exists before scoring** - Preserve rendered prompts, raw outputs, extracted answers, per-item metadata, token counts, stop reasons, log excerpts, run manifest, scorer output, validation report, and a top-level manifest hashing every file. Scoring must be reproducible from the bundle offline, with no site or D1 contact.
5. **Prompt-template fidelity** - Hash the template and fully rendered prompts. Confirm no per-item edits, no ground-truth leakage, correct chat template/system prompt, and no pre-model truncation.
6. **Invalid/refusal/truncation accounting explicit** - Define how refusal, format failure, missing final answer, leaked reasoning, truncation, timeout, OOM, empty output, and duplicate output count in the denominator. Do not silently drop failed items; show invalid, format, and truncation rates next to scores.
7. **Scorer determinism proven** - Run the scorer twice from the same bundle and produce byte-identical score JSON, or document timestamp-only diffs. Tie-breaking, rounding, weighting, and normalization must be deterministic.
8. **Reproducibility demonstrated** - A clean checkout reproduces the published score and row hashes from the artifacts.
9. **Statistical sufficiency visible** - Show exact expected, attempted, valid, and invalid item counts per axis plus confidence intervals. Do not use `files=11` as the denominator. Show per-axis scores and uncertainty so rank differences are not overclaimed.
10. **Tamper-evidence** - Create a top-level release manifest hashing the suite manifest, runner config, model file, prompt template, rendered prompts, raw transcripts, extracted answers, score output, board row, and public bundle. The public board row should carry bundle and scorecard hashes.
11. **No unrecorded manual path** - No one-off fixes outside runner/scorer, manual transcript edits, hand-corrected answers, post-hoc item exclusions, rerun-because-underperformed, or prompt tweaks after seeing failures.
12. **Redaction and license pass** - Public artifacts contain no local usernames, Windows paths, hostnames, secrets, private-repo URLs, or identity-bearing logs. Confirm dataset/model license permits the exact public release.

## Gate B - Pipeline-unblock gate

Online submission and pipeline work may resume only when Gate A passes and all of these are true:

- The first bundle validates under the future submission-bundle validator.
- The validator emits a deterministic accepted-result projection containing every public-board field.
- D1 can be designed as index rows pointing to immutable bundle hashes; D1 is not scoring truth.
- Trust labels are frozen as conservative labels such as `community re-scored` and `spot-reproduced`, not `verified`.
- The format represents both `origin: project_anchor` and `origin: community_submission`.
- The same scorer path is used for project and community artifacts.
- Bridge test with no D1: `validate-submission-bundle` plus `rescore-bundle` on the first anchor bundle produces `accepted_result_projection.json` that exactly matches the public board row.
