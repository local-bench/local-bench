# Public snapshot manifest — wave-4 go-public tooling

**PRIVATE ops doc — lives in `docs/deploy/`, which is excluded from the snapshot. Never ships.**

Tool: `scripts/publish-snapshot.ps1` (v1.2.0). Builds a clean public snapshot of this
repo — fresh directory, no git history — ready to become
`github.com/local-bench/local-bench`.

Locked decisions this tooling implements:

| Decision | Value |
|---|---|
| License | Apache-2.0 (copyright line: `Copyright 2026 local-bench contributors`) |
| GitHub org | `local-bench` (repo `local-bench/local-bench`) |
| PyPI distribution name | `local-bench` (console script stays `localbench`) |
| Site deployment | stays on the PRIVATE deploy repo — the public repo connects to nothing |

## How to run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish-snapshot.ps1 -Force
# default OutDir: C:\Users\Michael\local-bench-public-snapshot
# scrub report:   <OutDir>-scrub-report.md   (written NEXT TO the snapshot, never inside)
```

Exit codes: `0` = publishable (scrub clean + Apache-2.0 LICENSE present/created);
`2` = scrub findings (blockers listed in the report); `3` = scrub clean but LICENSE
is still the placeholder / not Apache-2.0; `1` = usage/fatal error.

Behavior notes: never edits the source repo or snapshot contents (LICENSE creation is
the single additive exception, and only when no LICENSE exists); refuses an OutDir
inside the source tree; refuses to delete any directory containing `.git`; wipes an
existing OutDir only with `-Force`. Deterministic: identical source tree in produces a
byte-identical snapshot and report out (verified 2026-07-04 by double-running on a
frozen tree; report contains no timestamps, only source HEAD + dirty-count provenance).

## What is excluded, and why

Directory prunes (path-anchored, relative to repo root):

| Excluded | Why |
|---|---|
| `.git/` | Snapshot is history-free by design — full history carries the work-email author identity on every commit |
| `web/node_modules/`, `web/.next/`, `web/out/` | Dependency cache / build outputs |
| `web/.e2e-artifacts/`, `web/.qa/` | Local Playwright/QA artifacts |
| `cli/.venv/`, `cli/build/` | Virtualenv, Python build artifacts |
| `cli/$tmpdir/` | Stray literal-`$tmpdir` scratch dir (exists on disk) |
| `cli/runs/` (ENTIRE dir) | Run artifacts are not for the public repo. Single re-include: `cli/runs/board/board_v1.json` (frozen fixture, git blob `3d058e60…`, required by `cli/tests/test_site_parity.py` and `cli/tests/submissions/test_wave2_static_composite.py`). NOTE: this also drops the 9 git-TRACKED `cli/runs/vast/*.json` receipts and `board_v1.manifest.json` / `board_v2*` / `launch_freeze_v1.json` — no test references them; re-include explicitly if that changes |
| `.github/workflows/` | Shadow-repro CI rides only the private deploy repo (the snapshot excludes run records, so the workflow would sit permanently red); belt-and-braces on top of the workflow's `if: github.repository ==` guard |
| `shadow-ci-out/` | Local shadow-CI evidence output (`scripts/ci/shadow_compare.py --emit-dir`); the wider `shadow-ci-out*/` family is gitignored, which the snapshot walker also honors |
| `docs/deploy/` | Private ops docs: deployment ids, Cloudflare state, bypass-token paths, the private deploy repo name — and this manifest |
| `docs/briefs/` | Internal agent build briefs full of machine paths |
| `runs/`, `tmp/`, `data/` (top level) | Local run/monitor artifacts, scratch, dataset cache |
| `suite/v0/private/` | Private held-out items — never publish |
| `.agents/ .omo/ .codegraph/ .superpowers/ .pytest-* .ruff_cache` | Local tool state (several are ignored only via machine-local `.git/info/exclude`, so they are hard-excluded here too) |

Name prunes anywhere: `.git node_modules __pycache__ .pytest_cache .ruff_cache
.mypy_cache .venv .idea .vscode .next .wrangler .vercel .turbo *.egg-info`.
Junctions/symlinks are never followed (`.codegraph` is a junction).

File excludes — ALWAYS, even if git-tracked (spec rule; none are currently tracked):
`*secret* *token* *.pem .env* *.key Thumbs.db .DS_Store desktop.ini`.

File excludes — only when NOT git-tracked (local noise; tracked matches are
intentional fixtures and ship, e.g. `cli/tests/fixtures/kld/*.log`):
`*.log *.pyc *.pyo *.tsbuildinfo *.run.json`.

Root dot-files: only `.gitignore .gitattributes .editorconfig` ship (kills
`.debug-journal.md`, `.tmp-next-runtime-ui.*.log`). Root dot-dirs: only `.github`.

Self-exclusion: `scripts/publish-snapshot.ps1` itself does NOT ship — it embeds the
private scrub terms and machine paths. Publishing tooling stays private.

Gitignore filter: when git is available, any file `git check-ignore` reports is also
dropped (belt-and-braces; respects the index, so tracked fixtures are safe). Every
exclusion is itemized in the scrub report.

2026-07-04 proof run: **954 files, 18,495,002 bytes (17.64 MB)** from HEAD `15209fe`
(branch `codex/local-bench-online-backend`, 15 dirty). Untracked working-tree files
ship by design — this correctly picked up the other agent's in-flight new files
(`cli/src/localbench/submissions/submit_run.py`, `cli/tests/test_wave3_*.py`,
`cli/tests/submissions/test_submit_run_*.py`).

## Scrub rules (report-only; the tool never edits)

Blocking (exit 2) — scanned over every text file in the SNAPSHOT:

| Rule | Pattern | Notes |
|---|---|---|
| A-clarityconsultive | `clarityconsultive` (ci) | Work email identity |
| B-papa-midnight-dev | `papa-midnight-dev` (ci) | Private deploy repo name |
| C-secret-env-literal | `ADMIN_API_SECRET \| LOCALBENCH_ADMIN_SECRET \| LOCALBENCH_PRIVATE_BYPASS_TOKEN \| R2_ACCESS_KEY_ID \| R2_SECRET_ACCESS_KEY` followed by `:`/`=` and a literal value | The env var NAME alone is fine. Benign-value heuristics (env indirection, bare identifiers, type annotations, placeholder words incl. `test`/`mock`/`fake`, <8 chars) are skipped; matches inside test paths downgrade to ADVISORY |
| D-abs-path-michael | `C:[\\/]+Users[\\/]+Michael` (ci) | Catches `C:\`, `C:/`, and JSON-escaped `C:\\` forms |
| E-secret-named-file | snapshot filename matching `*.pem *token* *secret* .env* *.key` | Double-checks the copier |
| F-credential-format | `sk-ant-… ghp_… github_pat_… AKIA… AIza… xox?-…` | Downgrades to ADVISORY when the match contains test markers or sits in a test path |
| K-private-key-block | `-----BEGIN … PRIVATE KEY-----` | FAIL only when followed by actual base64 key material outside test paths; bare headers in code/assertions are advisories |

Advisories (never affect exit code): G-personal-name (`michael.russell`, `mj_russell`,
`Michael Russell`, `ultimatedc`), H-deploy-id (`"database_id": "<uuid>"`).

Limitations: binary extensions are skipped; files >50MB are skipped-with-note;
UTF-16-without-BOM text may not scan reliably; rule C is a heuristic — eyeball its
advisories once per release.

## Residual identity edits (2026-07-04 run: 77 blockers in 27 files, 15 advisories)

The scrub report (`<OutDir>-scrub-report.md`) is the authoritative file:line list;
this is the by-file summary with recommended handling. **These edits are for the
owner/manager — NOT made by this tooling, and cli/ + docs/benchmark-build/wave3-* are
being edited by another agent right now, so sequence after that work lands.**

Recommend EXCLUDE from the public repo (add to the script's exclusion lists) rather
than edit — internal working docs/logs with no public value:

| File | Hits | What |
|---|---|---|
| `docs/foundations/redteam/codex-err.txt` | 11 | Raw codex stderr dump; machine paths incl. a pointer to `Desktop\API keys.txt` |
| `scripts/redteam_gemini.py`, `scripts/redteam_qwen.py` | 2+2 | Hardcode repo path AND read `C:\Users\Michael\Desktop\API keys.txt` |
| `docs/foundations/anonymity-audit-v1.md` (13) + `anonymity-license-sweep-2026-06-23.md` (4) | 17 | Audit docs that deliberately QUOTE the identity strings they audit for |
| Session/agent working docs: `docs/foundations/OVERNIGHT-2026-06-25.md` (1), `OVERNIGHT-AUTONOMY-PROMPT.md` (2), `OVERNIGHT-LOG.md` (1), `own-benchmark-research-prompt.md` (3), `SESSION-HANDOFF-2026-06-14.md` (2), `SESSION-HANDOFF-2026-06-15-night.md` (1), `docs/SESSION-CHECKPOINT-2026-06-20.md` (1), `docs/superpowers/plans/2026-06-23-landing-layout-latency.md` (1) | 12 | Internal orchestration notes with machine paths |

Recommend EDIT (public-facing content worth keeping; replace `C:\Users\Michael\…`
with a neutral `<repo-root>` convention and drop personal identifiers):

| File | Hits | What |
|---|---|---|
| `docs/REPRODUCE.md` | 3 | Repro commands embed machine paths — genericize |
| `docs/foundations/PROJECT-HANDOFF.md` | 2 | Repo path + API-keys-file pointer |
| `docs/foundations/model-benchmark-roster-2026-06-28.md` | 7 | OneDrive path with `clarityconsultive.com` + vast import paths |
| `docs/foundations/license-inventory-DRAFT.md` | 2 | Git-author identity line (work email) |
| `docs/foundations/website-design.md` (1), `serve-orchestrator-spec-2026-07-01.md` (1), `submit-cli-rewrite-spec-2026-07-01.md` (2), `board-v1-build-spec.md` (2), `board-row-semantics-spec.md` (1), `approach-consolidation-and-mmlu-pro-2026-06-16.md` (1), `agentic-lane-b1-spec-2026-07-03.md` (2) | 10 | Spec docs with worktree/venv/token-file machine paths |
| `docs/benchmark-build/engine-hardening-spec-2026-06-29.md` (1), `resume-gate-fix-spec-2026-07-03.md` (4), `retry-errored-writer-v1-spec-2026-07-03.md` (9 incl. dup-line matches → 4 lines) | 9 | Build specs with worktree paths — same dir the other agent is working in; edit after they land |

Advisories to eyeball once (no action expected): PEM formatter code + throwaway test
key fixture (`cli/src/localbench/submissions/keys.py`, `cli/tests/submissions/fixtures.py`
— confirm the fixture key was generated for tests only), fake `sk-ant-testsecret123`
redaction fixtures (`cli/tests/test_runner.py`), `owner-token` vitest fixture
(`web/tests/offline-gate.test.ts`), grep-command line in
`docs/superpowers/plans/2026-06-23-benchmark-onramp.md:1068`, and
`web/wrangler.jsonc:9` D1 `database_id` (+ R2 bucket names) — decide whether to
genericize the wrangler config or accept it in public.

## License / attribution tasks (blockers and near-blockers)

1. **Root `LICENSE` is the "NOT YET CHOSEN" placeholder** (all rights reserved). The
   script reports this as a blocker (exit 3 once scrub passes) and never overwrites.
   Owner action: replace repo `LICENSE` with the full Apache-2.0 text, copyright line
   `Copyright 2026 local-bench contributors`. (If the file were absent, the script
   writes exactly that text itself.)
2. **`NOTICE` (root) is stale**: lists only MMLU-Pro / IFBench / IFEval / BFCL. The
   reviewed draft `docs/foundations/NOTICE-DRAFT.txt` (2026-06-25, pending owner+legal
   review) adds AMO-Bench, OlymMATH, SuperGPQA and the TO-CONFIRM block:
   **LiveCodeBench** (dataset CC-BY-4.0, harness MIT, LeetCode-ToS caveat on problem
   text), BFCL vendored-rows credit, RULER, BigCodeBench-Hard. Verify + adopt before
   go-public.
3. **`LICENSES/` lacks LiveCodeBench texts**: currently only `Apache-2.0.txt`,
   `IFBench-ODC-BY-1.0.txt`, `MMLU-Pro-MIT.txt`. If LCB items stay in the suite, add
   CC-BY-4.0 (dataset) and the harness MIT text, per NOTICE-DRAFT.
4. **`cli/src/localbench/scorers/lcb.py` has no attribution header** — unlike the
   ifeval/ifbench/bfcl scorers (which carry NOTICE files), the LiveCodeBench scorer
   has a bare docstring. Add an upstream-attribution header (and/or a scorer-dir
   NOTICE) referencing LiveCodeBench (harness MIT).
5. **`cli/pyproject.toml` `[project] name = "localbench"`** — locked decision is PyPI
   distribution `local-bench`; rename dist while keeping `[project.scripts] localbench`
   (and `localbench-monitor`). cli/ is owned by the other agent right now — sequence.

## Go-public runbook

Preconditions (in order):
1. Other agent's cli/ + wave3 work landed and committed.
2. Residual identity edits above done (or files added to the script's exclusion
   lists), LICENSE replaced, NOTICE adopted, LICENSES/ completed.
3. `scripts\publish-snapshot.ps1 -Force` → **exit 0**, and skim the report's
   advisories one last time.
4. Optional sanity inside the snapshot: `python -m venv .venv; .venv\Scripts\pip
   install -e .\cli[dev]; pytest cli\tests` and `cd web; npm ci; npm run build`.
   Verify `git hash-object cli\runs\board\board_v1.json` = `3d058e6074bd781cc488c03255904b5f9599e37e`.

Publish (fresh history, anonymous author):
```powershell
cd C:\Users\Michael\local-bench-public-snapshot
git init -b main
# CRITICAL: repo-local anonymous identity BEFORE the first commit -- the default
# git config would stamp the work-email author on the public initial commit.
git config user.name  "local-bench contributors"
git config user.email "local-bench@users.noreply.github.com"
git add -A
git commit -m "Initial public snapshot"
gh repo create local-bench/local-bench --public --source . --push   # org must exist; gh auth acct = org publisher
# (or: git remote add origin https://github.com/local-bench/local-bench.git; git push -u origin main)
```

Connect NOTHING after push:
- Cloudflare Pages stays wired to the PRIVATE deploy repo (`Papa-midnight-dev/local-bench-site`).
  Do not connect Pages, Workers, or any CI secret to the public repo.
- No GitHub Actions with credentials in the initial commit; add CI later, secretless.
- Note the pushing GitHub account is visible on the commit/repo activity — publish
  from the org-appropriate account and keep org member visibility private.
- PyPI release of dist `local-bench` is a separate later step, not part of this push.

Post-publish: clone fresh from GitHub and re-run the scrub scan against the clone
(`publish-snapshot.ps1 -SourceRoot <clone> -OutDir <tmp>`) for a final
independent PASS, then delete the temp output.

## Maintaining this tooling

- To exclude another file/dir: edit `$PathPrunes` / `$FileExcludeAlways` /
  `$FileExcludeUntrackedOnly` in `scripts/publish-snapshot.ps1` (keep this manifest's
  tables in sync).
- Re-run cadence: after every batch of residual edits, and always immediately before
  the real push (the working tree moves — the other agent added files between proof
  runs on 2026-07-04, which the tool picked up correctly).
- The scrub report next to the snapshot contains identity strings by nature — treat
  it as private, delete it before sharing the snapshot dir itself.

## 2026-07-04 residual close-out (Claude)

- EDIT bucket done in source: `C:\Users\Michael\` → `<home>\` (and `/` variant)
  across REPRODUCE, PROJECT-HANDOFF, roster, license-inventory-DRAFT, 3
  benchmark-build specs, 6 foundations specs, one superpowers plan; plus three
  rewords (API-keys pointer, OneDrive runbook path, git-author identity line).
- EXCLUDE bucket added to the script (v1.3.0): dirs `docs\foundations\redteam`,
  `docs\superpowers`; `$RelFileExcludes` for the two anonymity audits, five
  session/overnight docs, own-benchmark-research-prompt, SESSION-CHECKPOINT,
  and the two redteam_*.py scripts.
- LICENSE is now real Apache-2.0 (654b45f); NOTICE adopted from the verified
  draft; LICENSES/ has both LiveCodeBench texts; lcb.py header added;
  dist renamed `local-bench` — items 1–5 of the licensing tasks are CLOSED.
