# Path-to-launch plan (oracle-synthesized, 2026-06-24)

GPT-5.5 Pro path-forward consult (`localbench-path-forward-launch`). Combined v1 launch
(install -> run -> submit -> board). This supersedes the ad-hoc sequencing; it is the launch spine.

## VERDICT
- **AppWorld-C TODAY = NO-GO to publish.** Sandbox is credible; the loop/diagnostics/replay/GPU
  runs/repeats/site integration are NOT yet proven.
- **AppWorld-C on the v1 path = GO, as a 0-weight candidate column, ONLY if it clears the gates.**
- **Biggest risk = CONSTRUCT VALIDITY:** a beautiful, secure column that measures Protocol C harness
  artifacts (parser brittleness, sandbox friction, cap/timeout, syntax/runtime failures, prompt-format
  compliance) instead of interactive API-coding skill. The sandbox de-risked cheating, not validity.
- **JSON/BFCL companion = NOT a v1 requirement** if AppWorld-C is narrowly named + 0-weight. Required
  before promotion / headline weighting / any broad "agentic capability" claim. Write the SPEC now.

## NAMING (brutally narrow)
Ship only as: **"Candidate: AppWorld-C interactive API-coding ASR, 0% Index weight."** NEVER "agentic
score / tool-use / autonomous-agent / reasoning-agent" or in the headline Index. Every candidate number
carries a visible 0-weight badge + diagnostics beside it.

## CORRECTED SEQUENCE (not loop -> full benchmark -> site -> QA)
- **Phase 0 (now, CPU): freeze the public contract** — `launch_freeze_v1.json`: board hash, suite
  hashes (MMLU-Pro 400 / IFBench 294 / AppWorld-C split if used), scorer version + wheel hash, model
  rows/quants/prompt/template/sampler, as-of date (2026-06-23 or a unified re-freeze), headline def
  (K+I only), candidate def (AppWorld-C 0% weight), submission-verifier rules, determinism wording.
- **Phase 1 (parallel, CPU):** A) Protocol C loop build [running]; B) **site parity repair + automated
  parity TEST** (renderer rows/Index/K/I/CI/sort EXACTLY match board_v1.json; candidates cannot affect
  Index; footer exposes board hash + as-of date) [site data already regenerated with gemma + parity ok;
  the TEST is the new ask]; C) QA prep + public copy (6 reviewers below).
- **Phase 2 (serial, before any scored GPU): FULL-LOOP VALIDATION GAUNTLET** — 55-canary suite THROUGH
  the complete loop (not just AppWorldSandbox); canned/fake model trajectories solve real dev tasks
  through the exact loop; trace-replay exactness (recorded blocks + frozen hashes -> same success bool +
  DB diff); rollback test (mutate then timeout/cap -> rollback to pre-block checkpoint); parser
  adversarial (no block / two blocks / markdown junk / hidden answer / malformed fence / extra prose /
  syntax err / runtime err); diagnostics correctness; AppWorld env validation under pinned hash.
- **Phase 3 (GPU, serial funnel):** 3.1 dev smoke (1 system, find loop bugs, no score); 3.2 dev lite
  (~36 tasks, 2 contrasting systems, check non-saturation + failure taxonomy); 3.3 FREEZE the AppWorld-C
  manifest (prompt, cap 24, per-block timeout + API-call safety cap, truncation, task IDs/order, retry,
  scorer, diagnostics schema, bootstrap, stability gate) -- after this NO prompt/cap tuning on scored
  tasks; if you fix an invalidating harness bug, DISCARD + rerun affected scored runs; 3.4 first full
  96-task pass across Qwen ladder + gemma (early-stop if best ~0 or near-perfect / all within noise /
  failures mostly parser-syntax-runtime-cap / order just mirrors IFBench+code-proxy / any canary
  regression); 3.5 **2 full reruns per displayed row** (abs delta >5pp -> 3rd + mean w/ task-clustered
  bootstrap; 1 task ~= 1.04pp so show CIs, avoid fine rank claims).
- **Phase 4:** integrate AppWorld-C ONLY if gates pass; else ship headline WITHOUT it + a "under
  validation" methodology note. Do NOT publish a bad candidate column just because agentic was reinstated.
- **Phase 5 (final serial):** freeze artifacts -> regenerate site from frozen artifacts -> clean
  install->fetch->run->my-run.json->verify->submit test -> submission adversarial tests -> multi-agent
  QA -> fix release blockers only -> re-freeze changed -> launch.

## MISSING / UNDERWEIGHTED (oracle)
1. **Submission tamper-resistance (v1 requirement):** server RECOMPUTES scores from per-item records
   (not trusting aggregate my-run.json fields); verify suite/scorer hashes + schema version; reject
   unknown task IDs / missing outputs / dup rows; file-size limits; escape model names; quarantine
   malformed; show scorer-verified vs self-reported. If recompute impossible, board must say submissions
   are self-reported (weaker -> prioritize recompute).
2. **Reproducibility wording:** "Scoring is deterministic from frozen artifacts + submitted outputs.
   Model reruns are reported with fixed settings, seeds where applicable, bootstrap CIs, and
   repeatability checks; NOT claimed bit-identical across hardware/software stacks."
3. **Site copy prevents overinterpretation:** above-the-fold headline = K+I; candidates separate 0%;
   AppWorld-C tooltip; contamination note (public/semi-public benchmarks; freeze hashes; discourage
   small-delta reading).
4. **As-of-date freeze visible on the site** (board frozen DATE + scorer hash + suite hashes), not buried.
5. **Cold-install QA:** clean env pip install wheel -> fetch-suite --frozen -> run -> verify -> submit;
   hunt local paths / WSL-only assumptions / missing CUDA messaging / hidden env vars / stale cache /
   post-fetch network dependence / wrong wheel contents / inconsistent hashes after reinstall.
6. **AppWorld-C is OPT-IN, not in the default user run** (`localbench run --include-candidate appworld-c`),
   or internal-only for first launch (the sandbox has Linux/bwrap/AppWorld-data assumptions -> risky as a
   default public on-ramp).
7. **Launch artifact bundle:** board_v1.json, renderer data, wheel hash, suite/scorer/model manifests,
   AppWorld-C manifest (if enabled), signed release manifest, QA report, known limitations.

## SIX QA REVIEWERS (for #32)
1 scorer/math/reproducibility · 2 install/run/submit on a clean machine · 3 site renderer/data parity ·
4 submission security + tamper resistance · 5 benchmark-methodology honesty · 6 AppWorld-C
harness/security/CONSTRUCT VALIDITY.

## DECISIONS FOR MICHAEL
- AppWorld-C ships ONLY as a validated 0-weight candidate (narrow naming); if validation fails, launch
  WITHOUT it. Accept that agentic numbers may not make the first launch if the gauntlet/funnel doesn't
  pass. (Recommended: yes — a bad candidate column is worse than none.)
- Submission verifier (server recompute) becomes a v1 launch requirement for the "submit + appear"
  promise. This is real deploy-side work.
- JSON/BFCL: spec-only for v1.
- Single unified freeze date is cleaner than split headline/candidate dates.

## CHEAPEST HIGH-IMPACT (oracle top list)
site-parity test · narrow rename · visible 0-weight badge · diagnostics beside AppWorld-C · full-loop
gauntlet · release manifest w/ hashes+as-of · server-side recompute · precise repro language · JSON
fast-follow paragraph · do not over-rank small deltas.
