# v1 distribution plan — functional local run (oracle-reviewed, 2026-06-23)

Source: GPT-5.5 Pro (oracle) consult `localbench-suite-cli-distribution`, resolving on-ramp gap 1
(suite + CLI distribution). Weighed + ENDORSED by the orchestrator. PENDING Michael's confirm (it
extends v1 + commits to a distribution layer + needs his Cloudflare account for hosting), but the
recommendation is strong + decisive.

## Verdict: functional local RUN, deferred SUBMISSION
v1 lets an external user install the CLI, fetch the frozen public Core Text v1 suite, run it
locally, and get a board-comparable `my-run.json` (same scorer, scorecard, suite hashes,
conformance, composite). v1 does NOT let them submit to the public board (that is v2).

This is NOT "community submissions" (rightly deferred) — it is "external reproducibility of the
public benchmark", which keeps the read-only-board boundary intact while making the "local" claim
REAL. The honest-preview alone is too weak for the core promise.

**v1 scope line:** "v1 supports local self-runs against the frozen public Core Text v1 suite.
v1 does not accept, verify, rank, or publish community results."

| Capability | v1 |
|---|---|
| Install CLI without repo checkout | YES |
| Fetch the exact public v1 suite | YES |
| Run MMLU-Pro 400 + IFBench 294 locally | YES |
| Produce `my-run.json` (same scorer/scorecard/hashes) | YES |
| Upload to public board / server re-score / trust tier / public row | NO (v2) |

## Distribution mechanism: Cloudflare-hosted wheel + R2 suite fetch (Option B)
NOT PyPI (Trusted Publishing ties to CI identity; bundling = redistribution event), NOT a public
repo (permanent identity-maintenance burden). Instead:
- Host a SANITIZED wheel/zip release on `local-bench.ai/releases/`.
- `localbench run` auto-fetches the frozen suite from a Cloudflare R2-backed custom domain
  (the SAME anonymized account as the site + the future v2 submission backend). Public GET via
  custom domain (not the rate-limited r2.dev URL; not presigned for v1 reads).
- Keep CLI artifact + suite artifact SEPARATE (do not bundle the suite in the wheel).

Primary on-ramp UX (one command, assuming a local OpenAI-compatible endpoint is already up):
```
uvx --from https://local-bench.ai/releases/localbench-0.1.0-py3-none-any.whl localbench run \
  --suite core-text-v1 --accept-suite-terms \
  --endpoint http://127.0.0.1:8000/v1 --model <served-name> --out my-run.json
```
`localbench run` flow: resolve `core-text-v1` -> check `~/.cache/localbench/suites/<id>/<hash>/`
-> if missing, download suite manifest + tarball from local-bench.ai -> verify tarball SHA-256 +
per-item-set hashes -> record exact suite hash, scorecard id, scorer versions, decode params, CLI
release id in `my-run.json` -> FAIL CLOSED on any mismatch. Also ship `localbench fetch-suite`
(explicit, requires `--accept-suite-terms`) + `localbench suite inspect`.

## Suite contents: headline-only
Distribute ONLY the v1 headline suite: **MMLU-Pro 400 + IFBench 294, 50/50.** Rule: "if it is not
in the v1 headline score, it is not in the public v1 suite bundle." Do NOT ship AMO, OlymMATH,
SuperGPQA, BFCL, LiveCodeBench, RULER, or BigCodeBench (shrinks legal/support/contamination
surface). Public bundle layout: `suite.json, mmlu_pro.jsonl, ifbench.jsonl, itemsets.lock.json,
SCORECARD.json, ATTRIBUTION.md, NOTICE, LICENSES/{MMLU-Pro-MIT, IFBench-ODC-BY-1.0,
IFEval-Apache-2.0}, SOURCE_REVISIONS.md, CHANGES.md, SHA256SUMS`. CHANGES.md states it is a
sampled/subsetted bundle, lists exclusions, and that scoring is local-bench's own composite.

## LICENSE — MUST resolve before serving the suite
- **IFBench license — VERIFIED ODC-BY-1.0 (2026-06-23):** the Sonnet audit said Apache-2.0 (that
  is the GitHub repo CODE license); the live HF dataset card (`allenai/IFBench_test`) confirms the
  DATASET is **ODC-BY-1.0** ("intended for research and educational use in accordance with Ai2's
  Responsible Use Guidelines"; "includes output data generated from third party models that are
  subject to separate terms"). We redistribute the dataset ITEMS, so the suite
  NOTICE/LICENSES/ATTRIBUTION must credit IFBench as ODC-BY-1.0 (attribution + license notice +
  keep original notices) AND surface the Ai2 Responsible-Use + third-party-output caveats. Fact is
  RESOLVED; the NOTICE/inventory edits remain to do before serving the suite.
- MMLU-Pro: dataset = MIT (HF card), repo code = Apache. Distinguish dataset vs code license.
- Auto-fetch = a redistribution event: require `--accept-suite-terms` + record the accepted suite
  license manifest in `my-run.json`. Pin EXACT upstream revisions + item hashes; never silently
  update `core-text-v1` once public.

## Implementation checklist (before it can be called "functional")
1. **Replace the source-tree suite resolver.** New order: `--suite-dir` -> `LOCALBENCH_SUITE_DIR`
   -> user cache `~/.cache/localbench/suites/<id>/<hash>/` -> package-data fallback (tiny smoke
   ONLY) -> auto-fetch from local-bench.ai + verify hashes. Kill the
   `Path(__file__).parents[3]/suite/vN` path in the installed CLI. (Also fixes gap 2: default to
   v1 + the `--suite core-text-v1` alias.)
2. **Empty-machine release test** (launch-blocking): fresh venv + fresh HOME, `pip install` the
   hosted wheel, `fetch-suite`, `suite inspect`, `run --dry-run`, + a real 2-item smoke against a
   local endpoint. If it needs the private repo ANYWHERE, v1 is not functional.
3. **Pin the lane as `top_k=1`** (not just `temperature=0`) before exposing external runs; record
   full decode params in the manifest. (Also a v2-forward-compat item.)
4. **Define "board-comparable" NARROWLY** (code + copy): same item set / scorer / scorecard /
   extraction / conformance / composite. NOT verified identity / accepted row / same timing /
   trust tier.
5. CLI ergonomics for the support burden: `localbench doctor`, `--dry-run`, `--limit 2`, a clear
   "bring your own OpenAI-compatible server" boundary. NO secrets in the CLI (download is public
   read-only; v2 upload tickets are server-issued).

## Site framing (3 labels — makes run-without-submit intentional)
- Board: "Project anchor results — run by local-bench on the pinned v1 rig, frozen into
  board_v1.json." (NOT "verified".)
- Benchmark-a-model: "Run the public v1 benchmark locally... the result is for your own
  comparison. v1 does not accept public submissions." then the command.
- End state: "What you get" (a local score file with hashes/scorecard/scorer/conformance/
  per-bench + composite) vs "What you do NOT get in v1" (a public row, a verified badge,
  model-identity verification, server re-score; public submissions land in v2, may need a rerun).

## Anonymity-safe release mechanics
Export CLI source to a clean dir OUTSIDE git -> build wheel there -> NO sdist for v1 -> no
GitHub/GitLab URLs in wheel metadata -> `contact@local-bench.ai` not a personal email -> no private
commit SHAs in metadata -> no personal GPG signing (pseudonymous release key only) -> upload
wheel+suite+manifest+checksums to the anonymized Cloudflare account -> GREP the built wheel METADATA
+ artifacts before upload. Boundary: anonymous to the public + casual OSINT, NOT to Cloudflare /
registrars / legal process. (A public wheel exposes the CODE even with a private repo — fine, but
don't conflate "private repo" with "private implementation".)

## Go / no-go gate (all six)
1. Empty-machine install works without a repo checkout.
2. `localbench run --suite core-text-v1` auto-fetches + verifies the suite.
3. Public suite contains ONLY MMLU-Pro + IFBench.
4. IFBench license/NOTICE corrected to the current dataset terms (ODC-BY until verified).
5. Run JSON records suite hash, scorecard id, scorer versions, decode params, conformance.
6. Site copy says "local self-run, not submission."

## Timeline + dependency note
This EXTENDS v1 (a distribution layer: wheel-release pipeline + R2 suite hosting + the new
resolver + fetch-suite/inspect/doctor + the empty-machine test + top_k=1 + license corrections).
Michael authorized "extend timing for complete." CRITICAL UPSIDE: this distribution layer IS v2's
foundation (CLI + suite distribution + run-JSON-as-bundle), so building it in v1 pulls v2 much
closer — v2 then reduces to the submit/verify/merge backend on the SAME Cloudflare R2/Workers
infra. Needs Michael's Cloudflare account (same one as the site deploy) for R2 hosting — one creds
ask, now serving the site + the wheel + the suite.
