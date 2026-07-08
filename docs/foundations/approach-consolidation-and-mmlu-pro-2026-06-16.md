# Approach for red-team: branch consolidation (b) + MMLU-Pro knowledge axis (a)

*2026-06-16. Michael authorised (a)+(b) "with best practice; ensure red-team agreement on the approach
before beginning." This doc IS the approach to red-team. Do not execute until a red-team verdict agrees
(or the must-fixes are folded in).*

---

## PART B — Branch consolidation

### Verified topology (read-only, this session)
- **`suite/v1-quant-wedge` is the strict SUPERSET of all 8 other branches** — every branch reports
  `BRANCH-ONLY:0` against it (nothing is unmerged anywhere). The overnight-log `site-overhaul` commits
  (`d60bbf0`, `857361f`, `39c9f5c`, `fbd4c20`, `7b3822b`) are all `contained-in-wedge: YES`.
- Branches (all merged into wedge): `main`, `site-overhaul`, `foundations/suite-v1-research`,
  `refactor/architecture`, `suite/v1-scorers`, `quant-scoring-fixes`, `feat/coding-axis`,
  `feat/longcontext-axis`.
- Worktree `<home>/local-bench-site` is on `feat/longcontext-axis` (`6e79a9d`, merged).
- One stash: `stash@{0} … obsolete v0 web mods (pre-session, superseded by v1 site merge)`.
- 58 uncommitted files on wedge = **(i)** ~50 GENERATED `web/public/data/*` with small score drift
  (e.g. instruction 67.5→66.25; pre-existing, NOT from my scorer commit — belongs to the `site-overhaul`
  scoring-authority refactor workstream), **(ii)** doc edits `PROJECT-HANDOFF.md` + `README.md`,
  **(iii)** untracked work-product `docs/briefs/*` (4 refactor briefs) + `docs/foundations/axis-acquisition-dossier.md`,
  **(iv)** junk `docs/foundations/overnight-claude-output.log`.

### Plan (non-destructive, reversible-first)
1. **Backup tags BEFORE anything**: `backup/2026-06-16/<branch>` for every branch tip + a tag for the
   stash commit + `backup/2026-06-16/wedge-pre-consolidation`. Every later deletion is then 100% reversible.
2. **Clean the tree**: commit work-product (briefs + axis dossier + the two doc edits) to wedge;
   add `*.log` (or that specific file) to `.gitignore`; **LEAVE the ~50 `web/public/data` drift uncommitted**
   — it is generated output owned by the in-flight `site-overhaul` scoring-authority refactor (which has a
   byte-identity gate on exactly these files); regenerating/committing here risks colliding with that work.
3. **Designate `suite/v1-quant-wedge` as the canonical integration branch** and record it in the README/handoff.
   Do NOT rename it now (other headless/agent refs + the worktree assume names; rename = avoidable risk).
4. **Delete the 8 redundant merged branches** with `git branch -d` (refuses if not fully merged = a built-in
   safety check; backup tags also cover it). Keep `main` + `suite/v1-quant-wedge`. Remove the
   `local-bench-site` worktree first IF it is clean (else preserve it), then `-d feat/longcontext-axis`.
5. **Verify**: full cli suite (expect 496) + `web` `npm run build` green on wedge; confirm every backup tag
   resolves; confirm `git log --all` shows no orphaned work outside the tags.

### Guardrails
`main` untouched. No push, no force-push, no merge to main. Backup tags precede every delete. If the worktree
or any branch shows unmerged/uncommitted work I did not expect → STOP and report, do not delete.

### Open question for branch deletion
Deleting the 8 branches is reversible (backup tags) and is standard hygiene, but it is the only
"destructive-ish" step. Options: **(4a)** delete all 8 now [my lean — they are pure redundant ancestors];
**(4b)** keep `site-overhaul` + `foundations/suite-v1-research` as named "live workstream" pointers, delete
the other 6; **(4c)** delete none, only tag + document. Red-team to weigh.

---

## PART A — MMLU-Pro knowledge axis (replace SuperGPQA)

### Why (Michael's call, 2026-06-16)
SuperGPQA's knowledge axis has **~36% bad answer keys** (both frontier anchors agree on a non-gold answer),
which compresses the top of the axis. **MMLU-Pro** (TIGER-Lab, **MIT**) is expert-cleaned (the authors removed
350 wrong-answer + 1,953 false-option + 385 unusable items) → clean keys.

### Trade-off (stated honestly)
MMLU-Pro is older and more widely-trained-on than SuperGPQA → **higher contamination risk**. Mitigation: it is
labelled diagnostic and canaried by the **private genmath sentinel** (the project's contamination tripwire); we
report distance-to-frontier, not a contamination-proof absolute. MMLU-Pro is the *de-saturated* MMLU (frontier
~70–88%, small local ~30–50%) so it **discriminates across the local→frontier range** — it is NOT classic-MMLU
(which we excluded as saturated).

### Plumbing already present (de-risks the build)
`mmlu_pro` was a suite-v0 bench, so its wiring survives: `BENCH_DOMAINS["mmlu_pro"]="Knowledge"`;
`stratum_for_item` has `case "mmlu_pro": subject=category`; the `_scoring` dispatch already routes
`case "mmlu_pro" | "supergpqa"` → `score_mcq_detailed`; `mmlu_pro` is already in `_bench_has_extraction`. The
MCQ scorer handles up to 10 options (and I just fixed its bold + the math FPs). **So the only new code is the
builder + the jsonl + a `suite.json` bench entry + the axis swap + tests.**

### Builder `suite/build_v1_mmlu_pro.py` (mirror `build_v1_supergpqa.py` exactly)
- PEP-723 inline dep `datasets>=2.20`; pin `DATASET_ID="TIGER-Lab/MMLU-Pro"`, a specific `DATASET_REVISION`
  sha, `EXPECTED_LICENSE="mit"`, and the expected row count — **fail the build if HF drifts** (reproducibility +
  license gate, identical to supergpqa).
- `split="test"`; `TARGET_COUNT=400` (matches the current knowledge axis); deterministic `SAMPLE_SEED`.
- **Key integrity (the whole point)**: validate letter↔`answer_index` consistency, `options[gold_index]`
  matches the keyed answer, options non-empty + **no duplicate options**, option count in 2..10; drop & count
  any violation. (MMLU-Pro is pre-cleaned so drops should be ~0 — a near-zero drop count is itself evidence.)
- **Stratify by `category`** (14 categories), deterministic hash order; emit
  `{id:"mmlu-pro-NNN", question, options, answer, category}` (carry `category` so `stratum_for_item` picks it
  up via the item fallback). LF newlines, compact JSON, like supergpqa.
- Print a datasheet (drops by reason, category distribution, options-count distribution).

### Wiring
- `suite.json`: add a `mmlu_pro` bench `{chance_correction_baseline:0.1, decoding:{max_tokens:12288,temperature:0},
  itemsets.standard:{file:"mmlu_pro.jsonl", item_count:400, sha256:<computed>}, template:"templates/mcq_cot.txt"}`
  (reuse the MCQ-CoT template — MMLU-Pro is MCQ-CoT like supergpqa).
- `axes.knowledge.benches`: `["supergpqa"]` → `["mmlu_pro"]` (the replace).
- **Remove `supergpqa` from the active suite** (`benches` + `axes`) but KEEP `suite/v1/supergpqa.jsonl` +
  `build_v1_supergpqa.py` on disk (archival / future probe). `BENCH_DOMAINS["supergpqa"]` can stay (harmless).

### Tests
Builder unit tests (key-validation rejects a bad-key/dup-option row; stratification + sampling are deterministic
for a fixed seed on a tiny fixture); a few real `mmlu_pro` items score correctly through the MCQ dispatch; the
`suite.json` `sha256`/`item_count` match the emitted file; full cli suite stays green.

### Scope boundaries
- **Chance-correction**: MMLU-Pro is mostly-10-option, so the fixed `0.1` baseline is a good approximation;
  exact per-item `1/n` is the deferred finding #5 (collides with the site scoring-authority refactor) — NOT in scope here.
- **MMLU-Redux validation slice**: **DEFER**. It is classic-MMLU (4-option, saturated) so it cannot be a scored
  discriminator; its only role would be a key-quality QA cross-check, which the builder's integrity gate + the
  (gated) anchor probe already cover. Build it later only if we want an independent key-quality audit.
- **Empirical bad-key proof**: the build ASSERTS clean keys (integrity gate + expert-cleaned source). The
  empirical "do anchors agree on a non-gold answer?" rate needs anchor runs on the new items = the **gated
  discrimination probe** (spend + Michael sign-off), NOT part of this build.
- **No spend / no GPU**: the build is an offline HF dataset download + CPU sampling. Anchors/probe are separate + gated.

### Execution
Consolidation: I (Claude) do it directly — careful, reversible git hygiene, not a "build". MMLU-Pro: **codex
GPT-5.5 xhigh implements** (heavy build, per the project model), Claude writes the brief + reviews every diff +
runs the tests. Land on the canonical wedge branch after consolidation.

---

## What I need from the red-team (agreement gate)
1. **Consolidation safety** — is "tag-all → clean tree → delete the 8 merged branches → verify" safe and complete?
   Any way work could be lost? Which branch-deletion option (4a/4b/4c)?
2. **Uncommitted web/public/data** — agree to LEAVE it for the site workstream (vs regen-and-commit vs stash)?
3. **Replace vs repair vs keep-both** — is wholesale SuperGPQA→MMLU-Pro right, or should we *repair* SuperGPQA
   (drop the frontier-agreed-bad items) and/or keep both and let the probe weight them? (Michael chose replace.)
4. **Contamination** — is MMLU-Pro acceptable for the knowledge axis given clean keys + the sentinel canary,
   or does the contamination regression vs SuperGPQA outweigh the key-quality win?
5. **Design** — 400 items, stratify-by-category-only, reuse mcq_cot template, drop supergpqa from the active
   suite: anything wrong or missing? Any wiring/scoring edge I've missed (the suite loader, the runner, CIs)?
6. **Anything else** that would corrupt the suite, mis-measure, or lose work.

End with a clear **GO / GO-WITH-FIXES / NO-GO** and the must-fix list.

---

## RED-TEAM VERDICT (GPT-5.5 xhigh, read-only) + folded fixes — 2026-06-16

**Verdict: Part B = GO-WITH-FIXES, Part A = GO-WITH-FIXES.** It independently confirmed the load-bearing
facts (wedge superset via empty `git log wedge..<branch>` for all 8; worktree clean; MMLU-Pro plumbing exists;
runner consumes top-level `benches` so BOTH `benches` + `axes` must change; MMLU-Pro dataset IS MIT on HF).
Fixes folded into execution:

**Part B**
- **Delete count = 7 not 8** (I miscounted `main`). FINAL DECISION: delete only the 4 unambiguously-dead merged
  feature branches (`refactor/architecture`, `suite/v1-scorers`, `quant-scoring-fixes`, `feat/coding-axis`);
  KEEP `main` (baseline), `suite/v1-quant-wedge` (canonical), `site-overhaul` (active site workstream +
  possibly referenced by the headless resume task), `foundations/suite-v1-research` (research lineage), and
  `feat/longcontext-axis` (the live worktree branch — deleting it needs worktree removal = avoidable disruption).
  All 9 + the stash are backup-tagged `backup/2026-06-16/*`, so any can be resurrected. (Conservative because
  parallel agents/automation may reference names; Michael can prune the kept-3 later.)
- **Ran the exact safety checks** codex's sandbox blocked: `git rev-list --left-right --count wedge...<branch>`
  = BRANCH-ONLY:0 for all 8; 11 unreachable commits exist but are git internals (stash etc.) untouched by
  `branch -d` of merged branches; backup tags verified to resolve.
- **Dirty tree handled honestly**: the real dirt is 7 `web/public/data` qwen run-JSONs (score drift, owned by
  the in-flight site scoring-authority refactor) + 2 doc edits (`PROJECT-HANDOFF`, `README`) — NOT mine; the
  other ~43 "modified" files are phantom (mtime-only). **Decision: LEAVE them untouched** (non-destructive;
  the site workstream reconciles its own generated data) and do NOT claim a clean tree. Only additive
  work-product (briefs, dossier, this doc) is committed.

**Part A (MMLU-Pro) — folded into the codex build brief**
- **Normalize `N/A` filler options BEFORE validation** (MMLU-Pro pads to 10 with "N/A"); validate the real
  options + answer index against the trimmed list.
- **Chance baseline = selected-set mean `1/len(real_options)`** (paper: avg 9.47 options, ~17% have <10), NOT
  fixed 0.10. Store that computed value as the bench `chance_correction_baseline` (stays in-architecture;
  exact per-item is the deferred #5).
- **Update supergpqa-specific v1 tests + web fixtures** (`test_v1_supergpqa_axis.py`, `test_v1_supergpqa_items.py`,
  `test_web_build_data.py`) and **make the v1 run path explicit** (`discover_suite_dir()` defaults to `suite/v0`).
- **Replace, but keep SuperGPQA archival**; the gated probe later decides whether to also repair-and-keep it
  (drop frontier-agreed bad-key items). Contamination acknowledged → MMLU-Pro is diagnostic + sentinel-canaried.

