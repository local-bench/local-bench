<task>
Make the leaderboard HONEST about what it shows (code-review findings #8, #9), branch
`refactor/architecture`. The product's whole value is honest measurement; the home page must not
imply a ranking the methodology disclaims. Today `web/components/home-leaderboard.tsx` numbers rows
1..N and sorts by composite across the entire index, even though (a) all current rows are Quick tier
which the page itself calls UNRANKED, and (b) reasoning lanes are mixed (anchors ran api-uncapped /
native reasoning; the local model ran answer-only) and composite is only comparable WITHIN a lane.

Read the current component, lib/schemas, lib/data, and the home e2e spec first, then:

1. DATA (web/build_data.py): 
   - Add a boolean `ranked` to each index row = (tier == "standard"). Quick rows are NOT ranked.
   - Fix `replicated` (finding #9): only true when the source entry carries explicit independent-
     replication metadata. Add an optional `independent_replication` field to the data_sources schema
     (default false/absent). Do NOT infer replication from run count or anchor kind. With current data
     every model becomes `replicated: false`. Keep emitting it for future use.
2. UI (web/components/home-leaderboard.tsx + home page):
   - SUPPRESS rank numbers for unranked rows. Show an ordinal rank ONLY for ranked (Standard, same-lane)
     rows. With current all-Quick data, NO rank numbers appear — replace the RANK column with nothing
     or a neutral marker; do not print 1..5.
   - Make lanes legible and NOT falsely comparable: group rows by reasoning lane (e.g. a subheading or
     visual separation for "Native reasoning · api-uncapped" vs "Answer-only"), OR keep one table but
     add a clear, prominent statement that rows are sorted-for-browsing only and lanes are not directly
     comparable. Either way the existing "Quick = UNRANKED" note stays and is strengthened to mention
     the cross-lane caveat. Sorting by composite for browsability is fine; just don't present positions
     as a ranking.
   - Do not claim "Replicated" anywhere (already true; keep it). Community rows show "Community-reported"
     + run count.
3. E2E (web/e2e/home.spec.ts): update to the new design — assert NO numeric ranks are rendered for the
   (unranked) rows, assert the lane grouping/caveat is present, assert models still sorted by composite,
   and keep the zero-console-error guard. Keep all other specs green.
</task>

<action_safety>
Touch ONLY: web/build_data.py, web/data_sources.json (if you add the optional field to entries — keep
existing values; do not change which runs are included), web/components/home-leaderboard.tsx,
web/app/page.tsx (home copy), web/lib/schemas.ts + web/lib/data.ts (types for ranked/replicated),
web/e2e/home.spec.ts. Do NOT touch cli/, suite/, scoring, the model/run pages, or other e2e specs.
Regenerate web/public/data by running build_data after changes. No git commits.
</action_safety>

<completeness_contract>
Done = `cd web && npm run build` passes; `npm run e2e` passes (8+ specs incl. the updated home spec);
full `cli/.venv/Scripts/python -m pytest cli/tests -q` green (build_data test still passes — update it if
the index schema gains `ranked`); no rank numbers shown for Quick rows; `replicated` is false for all
current models; lanes are not presented as directly comparable.
</completeness_contract>

<verification_loop>
Rebuild data; run web build + e2e; confirm the home page shows no 1..5 rank numbers, shows the lane
grouping/caveat, and still lists all 5 models sorted by composite. Confirm pytest green. Fix before finishing.
</verification_loop>

<missing_context_gating>No questions. Choose the cleaner of grouped-by-lane vs single-table-with-caveat;
note which and why in a comment.</missing_context_gating>

<compact_output_contract>
Final: (1) files changed, (2) build + e2e + pytest result lines, (3) how rank suppression + lane honesty
are implemented (grouped vs caveat), (4) <=5 bullets incl. the replicated/ranked schema change and the
updated home e2e assertions.
</compact_output_contract>
