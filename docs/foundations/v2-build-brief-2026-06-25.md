# v2.0 build brief — agentic-led composite (Codex implementation)

**For:** Codex (implementer). **Manager/reviewer:** Claude. **Date:** 2026-06-25.
**Read first:** `docs/foundations/agentic-led-composite-spec-2026-06-24.md` — the **DECISION block at the
top is LOCKED and authoritative** (owner + GPT-5.5 red-team). This brief is the *how*; that spec is the
*what/why*. Do not re-litigate the weight (0.50/0.25/0.25) or the name ("Local Intelligence Index").

## 0. Goal & guardrails
Implement the v2.0 agentic-led composite **on a branch, in parallel with a running benchmark campaign**,
so that when agentic coverage completes it's just "recompute + rebuild + QA". Validate the CODE now
against the partial agentic data already on disk.

- **Branch:** `git checkout -b composite-v2` from current HEAD (carries the uncommitted working-tree
  changes — staged board edits + build_agentic fix + the spec/brief — bring them onto the branch and
  commit them there). **Commit locally only; NEVER push.** Small, reviewable commits.
- **Do NOT disturb the running campaign:** do not touch `cli/runs/**`, do not run any GPU work, do not
  start/stop `llama-server`, do not run the agentic funnel. CPU build + unit tests only.
- **`cli/runs/board/board_v1.json` MUST stay byte-identical** (the frozen v1 artifact; historical). v2
  produces a NEW `board_v2.json`; v1 is retained untouched.
- If a design ambiguity materially affects the HEADLINE number and isn't resolved by the spec, **STOP
  and write the question into your summary** rather than guessing. This is the site's headline metric.

## 1. The locked formula (from the spec DECISION block)
```
A* = clamp(AppWorld-C_ASR / 50  * 100, 0, 100)     # agentic; ceiling 50 = frozen EXTERNAL anchor
K* = clamp((MMLU_Pro_acc - 10)  / 90 * 100, 0, 100) # knowledge; chance-corrected (10-choice)
I* = clamp(IFBench_acc, 0, 100)                      # instruction
Local Intelligence Index = 0.50*A* + 0.25*K* + 0.25*I*
```
Per-raw-point influence (sanity check for review): +1 ASR ≈ +1.0 index, +1 IFBench = +0.25, +1
MMLU-Pro ≈ +0.278. A model is **ranked only if all three axes are present**; otherwise it is
`agentic-pending` (shown, not ranked — no fabricated 0).

## 2. Architecture decision (how agentic enters the composite) — DECIDED, implement as-is
The agentic ASR is already aggregated per board-slug by `web/build_agentic.py` (best-variant selection,
already fixed: slug -> the run matching the board best_run_id quant). Use that as the agentic source.

1. **Agentic source = the best-variant ASR per slug** from `build_agentic` (do NOT average quants; do
   NOT re-run anything). A slug with no best-variant agentic run = `agentic-pending`.
2. **Apply AXIS_TRANSFORMS** (see §3.1) to produce A*, K*, I* per model.
3. **Composite** = weighted mean per §1, computed wherever the headline composite is built today
   (trace from `localbench.scoring.axes` consumers -> `board_scoring.py` / `web/build_data*.py`).
4. **Provenance:** register AppWorld-C in the scorecard (scorer_version + frozen harness identity, §3.2)
   so a v2 run is self-describing — even though the ASR is sourced via build_agentic, not the K+I run
   pipeline. (Provenance ≠ computation; both required.)
5. **board_v2.json**: new frozen artifact produced by the v2 board builder; mirror how board_v1.json is
   produced/consumed (the web "pure-renderer board intervals" override path in build_data.py must read
   board_v2 on this branch).

## 3. File-by-file plan (the spec's 8 requirements mapped)
### 3.1 `cli/src/localbench/scoring/scorecard.py`
- `SCORECARD_VERSION = "scorecard-v2.0"`.
- Add a frozen **`AXIS_TRANSFORMS`** registry: per axis `{kind:"linear_reference_range", floor, ceiling,
  clamp:true, raw_unit}` — knowledge (10,100,"percent_accuracy"), instruction_following
  (0,100,"percent_accuracy"), agentic (0,50,"percent_asr").
- Add `axis_transforms_digest()` and embed the full transform payload into `scorecard_identity()`
  (REQ #1 — the biggest catch: a future ceiling 50->60 must change the scorecard id, not silently
  re-score history).
- Add `appworld_c` to `SCORER_VERSIONS`. Add an **agentic harness identity** block to the scorecard
  (REQ #3): AppWorld version + dataset-split digest, evaluate() version, agent-loop version,
  system-prompt digest, tool-contract digest, max-steps/wall/tokens, generation params, backend +
  quant policy, container/image digest. Source these from the agentic run manifests under
  cli/runs/agentic/*.scored.run*.json (read, don't run) and/or the funnel config; where a value isn't
  available yet, use an explicit `"unknown@v2.0-draft"` placeholder constant (flagged) so the hash is
  stable but honest — list these placeholders in your summary for me to fill before final freeze.

### 3.2 `cli/src/localbench/scoring/axes.py`
- agentic axis -> role `headline`, weight **0.50**, benches `("appworld_c",)` (REQ #2: a NEW measured
  bench, NOT a relabel — keep bfcl/bfcl_multi_turn out of the headline; either retire them from web
  display or leave them experimental & unused). knowledge/instruction -> weight **0.25** each. math /
  long_context / coding stay candidate/experimental at 0.0. `_validate()` must still pass (headline
  weights sum to 1.0; only headline carry non-zero).
- Update the docstring + any derived helpers (domain_weights, web_composite_weights,
  web_source_bench_groups, etc.) consistently; `appworld_c` must map to display "Agentic".

### 3.3 Composite computation (scaling)
- Implement the AXIS_TRANSFORMS application (clamp/linear) as a small pure function and use it wherever
  the composite + per-axis normalized values are computed (board scorer + web build). Raw values stay
  available alongside normalized (REQ #5).

### 3.4 `web/` (presentation)
- Render the new composite; the agentic mini-bar flips **purple -> green** (`bench-purple` ->
  `bench-accent`/the headline tone) since it's now a headline axis (the staged `agentic-column.tsx`
  edit currently uses purple — change to the headline tone).
- The staged board edits already in the tree (Hardware column, Cost removed, User stub) stay.
- Show **raw + normalized axis + index + a CI/tie band** (REQ #5). Methodology page: the compensatory-
  composite note (REQ #6), the **validation gates as a confidence signal** (coverage / repeatability
  <=0.5pp / discrimination P90-P10>=8pp / rank-stability — REQ #7), contamination note (REQ #8).
- **Anchors:** same formula, shown, but **no Local Rank** (label "reference, not local-ranked"; REQ #4).
- Update `web/lib/schemas.ts` / data contracts as needed for normalized values + the index name stays
  "Local Intelligence Index".

### 3.5 Tests
- Update existing scoring/web tests for the new weights, transforms, scorecard v2.0, and composite.
- Add unit tests: the transform fn (boundaries/clamp), the composite arithmetic (the §1 worked example),
  the agentic-pending (unranked-when-missing) rule, and a scorecard-identity test proving the transform
  digest is included (changing a ceiling changes the id).

## 4. Validation against partial data (do this; it proves the code)
Current agentic coverage on disk: `qwen3-6-27b` best-variant **Q6_K ASR 14.58%**, `gemma-4-31b-it` Q4
**11.46%** (others agentic-pending). Build a **partial** board_v2 and confirm:
- `qwen3-6-27b`: A* = 14.58/50*100 = **29.16**; K*/I* from its real MMLU-Pro/IFBench (chance-corrected
  K); Index = 0.5*29.16 + 0.25*K* + 0.25*I*. Print the computed Index + the three normalized axes for
  me to sanity-check.
- `gemma-4-31b-it`: A* = 22.92; same composite.
- Every model WITHOUT an agentic best-variant score = agentic-pending (unranked), NOT a 0.
- `npm run typecheck` + `npm run build` (web) pass; `pytest` (cli) green.

## 5. Deliverable (return to me)
A summary listing: the branch name + commit list; every file changed; the partial board_v2 numbers
(qwen + gemma Index + normalized axes); any `"unknown@v2.0-draft"` harness-identity placeholders you
left for me to fill; any design ambiguity you hit; and confirmation board_v1.json is byte-identical +
nothing under cli/runs was touched + no push. Do NOT declare the headline "done" — it's partial until
campaign coverage lands; this is the code + a partial validation.
