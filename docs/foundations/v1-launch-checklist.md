# v1 launch checklist (oracle-reviewed, 2026-06-23)

Distilled from GPT-5.5 Pro (oracle) consult `localbench-v1-ship-plan-review`, weighed by the CLI
agent. Verdict: **GO for v1 once gemma passes or is explicitly deferred. Do NOT wait for
agentic, a public repo, or community submissions. Do NOT publish the CLI via a personal
account.** Ship a clean read-only board + strong methodology page + immutable manifest +
anonymity-scrubbed static artifact + conservative claims.

## v1 scope — ruthlessly narrow
Qwen quant ladder + gemma, same headline capped-thinking lane, same validated Knowledge +
Instruction suite, read-only board. NO new axes, NO community submissions, NO public on-ramp, NO
AppWorld, NO extra models, NO UX flourish that can perturb the data contract.

## Critical path (in order)
1. **Freeze v1 semantics now.** Public label carries the scope: `MMLU-Pro 400 + IFBench 294,
   50/50, RTX 5090 32GB, capped-thinking headline lane`.
2. **gemma in ONLY if it passes the same release gate as Qwen** — conformance green, no leaked
   reasoning, no truncation, no missing final answer, same extractor, same suite hashes, same
   lane metadata, no one-off fix that isn't encoded as a regression. If it fails -> ship
   Qwen-only, mark gemma pending. NEVER rerun gemma to "get a better number"; rerun only for
   infra/protocol failure.
3. **Generate ONE immutable `board_v1.json` from the scorer, not the site.** The site is a PURE
   renderer. The artifact holds rows, ranks, raw per-domain scores, task counts, lane scope,
   score formula, suite hashes, model/runtime configs, reasoning-registry hash, extractor
   version, transcript/result hashes. Prevents the site from becoming a scoring actor.
4. **Enforce the lane contract before deploy** (task #22). Add FAILING tests for: duplicate model
   IDs across scopes; non-headline lane with non-null rank; answer-only rows entering rank;
   frontier/API rows entering rank; candidate domains silently changing the Index version.
5. **Publish a methodology/limitations page AS PART OF v1** (task #23) — highest-leverage
   credibility work. Cover hardware, runtime, quant format, context limits, reasoning/capping
   policy, scoring formula, failure policy, subset policy, run manifest, and **what the index
   does NOT measure**.
6. **Deploy by Cloudflare Pages Direct Upload from a sanitized build artifact, outside the git
   workspace.** (Direct Upload projects can't later switch to Git integration without a new
   project — good for anonymity.)
7. **Attach the apex domain, REDIRECT the `*.pages.dev` hostname to it** (so the project URL
   isn't a second public surface), and smoke-test the live artifact hash.

## The naming decision (DECISION FOR MICHAEL)
The oracle's one hard recommendation: a 2-domain composite labelled "Intelligence Index" invites
"an intelligence leaderboard with two tests" criticism. Its fix: keep "Intelligence Index" as the
SITE concept, but make the v1 table honest — either (Option 1) headline "Local Intelligence
Index" with a PROMINENT scope banner "Core Text v1: Knowledge + Instruction, ...", or (Option 2,
oracle's literal pick) table header "Core Text Index v1". Reconciles the growing-Index vision with
honest current-scope labelling. Michael chose "Intelligence Index" earlier; Option 1 honours that
+ adds the prominent scope. Pending Michael's confirm.

## Credibility additions (before launch)
1. Visible **scope banner** above the table (hardware, lane, quant/runtime, index version,
   measured domains) — in plain English; no methodology-page context needed to read the rank.
2. **Raw domain scores next to the composite** (Knowledge, Instruction, task counts,
   invalid/format/truncation rates). Tie language for close scores; avoid overprecise decimals.
3. A **rerun policy**, public: rerun only for infra failure / corrupted output / wrong
   model-config / failed conformance gate; NEVER because a model underperformed.
4. A **model-system identity policy**: rank SYSTEMS, not abstract models = base + quant + runtime
   + context + reasoning mode + cap + extractor + lane. Essential for the Qwen quant ladder.
5. A **release manifest download** (immutable manifest hash; JSON/CSV with hashes to inspect/cite).
6. A **"no LLM judge" explainer**: objective/programmatic/exact scoring only — and say objective
   scoring is NOT the same as complete capability coverage. Honest, not promotional.
7. A **public changelog** from v1 onward (version every scoring-rule/lane/extractor/bench/weight
   change). Do NOT foreground the (unpublished) gemma incident.
8. A **legal/license pass** (task #25): redistribution terms for MMLU-Pro, IFBench, model
   names/licenses, quant artifacts; AppWorld's protected-bundle rule later.

## Anonymity — keep the repo PRIVATE for v1 (task #20)
Ship site artifacts + reproducibility manifests, NOT public git history. If a public repo is
needed later: a FRESH pseudonymous repo from a clean source export — new dir, no `.git`, no old
remotes/commits/issue-templates, no personal CI, no personal package account, fresh local-only
pseudonymous git config. Do NOT rewrite+publish the existing repo; do NOT `push --mirror`.
The audit question is NOT "is my current email private" — it's "does ANY reachable commit, tag,
signature, co-author line, release note, or CI artifact contain identity."

Vectors to audit: WHOIS/RDAP (verify actual output for local-bench.ai; state/country may remain);
Certificate Transparency (CT logs are public — no identity-bearing staging subdomains); Pages
project name (neutral + redirect `pages.dev`); preview deployments (public by default — avoid for
v1 or put behind Cloudflare Access); sourcemaps/build paths (don't upload `.map`; scrub absolute
paths + Windows user dirs); analytics (NONE for v1); static assets (grep for names/emails/
usernames/hostnames/paths/EXIF/old repo URLs); run manifests (no local paths/hostname/username/
git remotes); contact (pseudonymous mailbox on the domain); package signing/provenance (avoid
until the signing identity is pseudonymous — provenance points at the source repo).

PyPI/npm if published: scrub Author/Author-email/Maintainer/home-page/project-URLs; pseudonymous
mailbox; PyPI Trusted Publishing is tied to CI identity (use only from a pseudonymous repo/org, or
a project-scoped token from a pseudonymous account); npm `author` + `npm init` infer repo/bugs/
homepage from the dir.

Pre-publish audit commands (run before any public package/artifact):
```bash
git log --all --format='%H %an <%ae> | %cn <%ce>' | sort -u
git log --all --format='%H %s%n%b' | grep -Ei 'co-authored-by|signed-off-by|@|github.com|users.noreply'
grep -RInE '(@gmail|@outlook|@icloud|C:\\Users\\|/Users/|/home/|github.com/|gitlab.com/|hostname)' dist site-dist public build . 2>/dev/null
find site-dist public build -type f \( -name '*.map' -o -name '*.tsbuildinfo' -o -name '.DS_Store' \) -print
# build sdist/wheel, then print METADATA and inspect Author/Author-email/Maintainer/URLs
```
Anonymity target (state internally): **anonymous to the public + casual OSINT, NOT to Cloudflare,
registrars, payment processors, package registries, or legal process.**

## AppWorld pilot — PARALLEL track, not a v1 blocker (task #18)
AppWorld is natively an interactive coding/API env (9 apps, 457 APIs, state-based eval); our
harness is a strict JSON tool-call protocol -> call it **"AppWorld-lite JSON tool-call axis"**, not
"AppWorld", and explicitly map + FREEZE the adapter semantics. Sequence:
1. Install + pin EXACTLY: clean Py3.11+ env, pin package version/commit, `appworld install`,
   `appworld download data`, set `APPWORLD_ROOT`, hash the `data/` tree + dataset IDs.
2. **Verify before any GPU run:** `appworld verify tests` + `appworld verify tasks` in the exact
   harness env. Stub unit tests are NOT evidence real state reset/save/eval works.
3. **Protocol iteration on train/dev ONLY.** The first Qwen Q4 pilot is a DEV pilot, not test.
4. **Freeze the adapter BEFORE selecting/running any scored test subset** (schema, tool
   namespace, API-doc exposure, max steps, timeout/retry, failure categories, state-save points,
   `complete_task` handling, answer normalization, scoring). Select the subset deterministically
   from task IDs only (seeded, split-balanced) WITHOUT inspecting task text/ground-truth/
   difficulty/eval-reports/failures.
5. Do NOT publish test transcripts (contamination/leakage). NEVER expose `ground_truth` or
   difficulty to the agent (guard the prompt/log stream). Sandbox (containerized servers;
   separate API server/port per task if parallelizing).
Waste signals: scripted runner not 100% green on a real slice; adapter hasn't proven state
round-trips on real tasks; high format-error rate before reasoning; too much API doc -> truncation;
inspecting test failures then changing prompts; shared server/port corrupting state; online eval
used as a tuning signal on test.

## Defer (NOT v1)
Agentic/AppWorld, community submissions, public repo, public package (if unscrubbed), landing
on-ramp builder, model-request workflow, full transcript explorer, the frontier/API reference
panel if not already implemented, any candidate column with no measured values.
