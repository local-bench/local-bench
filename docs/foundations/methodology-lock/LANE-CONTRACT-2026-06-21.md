# Lane Contract — local-bench publishing + ranking (DRAFT v0.1, 2026-06-21)

Status: DRAFT for sign-off. Synthesis of the oracle (GPT-5.5 Pro, session `localbench-next-move`)
4-lane recommendation + the off-family validation finding. Defines how results are CLASSIFIED and
DISPLAYED so we never co-rank models the lane can't fairly measure.

## Why this exists
`ANCHOR-VALIDATION-RESULTS-2026-06-21.md` proved the capped-thinking lane is **systematically
mismatched to reasoning-distilled models** (R1-Distill, Nemotron score low not from low capability
but because greedy + an 8192 budget doesn't suit their native sampled/long-CoT regime). Dumping every
model into one sorted table would publish **lane-artifact rankings**. The fix is not to change the
locked methodology — it's to sort models into result classes and only co-rank within a class.

## The four lanes
| Lane | Role | Contents | Ranked? |
|---|---|---|---|
| **Strict Local** | PRIMARY — the Local Intelligence Index | normal instruct/chat models that complete cleanly under the locked lane | ✅ the leaderboard |
| **Native Reasoning** | SECONDARY (beta) | reasoning-distilled/native models needing sampling / long-CoT / special prompting | ❌ shown, not co-ranked in primary |
| **Frontier Reference** | REFERENCE | closed/API frontier models | ❌ grey reference bands only |
| **Quant-Drift (KLD)** | DIAGNOSTIC | quantization faithfulness vs a reference | ❌ separate metric, **never** in the composite |

## Admission rule (deterministic; no LLM judge)
A model enters **Strict Local (primary)** iff BOTH hold:
1. **Format-compatible** — passes the pre-run mechanical smoke test: produces a parseable final
   answer under the locked lane at a healthy natural-termination rate (literal `</think>` if it is a
   thinking model). Operational signal = `termination_rate` from a short probe run.
2. **Regime-compatible** — its model card / intended use does NOT *require* sampling (temp > 0),
   long-CoT beyond the 8192 think budget, or special thinking-pattern prompting to reach its stated
   capability.

Routing:
- format-compatible **and** regime-compatible → **Strict Local**.
- format-compatible but reasoning-distilled / regime-incompatible → **Native Reasoning (beta)**.
- fails the smoke test (wrong delimiters, runaway non-termination, no parseable final) →
  **excluded / lane-incompatible** (documented, not ranked — NOT evidence of low capability).
- closed/API → **Frontier Reference** (never ranked as a local model).
- quantization-faithfulness runs → **Quant-Drift**, never in the intelligence composite.

Borderline cases route to **beta + a note**, never silently into primary. The classification + its
signal (termination health + card regime) is recorded per model for auditability.

## Ranking + display contract
- **Within a lane:** rows sortable by the strict composite (primary) / the lane's own metric.
- **Across lanes:** comparison is **reference-only** — no shared rank numbers. Frontier shown as
  bands beside/above the primary table, not in rank positions.
- Every row carries its **lane label** + the relevant caveat.
- **KLD** lives in its own column/section, never folded into the composite or the intelligence rank.
- **Frontier framing (required):** "how local/open models perform relative to selected frontier
  references under local-bench's strict scoring — NOT each provider's best native performance."

## Local utility layer (per row, non-composite — oracle add)
Show alongside the score so a row answers "can I run it?" not just "how smart?": params, quant +
file size, VRAM/RAM class, context length, tokens/sec on a reference rig (if measured), license,
engine support, recommended deployment tier. (Site/data layer; gather opportunistically.)

## Public caveat (display copy)
> local-bench's primary index is the **Strict Local Lane**: deterministic, budget-capped,
> strict-scored local-deployment quality, no LLM judge. Models whose stated capability depends on
> native sampled / long chain-of-thought are evaluated in a separate **Native Reasoning (beta)** lane
> and are not co-ranked — a low primary-lane score means "not well-measured by this lane," not "low
> capability." Frontier models are shown as **reference bands**, not ranked as local models.
> **Quant-drift (KLD)** is a separate quantization-faithfulness signal, not an accuracy score.

## Where current + incoming data lands
- Qwen3.5 ladder 0.8/2/4/9B → **Strict Local** (terminates healthy; the live v1 leaderboard).
- Granite-3.3 2B/8B → **Strict Local** (validation placed them correctly).
- R1-Distill-Llama-8B, Nemotron-Nano-4B → **Native Reasoning (beta)** (the lane-limited anchors).
- gpt-5.5 / opus / gemini / sonnet / gpt-4.1-mini → **Frontier Reference** bands.
- **Incoming Qwen3.6-27B quant sweep** → Strict Local accuracy rows (base lane) + **Quant-Drift (KLD)**
  for the degradation signal. Distills routed by the admission rule on inspection (coder/instruct →
  Strict Local if healthy; reasoning-distill → Native Reasoning beta).

## Site-agent work (web lane)
`data_sources.json` carries a `lane` field per source → `build_data` groups by lane → the table
renders same-lane sortable + cross-lane reference-only + the per-lane caveat. The campaign lane
supplies the `lane` label per run; web renders. (Hand-off, not a campaign edit to web/.)

## Open for sign-off
1. The two routing signals (termination-health threshold + card-regime) — exact threshold TBD from
   the Qwen-ladder + Granite termination rates (anchors: Granite ~100%, R1/Nemotron ~91–98% but
   regime-incompatible → beta on signal #2, not #1). Proposal: primary requires regime-compatible
   AND smoke-termination ≥ (min Strict-Local-cohort − 10pp); else beta.
2. Whether Native-Reasoning beta eventually gets its OWN fair lane (sampled/long-CoT policy) or stays
   display-only. (Defer; the validation says don't co-rank under the strict lane.)
