# Deeper-Budgets Migration — rev 3 (oracle dispositions folded; Codex implementation brief)

> Rev 1 -> oracle (slug `deeper-budgets-migration`, GPT-5.6 Sol Pro, 29m, verdict
> **SHIP-WITH-FIXES**, full text in oracle session artifacts). Rev 2 (code audit) fixed the
> turn-cap facts + per-turn semantics before the verdict landed. Rev 3 = final design, ALL
> oracle blockers adopted. Owner directive 2026-07-31: raise saturating limits NOW, one
> migration, full overnight autonomy, usual chain.

## Headline changes vs rev 2

1. **Suite v2 is OUT.** The static budget tuple becomes **profile-owned** and is consumed
   from the `ResolvedExecutionContract`, never from suite items. Suite + itemsets +
   subset_hash stay BYTE-IDENTICAL. Legacy suite `max_tokens: 16384` remains authoritative
   only for legacy profiles/lanes and must not shadow the new profile.
2. **Release is HELD** until the RTX PRO 6000 is installed and exact-config validation
   passes (oracle blocker 8). Tonight: implement + full tests + v9 ceremony + deploy
   backward-compatible site changes + stage the fail-closed release script. PyPI publish
   fires only when the 64k/f16 launch checks pass on real hardware, immediately followed
   by the head reruns (owner go-ahead required — GPU-ask-first).
3. Corrected arithmetic: **325** reasoning-cap items (100+39+110+72+4), not 327; worst-case
   additional think ≈ 7,987,200 tokens ≈ 35.8h at 62 tok/s. Agentic stats describe the
   canonical scored stage of the two-run stability campaign (drift 0.0pp; state this in
   docs when quoting).

## The new operating point (all values profile-owned, frozen at mint)

Profile id: `generic_think_tags_32768_v1` — minted ONLY after every field below is settled.
Public identity: `execution_profile.semantic_sha256` over the canonical serialized tuple;
resume identity, delta compatibility, worker activation, and site display all derive from
the same payload.

```
static_think_tokens                  = 32768   (pass-1 max_tokens)
static_final_tokens                  = 16384   (pass-2 max_tokens)
static_max_generated_tokens          = 49152   (two-pass total allowance; budget_audit promised total)
server_context_tokens                = 65536
agentic_max_turns                    = 40 provisional — dev-calibrated, see rule R2
agentic_max_output_tokens_per_turn   = 1024 (unchanged; conditional 2048, rule R3)
agentic_max_generated_tokens_per_task= 65536 provisional (validate >= dev p99, rule R2)
agentic_context_tokens               = 32768 (pinned explicitly; today's implicit value)
kv_cache_k_dtype                     = f16
kv_cache_v_dtype                     = f16
context_fit_policy                   = exact-or-fail (no llama.cpp fit/degradation)
context_extension_policy             = none (native model context must cover 65536; no silent RoPE/YaRN)
per_task_timeout_s                   = derived: scale with turn cap (24->1800 baseline; 40 -> 3000; keep "budgets decide, watchdog only catches deadlocks")
```

Naming per oracle: the agentic per-turn field is `agentic_max_output_tokens_per_turn`
(one-pass TOTAL incl. reasoning) — never "think cap". Gemma: `gemma4_channel_8192_v1`
stays the ONLY gemma profile in 0.4.14 (docs must not claim every thinking format moved);
a 32k gemma sibling is minted when a gemma model is next actually benchmarked.

Explicit `generic_think_tags_8192_v1` remains selectable in 0.4.14; `auto` resolves
thinking models to the 32768 profile and FAILS CLEARLY (offering the explicit legacy
profile) when 65536 ctx is infeasible; hardware availability never silently alters auto
resolution; old-campaign resume stays 8k (auto never re-resolved on resume).

## Pre-registered rules (write into docs with the release; never tune on test)

- **R1 (static cap review):** do not reconsider 32768 until >= 3 independent base-model
  families have complete 32k rows; reopen only if >= 2 families show > 25% cap saturation
  on the same axis.
- **R2 (turn cap + task bound):** on the PRO 6000 during non-publishable validation, run a
  fixed AppWorld DEV subset at max_turns in {32, 40, 48}; adopt the smallest value at
  which the dev trajectory distribution stops being materially cap-dominated
  (cap_exceeded_dev <= 10%); pre-registered default 40 if the curve is flat. Set
  agentic_max_generated_tokens_per_task >= dev p99 cumulative usage (provisional 65536).
  Label as "Local-bench Protocol C operating point" — no upstream AppWorld parity claims.
- **R3 (per-turn output):** if tonight's fusion bundle shows > 2% of agentic turns ending
  finish_reason=length, raise per-turn to 2048 in the same mint; else keep 1024 and
  publish per-turn p95/p99/max as a watched metric.

## Codex task list (tonight; hold PyPI publish)

T1. **Profile-owned budgets.** Registry entries own the full tuple; refactor
    `_generic_runtime(entry=...)`; remove `CAPPED_THINKING_THINK_BUDGET` from ranked
    resolution (legacy-compat only); `budget_forcing`/request shaping + `budget_audit`
    consume the ResolvedExecutionContract; suite items no longer shadow ranked budgets.
    Release test proves simultaneously: (a) suite_hash + subset_hash byte-identical
    pre/post; (b) 32k-profile request trace = 32768 then 16384; (c) audit promised total
    49152; (d) explicit-8192 path byte-identical behavior to 0.4.13.
T2. **Contract + semantic digest.** Extend ResolvedExecutionContract with the tuple;
    `semantic_sha256`; thread resolver -> campaign manifest -> resume identity -> agentic
    resume seed -> host/worker activation -> LoopConfig construction -> persisted run
    config -> public execution profile. Test: changing agentic_max_turns 40->39 refuses
    resume BEFORE any model request.
T3. **Public schema v2 (additive union).** v1 = existing structured fields (old rows keep
    parsing); v2 = v1 + complete budget/serving tuple, REQUIRED for the 32768 profile.
    Site TS `PublicExecutionProfile` discriminated union. This is contract validation, not
    a model admission pre-gate. KNOWN_EXECUTION_PROFILES legacy map untouched (never
    repoint to 32768).
T4. **Agentic LoopConfig from contract.** max_turns / per-turn / cumulative task bound /
    context window / per_task_timeout derived from contract with no default shadow;
    cumulative bound reuses frozen `cap_exceeded` + informational
    `cap_dimension: "task_output_tokens"`; diagnostics add per-turn p95/p99/max, history
    truncation rate, cumulative-cap-hit rate. Contract v9 ceremony after
    (`covered_behavior.budgets.*` lines change). C6 attempts + C8 matrix untouched.
T5. **Probe split.** Behavioral probe keeps a SMALL probe-local generation bound (never
    inherits 32k); new capacity probe asserts from live runtime evidence: effective ctx
    65536, cache types f16/f16, fit/degradation off, slot allocation. Verify exact llama.cpp
    b10076 flag names for cache types + fit; assert from server properties, not launch
    args. Also validate model native/effective context >= 65536 from GGUF metadata
    (n_ctx_train) — fail closed, no silent scaling.
T6. **Timeout derivation.** HTTP read timeouts, no-progress watchdog, campaign/keepawake
    leases derived from profile maximums at min supported throughput (32k think @ 10 tok/s
    ≈ 55 min/request); no fixed ~24h campaign constants; keepawake renewable.
T7. **Site transition package (deploy tonight, backward-compatible).** Board-level notice
    ("Operating point changed from 8k static reasoning to 32k. Cross-profile scores are
    not compute-matched." — gated to appear once any 32k row exists); prominent
    Current/Legacy operating-point badge; human-readable profile summary line; family-head
    /best-variant/Pareto selection made profile-aware; delta suppression keyed on complete
    semantic digest; no cross-profile rank-change copy anywhere. SUPERSEDES stays reserved
    for invalid->corrected rows: the future 32k pair does NOT supersede the valid 8k pair.
T8. **Docs/copy.** submit page ctx 65536 for the new profile; README/examples updated or
    marked legacy; methodology page states both operating points historically (8k docs
    preserved as historical); predeclared rules R1-R3 published; announce copy = Michael.

## Cross-artifact consistency gate

Use the oracle's 35-named-pair table verbatim (oracle session `deeper-budgets-migration`
artifacts; key pairs: suite<->shaper, registry<->_generic_runtime, contract<->request
trace, contract<->resume, old-manifest<->0.4.14-resume, contract<->LoopConfig,
profile<->llama launch evidence, profile<->probe, budgets<->watchdogs/keepawake,
schema<->TS union, legacy-IDs<->KNOWN map, digest<->delta suppression, 8k-row<->SUPERSEDES,
PyPI provenance<->rows). Every pair gets a named test or a written N/A.

## Rollout order (oracle-approved)

1. Tonight's fusion 8k run lands under 0.4.13 UNTOUCHED -> verify, supersedes link (over
   the invalid row only), matched 8k delta, preserve campaign dir + contract.
2. Settle remaining facts (below), freeze the tuple, mint the profile.
3. Codex T1-T6 + tests; contract v9 ceremony; full suite green.
4. Deploy site package (T7) FIRST — site understands the profile before any row exists.
5. RTX PRO 6000 install (Michael) -> non-publishable exact-config checks: 65536/f16/f16
   launch evidence, behavioral+capacity probes, static request shaping trace, agentic
   config, watchdog survival; R2 dev calibration -> final turn cap + task bound.
6. Publish stable 0.4.14 -> immediately start base + fusion 32k head reruns (owner go).
7. After first complete head row: publish saturation audit (per-axis think-cap rate,
   final-cap rate, turn-cap rate, cumulative-cap rate, history truncation, wall time,
   peak memory). Never alter the profile in place.

## Facts pinned tonight (before freezing the tuple)

- [x] PUBLISHED 0.4.13 wheel (venv-0413 site-packages) confirms: max_turns=24,
      max_output_tokens_per_turn=1024 (one-pass total via GenerationParams),
      context_window=32768, per_task_timeout_s=1800. Signed v8 contract embeds
      covered_behavior.budgets.max_turns -> v9 ceremony REQUIRED on change.
- [x] GGUF metadata (run dir gguf_metadata.json): `qwen35.context_length = 262144` ->
      context_extension_policy=none satisfiable at 65536, no RoPE scaling.
- [x] Architecture is HYBRID (`qwen35`: ssm.* keys + full_attention_interval=4, 65 blocks,
      head_count_kv=4, key/value_length=256) -> KV ~= 2x4x256x2B x ~16 attention layers
      ~= 64KB/token -> 65536 ctx ~= 4.3GB KV total (+~2.1GB vs 32k) -> the 32GB 5090 FITS
      this family at the new operating point (~26-27GB est, measured 24,203MiB @ 32k).
      Dense-arch models (e.g. classic 32B: ~0.5MB/token -> 34GB @ 64k) remain the
      community-trap case: fail-closed feasibility error + explicit legacy profile is the
      answer; docs must state feasibility is architecture-dependent.
- [ ] Fusion bundle (tonight, post-landing): agentic per-turn finish_reason=length rate ->
      R3 decision; static saturation profile of a thinking fine-tune (fusion vs base).
- [ ] Measured VRAM at 65536/f16/f16 on the 5090 (brief non-scored spawn post-landing) —
      informational; canonical validation on the 6000.
- [ ] llama.cpp b10076 exact flag names for cache types + fit + slots (Codex verifies
      against the pinned binary's --help; assert from runtime properties regardless).
