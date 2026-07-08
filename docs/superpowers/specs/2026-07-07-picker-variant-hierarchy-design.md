# Browse picker — family-tree variant hierarchy (design)

Date: 2026-07-07. Brainstormed by Claude + GPT-5.5 Pro (oracle, session
`picker-variant-tree-v2`); approved by Michael 2026-07-07 with one scope addition:
**coverage must span ALL catalogued base models, not just flagships.**

## Problem

Browse mode today: type toggle → Lab → flat model list → quant. Derivatives are listed
under the fine-tuner's org (Qwopus under "Jackrong"), so from Qwen a user cannot see the
variants of Qwen3.6-27B. The catalog also under-represents variants: only 4 true
derivatives at top level; Qwen3.6-27B alone has ~20 real HF fine-tunes and 3 distills
trapped in the nested `distills[]` array the picker never renders. The site's stated
first-class purpose is fine-tune-vs-base deltas; the front-door picker hides them.

## Approved shape ("B+ family tree")

Browse mode only. Popular and Paste modes are untouched.

**Flow: Base lab → family → variant (or explicit "Original release") → quant.**

```
[Base lab: Qwen v]  [Search model / creator / repo...]      [Quant: Auto v]

Qwen3.6-27B — Original + 4 variants · 27B · popularity
  o Original release                          best fit: Q4_K_M
  o Qwopus3.6 27B v2 MTP                      Fine-tune · by Jackrong
  o Qwen3.6-27B-MTP-pi-tune                   Fine-tune · by bytkim
Qwen3-14B — base only, no curated variants yet
```

### Locked interaction decisions

1. **"Original release" is a first-class selectable row inside each family.** The family
   header row is never ambiguously "select base" vs "expand"; selecting the original is
   always explicit. A base with no variants states it plainly: "base only — no curated
   variants for this base yet" (+ Paste HF repo as escape hatch).
2. **Scaling rules:** 0 variants → plain row + empty-state line when selected;
   1–3 variants → auto-expanded; 4–10 → collapsed behind "N variants"; 10+ → top 5
   inline + "show all variants" expansion. Per-family UI cap before show-all: 5.
3. **Lineage wins over author org.** Derivatives whose base is in catalog appear ONLY
   under the base's family. Fine-tuner orgs with no base models drop out of the lab
   dropdown, which is renamed **"Base lab"**. Derivatives whose base is NOT in catalog
   remain flat rows under their own org (until the base is added).
4. **Search box is mandatory** (client-side filter over id/display name/org/gguf repo).
   Searching "Jackrong" or "Qwopus" must surface the variant and jump/expand to its
   family. This is the compensating control for removing fine-tuner orgs from the
   dropdown.
5. **All/Base/Fine-tunes toggle is dropped.** Hierarchy + search subsume it.
6. **Variant chips:** `Fine-tune` / `Distill` / `Merge` / `Official variant`, plus
   "by {org}". Officialness is attribution, not lineage: derived as
   `variant.org === base.org` (no new model_kind value). Devstral, Phi-4-reasoning,
   gemma-3n-E2B present as "Official variant".
7. **VRAM honesty per row:** each selectable row shows its best-fitting quant for the
   selected VRAM ("best fit: Q4_K_M") or "no listed quant fits {N} GB". Never silently
   fall back to a quant that does not fit (fixes today's `found.quants[0]` fallback).
8. **Merges** (base_model as array): listed under every catalogued base they declare;
   canonical identity/state uses the first declared base; secondary rows read
   "Merge · also based on {other}".
9. **Recipe header states lineage:** "Benchmarking Qwopus3.6 27B v2 MTP — fine-tune of
   Qwen3.6-27B · by Jackrong". Original: "Original release".
10. **Variant sort within a family:** local-bench ranked score when present → has a
    quant fitting selected VRAM → HF downloads → name. Never label popularity as
    "best"; popularity disclaimer (repo-level) stays.
11. **A11y/mobile:** family headers are buttons with `aria-expanded`; selectable rows
    are a radio-group-like list (no fake listbox nesting interactive elements). Mobile:
    one family expanded at a time; keep the existing max-height scroll container.

### Out of scope (deferred)

- URL/query-param deep-linking into the picker state (fast follow).
- "Variants only" secondary view (search covers it; revisit on demand).
- Model-page changes (already have vs-base comparisons).

## Data plan (ALL models — owner requirement)

The UI is empty without catalog coverage. Every catalogued base gets a discovery pass;
the quality gate decides which bases gain variants. Honest empty states cover the rest.

1. **Backfill `model_kind`** on the 4 existing derivatives (Qwopus3.6 v2 MTP =
   finetune; Devstral, Phi-4-reasoning, gemma-3n-E2B-it = finetune with official
   attribution derived from org).
2. **Promote nested `distills[]`** to full catalog entries where verifiable (license +
   lineage + GGUF repo + >=1 recipe-grade quant with real file size). Drop or keep
   nested-only when not benchable — the picker never renders disabled clutter.
3. **Extend `scripts/catalog_refresh.py` discovery:**
   - `--mode discover-finetunes` seeds from BOTH nested `distills[]` AND the per-base
     HF probes (`filter=base_model:finetune:{id}`, plus merge/adapter probes tolerated
     as tag noise) across **every** catalogued base.
   - Per-base cap: default 2; per-base overrides via a config block in the script or a
     JSON sidecar (e.g. Qwen/Qwen3.6-27B: 8). Wave cap raised to ~24; run multiple
     waves until discovery is dry (each wave is a reviewed proposal, never auto-applied).
   - Quality gate unchanged: >=2k monthly downloads or >=50 likes, resolved license,
     declared lineage, >=1 recipe-grade quant with real file size from the actual GGUF
     repo listing. Rejects listed with reasons in the report.
4. **Review workflow unchanged:** report → diff proposal → apply → rebuild → web tests.
   Expected outcome: roughly 10–20 new curated variant entries initially; every one is
   a benchable, submittable target.

## Architecture

- **`web/lib/onramp.ts`:** new pure grouping layer, e.g.
  `browseFamilies(catalog, { lab, search, vramGb }): readonly Family[]` where
  `Family = { base: OnrampCatalogModel, variants: readonly Variant[] }` and
  `Variant = { model, kind, official, alsoBasedOn }`. Derivative = base_model resolves
  to an in-catalog id (existing `isDerivativeModel` semantics) — entries whose
  base_model points outside the catalog (e.g. `-Base` pretrains) stay ordinary bases.
  `recommendedQuantForVram` reused for per-row fit labels. Remove `BrowseModelType`.
- **`web/components/benchmark-model-picker.tsx`:** browse branch re-rendered as the
  family tree; search input; selection carries the chosen model slug exactly as today
  (`browseSlug`), so `benchmark-onramp.tsx` state shape and `buildRecipe` are unchanged
  except: quant fallback must respect rule 7 (no silent non-fitting fallback) and the
  recipe header gains the lineage line (benchmark-recipe.tsx).
- **No schema change** beyond what already exists (`model_kind`, `base_model`
  string|array). `variantSource`/officialness is computed, not stored.
- **Static site invariant:** all grouping happens at build/render time from
  model_catalog.json; no runtime HF calls.

## QA gates

- Unit (vitest): grouping (bases-only lab list; variant nesting; base-not-in-catalog
  stays flat; merge multi-listing with canonical first base; official derivation;
  search matching incl. creator org; VRAM fit labels; no-fit never auto-selected),
  picker render states (0 / few / many variants, expanded/collapsed, empty states,
  aria-expanded), recipe header lineage, existing onramp-recipe tests stay green.
- Catalog: refresh-script unit tests extended for seed-from-probes + cap overrides;
  every applied wave re-runs `build-site.ps1` + full web test suite.
- Manual: clean-room browse-to-recipe walk on the deployed site (Qwen family with
  variants; a base-only family; a searched creator), before announce.

## Execution

Codex implements (two briefs: web UI, catalog script); Claude reviews, tests, commits,
deploys. Shared-workspace rule: commit early and often on
`codex/local-bench-online-backend`.
