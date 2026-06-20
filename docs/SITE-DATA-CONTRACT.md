# Site data contract — strict scoring + IFBench decomposition (2026-06-21)

Defines what the SITE (`web/`) consumes so the scoring lane (`cli/`) can hand off data that turns the
scoreless catalog into a live Local Intelligence Index. **PROPOSED — field names to be reconciled
with the campaign agent before either side implements.** Per the GPT-5.5 Pro oracle review
(slug `site-progress-nextsteps-2`).

## Lane rule (non-negotiable)
- The **scoring lane (`cli/`) owns scoring.** It produces canonical, strict-scored run JSONs.
- The **site (`web/`) consumes + validates + renders.** It must NOT compute strict IFBench from
  per-item `finish_reason`, and must NOT derive the LII composite/axes in the web layer — it trusts
  the pipeline's `composite`/`axes`.
- `build_data.py` stays deterministic / pass-through; if the optional fields below cannot flow
  through it unchanged, that's a scoring-lane change, not a site change.

## What the site needs to go live
1. The strict-scored Qwen3.5 ladder as **measured, non-demo, standard-tier (ranked)** rows in
   `public/data` (composite + axes already strict). Legacy IFBench scores must be REPLACED by the
   official strict numbers in the fields the build reads — never shipped as "final strict."
2. The IFBench 3-way decomposition, as an **optional** block under the instruction axis score.

## IFBench decomposition (optional, provisional-aware)
Proposed location: `axes.instruction.diagnostics.ifbench_decomposition` in the run/model JSON.

```ts
type IfbenchDecompositionV1 = {
  schema_version: 1;
  status: "provisional" | "final";
  scoring_policy: "strict_nontermination_incorrect";
  denominator: "all_items";
  n_total: number;
  n_terminated: number;
  n_correct_and_terminated: number;
  n_finish_reason_length: number;
  strict_accuracy: Score;       // raw correct_and_terminated / all
  termination_rate: Score;      // terminated / all
  conditional_accuracy: Score;  // correct_and_terminated / terminated
  source_run_sha256: string;
  scorer_commit: string;
  computed_at: string;          // ISO; pass in, do not generate inside scripts
};
```

- `strict = termination × conditional` is a **raw-proportion identity** — the site DISPLAYS it but
  NEVER derives the chance-corrected axis / composite from it.
- The site renders `pending` when the block is absent, `provisional` / `final` per `status`.
- Method note the site will show: *"Outputs that hit the answer-token cap are counted incorrect;
  this prevents non-terminating generations from getting credit for matching required tokens inside
  a runaway response."*

## Handoff mechanism
- **Canonical source = re-emitted run JSONs** (official strict scores in place; per-item
  `finish_reason` retained as audit evidence).
- **Optional sidecar = a handoff MANIFEST** `strict_handoff_manifest.json` (run ids, source hashes,
  scorer commit, expected headline numbers) — the site's integrity test compares the generated
  `public/data` against it. The manifest is an audit aid, NOT the primary data source.

## Open — reconcile with the campaign agent
The field names above are a PROPOSAL. Confirm with the `cli/` scoring owner before either side wires
them, so the emitted shape and the site's zod schema match exactly. Until then the site builds the
3-column display against fixtures, rendering `pending`.
