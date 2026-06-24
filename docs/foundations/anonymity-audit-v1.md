# Anonymity Pre-Publish Audit — v1

**Scope:** local-bench.ai Cloudflare Pages launch (Wrangler direct-upload of `web/out/`).
**Date:** 2026-06-23
**Model:** Claude Sonnet 4.6

**Key deployment fact:** the repo has no git remote and is never pushed. Deploy is a Wrangler
direct-upload of `web/out/`. Git history and all files outside `web/out/` are never published.

---

## Verdict summary

| Vector | Scope | Verdict |
|---|---|---|
| Git identity — commit author/committer fields | Private repo history | FLAG (A) — expected, non-blocking |
| Git log — commit body strings | Private repo history | FLAG (A) — non-blocking |
| Content sweep — personal name "Michael" | Working tree | FLAG (A) for repo docs; FLAG (B) for one tracked source file |
| Content sweep — email addresses | Working tree | PASS |
| Content sweep — Windows user paths (`C:\Users\Michael`) | Working tree | FLAG (A) for gitignored log; FLAG (B) for one tracked source file |
| Content sweep — unix home paths | Working tree | PASS |
| Content sweep — repo URLs (github/gitlab) | Working tree | PASS |
| Built site `web/out/` — all identity strings | Published artifact | PASS |
| Built site `web/out/` — `.map`/`.tsbuildinfo`/`.DS_Store` | Published artifact | PASS |
| Built site `web/out/` — absolute build paths in bundle | Published artifact | PASS |
| Run manifests `cli/runs/*.json` — local paths | Source run JSONs | FLAG (A) for `output_path`; PASS for published equivalents |
| Deploy script | Published artifact | PASS |

---

## BUCKET A — Private repo history (non-blocking for a private repo)

These findings exist in the git history or in files that are never published to
`local-bench.ai`. They are documented here for completeness only. As long as the
repo has no public remote (confirmed: `git remote -v` returns nothing), none of these
reach visitors.

### A1. Git commit author/committer identity

Every commit in the repo was authored by **Michael Russell
<michael.russell@clarityconsultive.com>**. All commits also carry `Co-Authored-By`
trailers from Claude Opus 4.8 and Claude Fable 5 (Anthropic noreply addresses only).

```
git log --all --format='%H %an <%ae> | %cn <%ce>' | sort -u
# Result: every line = Michael Russell <michael.russell@clarityconsultive.com>
```

Not exposed via direct-upload deployment. Non-blocking.

### A2. Working-tree docs containing "Michael" (not published)

The following **git-tracked** documentation files reference "Michael" in the sense of
an owner/approver. These files are in `docs/` and are never served by the site — only
`web/out/` is uploaded. All occurrences are internal planning language (e.g.
"Michael's sign-off", "Michael chose").

Files (representative, not exhaustive):
- `docs/foundations/methodology-lock/DECISION.md` — "SIGN-OFF — Michael, 2026-06-18"
- `docs/foundations/methodology-lock/DISCRIMINATION-CAMPAIGN-2026-06-19.md`
- `docs/foundations/methodology-lock/FOUNDATION-WIDENING-RESEARCH-2026-06-19.md`
- `docs/foundations/methodology-lock/MATH-REBUILD-SPEC.md`
- `docs/foundations/methodology-lock/METHODOLOGY-v1.2-LOCKED.md`
- `docs/foundations/methodology-lock/RULER-CHECK-SPEC.md`
- `docs/foundations/methodology-lock/STATUS.md`
- `docs/foundations/methodology-lock/SUITE-LOCK.md`
- `docs/foundations/methodology-lock/CODING-EXEC-MODULE-SPEC.md`
- `docs/foundations/methodology-lock/WEDGE-RESULT.md`
- `docs/foundations/OVERNIGHT-AUTONOMY-PROMPT.md` — "while Michael sleeps" +
  `Repo: C:\Users\Michael\local-bench`
- `docs/foundations/approach-consolidation-and-mmlu-pro-2026-06-16.md`
- `docs/foundations/goal-assessment-2026-06-16.md`
- `docs/foundations/model-backlog.md`
- `docs/foundations/move2-difficulty-calibration-spec-2026-06-17.md`
- `docs/foundations/methodology-v1.1-proposal-2026-06-16.md`
- `docs/briefs/budget-forcing.md` — also contains `C:\Users\Michael\local-bench`
- `docs/briefs/phase3-finder.md`
- `docs/briefs/refactor-s0-test-infra.md`
- `docs/briefs/task-01-runner-scorers.md`
- `docs/briefs/task-08-reasoning-effort.md`
- `docs/briefs/v1-bfcl.md`, `v1-ifbench.md`, `v1-math-dataset.md`, `v1-math-scorer.md`,
  `v1-probe-harness.md`, `v1-supergpqa.md`
- `docs/deploy/cloudflare-pages.md` — "Michael provides Account ID + API token"
- `docs/external-crossref.md`

All are internal; none are served.

### A3. `.superpowers/sdd/` files (untracked, not in .gitignore)

The `.superpowers/sdd/` directory is untracked (`git status` shows `??`) and is NOT
in `.gitignore`. It contains agent task reports that include:

- `.superpowers/sdd/progress.md:19` — "Qwopus fold-in (Michael, 2026-06-23)"
- `.superpowers/sdd/progress.md:24` — "27B follow-up decisions (Michael 2026-06-23)"
- `.superpowers/sdd/task-2-report.md:27` — `cd "C:\Users\Michael\local-bench\web"`
- `.superpowers/sdd/task-2-report.md:54` — `C:/Users/Michael/local-bench/web`
- `.superpowers/sdd/task-3-report.md`, `.superpowers/sdd/task-8-report.md` — same

These are never staged or committed and are not uploaded. However, because `.superpowers/`
is not in `.gitignore`, it would appear in `git status` if the repo were ever pushed or
shared. Recommend adding `.superpowers/` to `.gitignore` before any repo-sharing scenario.

### A4. Source run JSONs with `output_path` containing Windows user path

The `cli/runs/` directory is gitignored (`runs/` pattern in `.gitignore`) and never
deployed to the site. The ladder run JSONs contain:

```
"output_path": "C:\\Users\\Michael\\local-bench\\cli\\runs\\ladder-qwen36-27b-Q2_K.json"
```

Present in: `ladder-qwen36-27b-Q{2_K,3_K_M,4_K_M,6_K,8_0}.json`,
`ladder-qwen36-27b-qwopus.json`, `smoke-qwen36-27b-q4.json`, `smoke-qwopus.json`,
and all files under `_superseded-gemma-answer-only/`.

`cli/runs/SKIPPED-kld.txt` also references `PYTHONPATH=/mnt/c/Users/Michael/` and
`/mnt/c/Users/Michael/local-bench/cli/runs/kld-qwen36-27b.json`.

None of these reach the published site. The build pipeline (`web/build_data.py`) strips
`output_path` when producing `web/out/data/runs/*.json` — confirmed by inspection: the
published run JSONs contain no `output_path` field.

### A5. Huggingface XET log (gitignored)

`data/cache/huggingface/xet/logs/xet_20260614T153125663+1000_38312.log` contains
`C:\Users\Michael\local-bench\...` paths in structured log lines. This file is correctly
matched by the `.gitignore` `data/cache/` pattern and is never published.

---

## BUCKET B — Published-artifact leaks (LAUNCH BLOCKERS)

These are findings in files that either (a) will be deployed to `web/out/`, or (b) are
git-tracked source files that could leak operator identity if the repo were ever shared
publicly.

### B1. LAUNCH BLOCKER — Hardcoded Windows user path in git-tracked test file

**File:** `cli/tests/test_ifbench.py`
**Line:** 285
**Content:**
```python
reference_root = Path("C:/Users/Michael/AppData/Local/Temp/local-bench-ifbench-ref")
```

This file **is git-tracked** and will be visible if the repo is ever published. It is
not served in `web/out/` so it is not a live site leak for v1 Wrangler upload.
However, it is a leak in the committed source and should be patched before any
GitHub/public-repo scenario.

**Recommended fix:** replace the hardcoded path with
`Path(tempfile.gettempdir()) / "local-bench-ifbench-ref"` or an environment variable.

**Blocking status:** Blocking for any public-repo scenario; not blocking for the current
direct-upload-only v1 launch. Flag for immediate remediation regardless.

### B2. INFORMATIONAL — `cli/runs/_superseded-gemma-answer-only/README.md` is gitignored

```
README.md:11: Scrapped from the active dataset per Michael's call (2026-06-23)
```

This file is under `cli/runs/` which is gitignored. Not a blocker.

---

## Checks that passed cleanly

- **`web/out/` complete sweep** — no "Michael", "Russell", "clarityconsultive", `@outlook`,
  `@gmail`, `C:\Users\`, or unix home paths anywhere in the published artifact.
- **Source map / build info files** — no `.map`, `.tsbuildinfo`, or `.DS_Store` files found
  in `web/out/`.
- **Absolute build paths in JS bundle** — `_next/static/chunks/` JS files contain no
  `C:\Users\Michael` strings.
- **Published run JSONs** (`web/out/data/runs/`) — `output_path` field stripped by
  `build_data.py`. Confirmed for all six published run files.
- **Email addresses** — no `@clarityconsultive`, `@outlook`, `@gmail`, `@icloud` anywhere
  in the working tree (excluding `.git`).
- **GitHub/GitLab URLs** — no owner-identifying repo URLs in the working tree.
- **Deploy script** — `scripts/deploy-site.ps1` holds no PII; credentials from env vars.
- **`app/layout.tsx`** — no `author`, `og:`, or `twitter:` tags. Generic site title only.

---

## Pre-deploy checklist (re-run before each deploy)

The existing gate in `docs/deploy/cloudflare-pages.md` specifies:
```powershell
grep -riE "michael|russell|clarity|outlook" web/out/
```
This command must return no output. It currently returns no output (PASS).
