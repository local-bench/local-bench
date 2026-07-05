# Suite-v2 / index-v3.0 — execution coding axis + math promotion

Status: **APPROVED DIRECTION 2026-07-05** (owner: "do it right the first time — otherwise we
re-run all the benchmarks, which take the most time"). Design red-teamed by GPT-5.5 Pro (oracle
session `suite-v2-coding-redesign`, transcript retained); its five structural amendments are
ADOPTED below and marked [oracle]. Owner sign-offs still pending: final weights (§3), verifier
Docker install on the maintainer machine, canary GPU smoke.

## Why

The v1 coding axis is `lcb` — an exec-free LiveCodeBench output-prediction proxy (n=129) chosen
at bring-up so standard runs need no sandbox. Measured: Gemma-4-12B scores 90.7% raw / 95.1%
conditional (CI 85.3–95.3) against 68–76 on knowledge/instruction/tool. A 12B nearly saturates
the axis; at n=129 the CI is ±5pts, so the axis cannot separate the 27–70B class the board most
needs to rank. The static index weights coding 20%, doubling the damage. index-v3.0 has zero
published rows, so the fix folds into v3 for free — each model is benchmarked once on the final
suite.

## The axis change

- **Ranked coding = BigCodeBench-Hard, Instruct form, execution pass rate** (n=148 frozen items,
  already in suite/v1; the item records carry both instruct_prompt and complete_prompt — ranked
  rendering uses instruct_prompt). [oracle: Instruct not Complete — chat/instruct models dominate
  local use; Complete stays diagnostic; public hard-set results show 0–33 Instruct range with
  useful mid-size separation — headroom, not saturation, not an AppWorld-like floor.]
- **`lcb` is demoted to diagnostic** and is NEVER pooled into the coding axis (different
  construct; pooling would launder the saturated proxy back into the headline). Old rows keep
  displaying it as legacy.
- **Math is promoted now**: olymmath_hard (100) + amo (39), both frozen, judge-free
  (parser-gradable). Genuinely hard; promoting later would force another full-board re-run.
- **Long-context (ruler_32k) stays candidate/diagnostic**: mandatory 32k contexts would raise the
  VRAM floor and strip ranked eligibility from small-card users.

## Weights (index-v3.0)

Full Local Intelligence Index:
  agentic .40 · knowledge .15 · instruction .15 · tool_calling .10 · **coding .15** · math .05
  [oracle: coding to .15 funded from agentic — verified-exec coding has the strongest trust story
  on the board while community agentic is self-reported-with-label; under-weighting the fixed axis
  wastes the fix. Owner may veto back to .45/.10.]

Static index (static-suite-v2):
  knowledge .25 · instruction .25 · tool_calling .20 · coding .20 · math .10

Statistical honesty rules [oracle]: publish per-axis CI bars; n=148 half-widths run ±5–8 raw pts,
so a 3–5 raw-point coding gap is NOT a ranking claim; rank containment applies when coding deltas
< ~8–10 raw pts (or full-index deltas < ~1pt driven mainly by coding). Model-vs-model coding
comparisons use paired-over-items methods, not independent CIs.

## Trust design — the big amendment [oracle, reverses the draft]

**Docker is required for the VERIFIER, not the submitter.**

- Submitters generate code with any OpenAI-compatible runtime — no sandbox needed to produce a
  ranked submission. Local execution (if they have Docker) is a preview convenience; their
  verdicts ride along as claims.
- **Code artifacts are schema-REQUIRED per coding item — hard reject if absent**: raw transcript,
  extracted answer, sanitized code, deterministic assembly recipe (or assembled-program hash),
  item/prompt/test shas, extractor + harness + container-image digests, verdict + timeout/OOM
  status + runtime + truncated stdout/stderr, optional submitter verdict signature.
- **The ranked coding score is produced (or confirmed) by project re-execution** of those
  artifacts on the maintainer machine — CPU-only, minutes per run, deterministic, automatable
  (joins ZT-1's auto-accept gates). Self-reported exec verdicts NEVER default-rank; unverified
  rows sit provisional/contained until re-exec.
- Project rows: the run attester signs the exec verdict block (mirrors AppWorld verdict
  attestation).

Release/eligibility matrix:
- **Ranked Full v3** — 6 axes (mmlu_pro, ifbench, tc_json_v1, bigcodebench_hard, olymmath_hard+amo,
  appworld_c). Needs WSL/AppWorld for agentic; coding needs NO submitter sandbox.
- **Ranked Static v3** — 5 axes (no agentic), same verified coding axis. "Coding" means one
  measured thing sitewide.
- **Static-Core diagnostic (unranked)** — knowledge/instruction/tool(+math) for zero-setup users,
  clearly labeled not comparable to ranked static. [oracle]
- v1 release pairs stay registered (reproducibility) but are legacy-labeled and excluded from the
  default board from day one — the launch never shows two "current" index identities. [oracle]

## Code-specific budget + extraction policy [oracle: "the one most likely thing to bite you"]

The generic bounded-final final-answer reserve (1,024 tokens) is dangerous for code: a model can
think well, get force-closed, then lack budget to emit a complete solution — scoring as "bad at
coding" when the harness truncated it.

- Coding items get a **code-specific final reserve: 4,096 tokens** (blunt safe default);
  thinking budget = min(8192, max(0, T_i − 4096)).
- No stop sequence may match triple backticks or any code-fence token.
- Extraction: golden test corpus REQUIRED before release registration — raw code, fenced,
  multiple fences, prose-before/after code, no fence, malformed fence, backticks inside string
  literals, thinking tags, truncated output. Ambiguous extraction = CONFORMANCE FAILURE, not a
  wrong answer. Extractor version digest is part of scorecard identity.
- Canary decides whether coding items run answer-only by default (if forced two-pass shows
  extraction risk, coding renders answer-only — allowed per-bench policy, recorded in the
  release manifest).

## Verifier sandbox hardening [oracle]

Upstream bigcodebench evaluate is a reliability guard, NOT a security boundary; generated code
and test code share a module, so a contaminated/adversarial model can attack the harness.
Verifier requirements: rootless Docker (or gVisor) — the module's fail-closed gate stays; image
pinned by digest, not tag; no network; no Docker socket; non-root; read-only bench/test mounts;
per-task wiped tmpfs, no shared writable cwd or site-packages; pids/cpu/mem/file-size limits;
clean interpreter per task; kill the process TREE on timeout; sentinel checks that fail the task
on mutation of unittest/core asserts/builtins/sys.modules/harness globals. Pre-launch adversarial
probes (all must be caught): assertEqual no-op patch, TestCases redefinition, os._exit(0),
sitecustomize/shadow-module planting for later tasks, reading mounted test files, monkeypatching
open/importlib/subprocess/signal, child processes outliving timeout, hard-coded answers from
inspecting test inputs.

## Re-freeze mechanics

bigcodebench_hard / olymmath_hard / amo item files gain canonical per-item budget + sampling
fields (prompt/test content byte-identical). **Item IDs stay stable** — metadata-only refreeze;
the release manifest + scorecard identity carry the version boundary. Any FUTURE semantic prompt/
test change uses a new item id (or @rev marker). Every per-item result row records release_id,
manifest_sha, item_record_sha, prompt_content_sha, test_sha, budget/sampler policy revs,
extractor + scorer revs — nothing downstream may compare item scores across releases without a
manifest match. [oracle]

## Sequencing (build order) [oracle reorder adopted]

1. Lock artifact schema + extractor policy + code budget policy (this doc + CLI build).
2. Golden extraction tests green.
3. Verifier bring-up on the maintainer machine (rootless Docker in WSL2) — BEFORE release
   registration. ← owner go required (system install)
4. Upstream ground-truth check (reference solutions pass) + the adversarial sandbox probes.
5. 10–20 item canary on Gemma-12B + the Qwen fine-tune; manually inspect raw → extracted →
   sanitized → verdict. ← owner go required (GPU)
6. Re-freeze + register full-6axis / static-5axis release pairs (server + CLI).
7. Full re-runs (as-a-user path).
8. Maintainer re-exec of coding artifacts; attester signs.
9. Scorecards with CI bars + rank containment.
10. Site flip (wave-4: methodology v3, weights, Docker-optional-submitter copy, Static-Core).

## Decisions log

- Saturating proxy replaced by execution, not by a harder proxy (proxies re-saturate within a
  model generation).
- lcb never pooled [oracle confirms draft].
- Instruct form ranks; Complete diagnostic [oracle amendment].
- Coding .15 / agentic .40 [oracle amendment; owner may veto].
- Docker verifier-side only [oracle amendment, reverses draft; kills the submitter-friction
  objection AND makes coding the strongest-trust axis].
- Self-reported exec verdicts never default-rank [oracle amendment — reproducibility makes
  "agentic parity" the wrong frame].
- Code-specific 4,096 final reserve [oracle amendment].
- LiveCodeBench exec NOT added now (second unproven harness = release risk; revisit at suite-v3
  if contamination-windowing becomes necessary).
- Item IDs stable across metadata-only refreeze [oracle confirms draft].
