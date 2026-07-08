<task>
Refactor Step 4 on branch `site-overhaul`: consolidate the web QUANT taxonomy (currently duplicated ~5×
with two divergent ordering encodings) into a single source of truth `web/lib/quant.ts`, WITHOUT changing
any rendered behavior or computed output. Pure refactor. You implement; Claude reviews + runs the gates.
</task>

<context>
The quant label set, ordering, bytes-per-param map, and parse/guard helpers are duplicated across:
- `web/lib/rig-match.ts` (`QUANT_OPTIONS`, `quantBytesPerParam`, `isQuantOption`/`toQuantFilter`-ish)
- `web/lib/quality-bars.ts` (a quant ordering encoding)
- `web/lib/quant-decision.ts` (`QUANT_OPTIONS` usage, `quantOrder`)
- `web/components/rig-match-finder.tsx` (`toQuantFilter`)
- possibly `web/lib/compare.ts`
The red-team flagged TWO divergent ordering encodings — reconcile them into ONE canonical order while
keeping the EFFECTIVE sort outcomes identical.
</context>

<deliverables>
1. Create `web/lib/quant.ts` as the single source of truth: the canonical quant list + order, the
   bytes-per-param map, the `QuantOption` type, the parse/guard helpers (`isQuantOption`, `toQuantFilter`),
   and an ordering helper. Export what the consumers need.
2. Replace the duplicated definitions in `rig-match.ts`, `quality-bars.ts`, `quant-decision.ts`,
   `rig-match-finder.tsx`, and `compare.ts` (if applicable) to import from `lib/quant.ts`.
3. PRESERVE fallback behavior EXACTLY (red-team guardrails): the unknown-quant rank vs `null` rank in
   `quality-bars.ts`; the default bytes-per-param in `rig-match.ts`; the exact export paths `compare.ts`
   relies on. Do NOT change the effective ordering, the VRAM math, or any computed/rendered output.
</deliverables>

<constraints>
- Branch `site-overhaul` ONLY; never main. PURE refactor — zero behavior/output/data change.
- Reuse existing types/tokens; match the codebase style.
</constraints>

<verification_loop>
- `npm run typecheck` clean; `npm test` green; `npm run build` green; `npm run e2e` green.
- Because this is a pure refactor, the rendered output is unchanged — the gates passing is the proof.
- Commit on site-overhaul with a clear message.
</verification_loop>

<output_contract>
Return: files changed; exactly what moved into `lib/quant.ts`; how you reconciled the two ordering
encodings (and confirmation the effective order is unchanged); gate results (typecheck/test/build/e2e).
</output_contract>
