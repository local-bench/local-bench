# bounded-final-v1 — the all-families ranked lane

Status: **APPROVED 2026-07-05** (owner), design reviewed by GPT-5.5 Pro (oracle session
`lane-registry-fix2`, 2026-07-05) and reconciled with an independent internal draft.
This document is the spec of record for index-v3.0. Implementation waves are tracked in the
session task list; deviations from this spec require updating this file in the same commit.

## Why

The launch board ranked only model families with a hand-verified reasoning-registry entry
(`status="ranked"`: Qwen3, Gemma 4). That gate conflated *how to enforce the lane* with *who may
enter it*, made non-thinking models permanently unrankable, and contradicted the project purpose:
a community benchmark anyone can run against ANY local model. The machinery underneath was already
mostly family-agnostic (generic HF-template renderer, family-agnostic conformance gates, llama.cpp
runtime budget forcing, family-agnostic agentic loop); this design removes the family gate and
replaces it with measured, auditable eligibility.

## The normalization principle (reader-facing, verbatim)

> Every model gets the same frozen generated-token budget per item; it may spend that budget on
> hidden reasoning or on the final answer, but only the extracted final answer is scored.

## Lane contract

```
lane            = "bounded-final-v1"
index           = "index-v3.0"        (axis weights unchanged from v2.1: A50/K15/I15/T10/C10)
tier            = "standard"          (unchanged)
sampler         = pinned greedy/temp-0, seeded (unchanged)

Per item i:
  T_i        = frozen total generated-token cap (16,384 for static axes unless the frozen cap
               matrix says otherwise; agentic uses per-turn T_turn from the frozen task budgets)
  MIN_FINAL  = 1,024
  THINK_CAP  = 8,192
  B_i        = min(THINK_CAP, max(0, T_i - MIN_FINAL))   # thinking sub-budget
  answer budget = T_i - actual reasoning tokens used     # thinking comes OUT of T_i, not on top

One execution profile per run, applied to EVERY item and EVERY agentic turn (no per-axis or
per-item mode switching). Only final_text is scored. reasoning_text is counted, audited, stored,
never scored. Total generated tokens must be <= T_i, verified from usage accounting (server usage
stats, else CLI-side tokenizer count; neither available -> diagnostic-only).
```

Key change from capped-thinking-v1: thinking tokens are no longer additive. A thinking model that
burns its full 8,192 sub-budget has 8,192 left for the answer on a 16,384 item; a non-thinking
model may spend all 16,384 on the answer. Equal total budget is the defensible fairness claim.

## Execution profiles (replace the family gate)

Profiles are versioned, individually digested, and allowlisted server-side. `model_match` metadata
may *suggest* a default profile for a model; it never gates rank.

### answer_only_v1
For non-thinking instruct models and thinking models run with thinking disabled.
- reasoning_mode: none; single pass; max_tokens = T_i
- prompt: canonical HF/GGUF chat template only (see Audits)
- stops: canonical tokenizer/template EOS/EOT only — never user-supplied
- scored text: response_text after generic special-token cleanup
- Ranked for ANY family that passes audits + conformance.

### generic_think_tags_8192_v1
For the `<think>…</think>` ecosystem standard (Qwen, DeepSeek/R1 distills, Granite, Nemotron,
GLM, Kimi, …).
- Two-pass forcing on raw /v1/completions (existing budget_forcing.py generalized):
  pass 1 max_tokens=B_i stop=["</think>"]; pass 2 = prompt + thinking + "\n</think>\n\n",
  max_tokens = T_i - reasoning used, stop = canonical EOT.
- Prompt rendered by the CLI from the canonical template (HF tokenizer / GGUF metadata);
  the server is never trusted to apply templates or reasoning parsers for ranked BYO runs.
- Activation (e.g. enable_thinking kwargs) comes from template introspection, not a closed enum.

### gemma4_channel_8192_v1
The current Gemma registry entry converted to an override profile (channel tags, forced close
"\n<channel|>", Gemma leak regexes). Its existence affects no other family.

### Adding profiles later
New profile = new id + digest added to the server allowlist; MUST NOT change scorecard_id and MUST
NOT invalidate in-flight bundles using other profiles. Semantics change to an existing profile =
new profile id (…_v2). Lane contract change = bounded-final-v2. Comparability change = index-v4.0.

### bench mode (strongest provenance)
CLI-launched llama.cpp with pinned flags (`--reasoning-budget 8192`, explicit reasoning format,
pinned minimum build). Output is still parsed and audited by localbench (never trust the runtime's
parser blindly; llama.cpp's default INT_MAX budget bug is why the explicit flag is mandatory).

## Ranked eligibility (the new gate)

```
ranked :=
      lane == bounded-final-v1 AND tier == standard AND index_version == index-v3.0
  AND execution_profile.digest in server allowlist (status ranked)
  AND scorecard_id == current v3 scoring object AND lane_spec_digest matches
  AND prompt_audit == canonical        # rendered with the pinned canonical template (sha256)
  AND budget_audit == exact            # T_i honored; usage accounting present
  AND sampler_audit == deterministic   # pinned params, seed
  AND suite_coverage == complete       # every item present; missing/errored items score 0
  AND conformance == headline-comparable
  AND all five axes measured
```

No family membership anywhere in the predicate. `PublishableCappedThinkingError` is replaced by
guidance: unsupported thinking profile -> offer the ranked answer_only_v1 path or a diagnostic
bounded-thinking run; never imply a family is unrankable.

### Agentic axis rule
Same execution profile on every assistant turn; per-turn cap T_turn with
B_turn = min(8192, max(0, T_turn − 1024)); frozen AppWorld task/step budgets unchanged; no final
action/code produced = the step fails (model failure, not a conformance excuse). Ranked agentic
requires stateless serving semantics: every request body carries the full visible conversation
state. Self-reported agentic POLICY (owner decision 2026-07-05): continues to rank with the
`self-reported` label until spot-replication / server-replay ships; the default-board flip to
attested-or-replayable-only is deferred and revisited when replication exists.

## Conformance changes

Keep leaked-reasoning at 2% nonconformant / 25% diagnostic. Split the blunt gates:

```
budget_cap_hit_rate          model burned its full budget -> scored (wrong/partial), visible
                             diagnostic, NOT headline-excluding
measurement_truncation_rate  harness/server truncated below the promised T_i (ctx too small,
                             timeout, max_tokens != T_i) -> headline-excluding
empty_final_rate             extraction produced empty final -> item scores 0, visible, NOT
                             automatically nonconformant (bad models rank low, not vanish)
ambiguous/contaminated_final scored text == reasoning text, or reasoning markers in final ->
                             headline-excluding at 2%
```

Conformance measures MEASUREMENT CORRUPTION, not model incompetence.

## Identity & digests (fixes the whole-registry-hash problem)

Today `scorecard_identity` hashes the entire reasoning registry, so ANY family addition
invalidates in-flight submissions (validate.py digest check). Replace with:

```
scorecard_id             = digest(index_version, scoring registry digest, scorer versions,
                                  CI method, lane_spec_digest, cap_matrix_digest)
execution_profile_digest = digest(the selected profile only)
profile_catalog_digest   = informational only; NOT part of scorecard_id
```

Run manifests embed: lane, lane_spec_digest, scorecard_id, execution_profile {id, digest,
reasoning_mode, caps, forced_close, parser}, prompt_renderer {source, hf_model_id, revision,
chat_template_sha256, template_kwargs, answer_stop}, sampler pins. Server-side validation checks
scorecard_id + lane_spec_digest + profile digest ∈ allowlist; it no longer cares whether the
submitting CLI knows about unrelated newer profiles. scorecard_version -> 3.

## Migration

- index-v2.1 / capped-thinking-v1 board is frozen as LEGACY: not comparable to v3, never mixed.
  With exactly one ranked row, no separate legacy board page: the old score stays visible on the
  run/model page with an explicit legacy-lane label and a methodology note.
- The Gemma 4 12B IT (QAT Q4_K_XL) row is RE-RUN under bounded-final-v1 (recommended profile:
  bounded thinking if it passes, else answer_only_v1) and published as the first v3 row. The old
  score is never carried into the v3 rank, footnoted or otherwise.
- The no-agentic fallback lane (static renormalization) carries over under v3 semantics as
  static-suite-v2, same never-comparable rule.
- board_v1.json remains untouched (pin 3d058e6074bd781cc488c03255904b5f9599e37e).

## Threat model deltas (severity-ranked; full table in the oracle transcript)

CRITICAL — template smuggling (ranked runs must render from the canonical published template,
pinned by sha256; custom templates = diagnostic-only) · server parser abuse (raw completions +
local parsing for ranked BYO) · model identity spoofing (unchanged posture: hashes, labels,
review) · self-reported AppWorld gaming (policy above; replication on roadmap).
HIGH — stop-token cherry-picking (canonical stops only) · per-bench mode switching (one profile,
request-body audit) · selective erroring (full manifest, missing=0) · degenerate non-terminators
(bounded forcing + timeouts; cap-hit scored) · pure single-pass total cap for thinkers (forbidden:
reintroduces mid-think zero-scores; force-close is the safety mechanism).
MEDIUM — generic force-close not "native" for some families (methodology says so plainly; overrides
versioned) · template/tokenizer mismatch (pin + display renderer source) · runtime default drift
(pin llama.cpp build; vLLM --generation-config) · profile allowlist creep (overrides are shims;
answer_only_v1 always available) · contamination by fine-tunes (existing posture) · 10x-token
winners (efficiency view + cost columns; never blended into the score).

## Site consequences (wave 4)

- Methodology: new lane section around the normalization sentence; profiles explained;
  "eligibility is measured, not allowlisted"; legacy lane note; self-reported agentic policy.
- Homepage: DELETE "Only Qwen3- and Gemma-family reasoning modes are board-rankable today…".
- Onramp: remove the rankable-family filter (all ~102 catalog models eligible); per-model
  recommended profile; preflight smoke status.
- Board: execution profile is part of row identity; default view collapses to best row per
  artifact; efficiency view (score per generated token / wall-hour) as a secondary sort; new
  visible columns: reasoning mode, profile, reasoning/final tokens, cap-hit rate.

## Rollout order

0. This spec committed (wave 0).
1. Identity/schema refactor FIRST (per-profile digests; scorecard v3) — before any new profiles.
2. bounded-final-v1 + answer_only_v1 -> every family ranked-eligible immediately.
3. Re-run the Gemma row under v3; regenerate board; legacy-label the old score.
4. generic_think_tags_8192_v1 (generalized two-pass forcing, open activation, derived stops).
5. Gemma override profile; delete the family gate error path.
6. Site wave (methodology, homepage sentence, onramp unlock, efficiency view).
7. BYO run-mode hardening (audits) + QA/red-team wave; then seed 2-3 diverse families
   (R1-distill, Llama, GPT-OSS/GLM) as project-run v3 rows before announcing.

## Decisions log

- 2026-07-05 UNCAPPED THINKING REJECTED for ranked lanes (non-reproducible across ctx sizes,
  unfair across consumer GPUs, rewards non-termination, still needs force-close plumbing,
  wall-time blowup). Allowed as diagnostic only.
- 2026-07-05 One headline rank; no thinking/non-thinking divisions.
- 2026-07-05 Cost never enters the composite; displayed + efficiency view + tie display order.
- 2026-07-05 Self-reported agentic keeps ranking WITH LABEL until replication ships (owner
  accepted Claude's recommendation over the oracle's stricter default).
- 2026-07-05 Equal-total-budget semantics adopted (oracle correction of the internal draft, which
  had kept additive think budgets).
