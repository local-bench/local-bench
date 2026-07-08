<task>
Establish a real browser E2E test harness for the web prototype so every refactor step can be
live-verified (not just unit-tested). Use Playwright (headless Chromium) against the actual built
artifact. The harness MUST be able to FAIL on real runtime bugs (console errors, failed requests,
missing/empty content, broken interactions) — it is the safety net for an architecture refactor.

1. Add `@playwright/test` as a devDependency in web/ and install the Chromium browser
   (`npx playwright install chromium` — chromium only, no other browsers). Add scripts:
   `"e2e": "playwright test"` and keep existing `test` (vitest) separate.
2. `web/playwright.config.ts`: a `webServer` that builds and serves the app deterministically.
   The app is a static export (output: export → web/out). Configure webServer to run a static
   server on web/out (e.g. `npx serve -s out -l 4321` or Playwright's built-in) on a FIXED port,
   reusing an existing server if present; baseURL that port. Single worker, chromium project,
   trace on-failure, screenshot on. Output artifacts to web/.e2e-artifacts/ (screenshots, traces).
3. `web/e2e/*.spec.ts` covering ALL routes, each test must (a) assert meaningful content, and
   (b) FAIL on any browser console error or failed network response (register page.on('console')
   /page.on('pageerror')/page.on('response') guards in a shared fixture and assert none occurred):
   - Home `/`: all 5 models present by label; the composite numbers render (e.g. Gemini 3.1 Pro
     row shows ~94.4); CI markers (± or lo–hi) present; kind badges (ANCHOR / COMMUNITY-REPORTED)
     present; NO "Replicated" badge anywhere (we don't claim it). Exercise the sort: click the
     Composite header (or another sortable header) and assert row order changes/stays consistent.
   - Model page for an anchor slug AND for qwen3-5-9b: scatter SVG present; dashed anchor reference
     lines present (assert >=1 dashed line / anchor label); runs table lists the runs; the
     "omitted from scatter (no footprint)" note shows for qwen. Each run row links to a run page.
   - Run detail for one anchor run AND one qwen run: composite shown; three axis bars
     (genmath/ifeval/mmlu_pro) present with CI; manifest fields (model, lane, hardware) present;
     item-set hashes (provenance) present.
   - `/methodology` and `/trust`: key substantive content present (e.g. "bootstrap"/"chance",
     "replication"/"community-reported"); internal links back to home work.
   - A cross-cutting test that visits every route from getStaticPaths-equivalent (read
     web/public/data/index.json + each model's runs) and asserts 200 + no console error on each.
   - Screenshot every visited page into web/.e2e-artifacts/ with stable names.
4. Gitignore web/.e2e-artifacts/ and Playwright's caches; keep test specs committed.
</task>

<action_safety>
Only touch web/ (package.json, playwright.config.ts, e2e/**, web/.gitignore). Do NOT modify app/
components/lib (the code under test) or anything in cli/ or suite/. Do NOT git commit. Do not
change web/public/data.
</action_safety>

<completeness_contract>
Done = `cd web && npm run build` then `npm run e2e` BOTH pass headless on a clean run; the specs
genuinely assert content + zero console errors + zero failed responses (verify by temporarily
introducing nothing — just confirm they pass on the current good build); screenshots land in
web/.e2e-artifacts/. Report the exact routes covered and the screenshot filenames.
</completeness_contract>

<verification_loop>
Build, run e2e, ensure green. Then sanity-check the guards actually work: confirm the console-error
assertion is wired (describe how). If any spec is flaky on the static server (timing), make the
webServer wait for readiness. Fix before finishing.
</verification_loop>

<missing_context_gating>No questions. Pick a fixed port unlikely to clash (e.g. 4321). If `serve`
isn't available, add it as a devDependency or use Playwright's static webServer.</missing_context_gating>

<compact_output_contract>
Final: (1) files added, (2) the `npm run build` + `npm run e2e` result lines (tests passed/total),
(3) routes covered + screenshot filenames, (4) <=5 bullets: how console-error/failed-response guards
are wired, the webServer command + port, and anything a reviewer should double-check.
</compact_output_contract>
