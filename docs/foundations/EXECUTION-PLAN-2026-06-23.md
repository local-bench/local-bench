# local-bench — execution plan (oracle-informed, parallelized)

Date 2026-06-23. Source: GPT-5.5 Pro (oracle) `localbench-execution-sequencing-parallelization-plan`,
weighed against the CLI agent's analysis. Outcomes > speed; parallelize where safe.

## Headline calls
- **Publish v1 once gemma is de-ranked/labeled — do NOT block v1 on the gemma re-run.** Risk =
  "answer-only floor presented as comparable headline data," not "gemma missing a number."
- **Registry SPINE before the gemma re-run; full registry maturation after** (not a hotfix — the
  error was lane-conformance/activation-identity; not the full cathedral — infra drag for a solo dev).
- **Idle GPU > untrusted runs.** Don't keep the 5090 busy while lane semantics / scorecard identity
  / slice selection are unsettled.
- **gemma answer-only data: SCRAPPED from active set** (archived `cli/runs/_superseded-gemma-answer-only/`).

## Critical path (note: first step is NOT GPU)
public truthfulness → lane-conformant harness (registry spine) → gemma Q4 thinking VALIDATION →
gemma Q4 full run → optional Q6 / broader families.

## Revised P0
- **P0.0 public-surface safety:** gemma → diagnostic/superseded, removed from headline rank, kill
  the cross-family plateau claim, nemotron (non-native activation) → diagnostic. Publish-gate on
  lane clarity.
- **P0.1 lane-conformance harness fix (registry spine):** `ReasoningRegistryEntry` + qwen + gemma4
  entries, gemma activation, `ForcingFormat`, answer_budget fail-closed, prompt/stop/provenance hashes.
- **P0.2 gemma Q4 native-thinking validation + run.**
- **P0.3 remaining footguns:** function_calling vs agentic_exec terminology; lane-table clarity;
  lock top_k=1 (verified no-op); stratified frozen slices before scale-out.
- **P1 ship v1** (can publish before P0.2 if P0.0 done). **P2 more families @ Q4+Q6. P3 agentic
  AppWorld-lite pilot.**

## Parallelization map (GPU serial; everything else concurrent)
| Lane | Owner | Work | Parallel w/ GPU? | Sync gate |
|---|---|---|---|---|
| **A site/data safety** | site agent | relabel gemma, drop from headline, kill plateau copy, relabel nemotron | yes | before v1 publish (G0) |
| **B registry spine** | **Codex** | ReasoningRegistryEntry + qwen/gemma4 entries + ForcingFormat + gemma activation + answer_budget fail-closed + tokenizer(pinned) + fixtures | yes | before gemma validation (G1) |
| **C GPU validation** | **Claude** | static→smoke→forced-close→negative-control→conformance→full Q4 | NO (serial) | starts after B passes G1 |
| **D methodology/docs** | Claude | Core Text naming, lane policy, native-mode ranking, incident note | yes | match site before publish (G4) |
| **E agentic_exec design** | Codex | AppWorld-lite pilot scope, JSON protocol, verifier shape — DESIGN ONLY | yes | not a v1 blocker |
| **F stratified slices** | Codex | stratified frozen selector + manifests + hashes + migration | yes | before broad new-family expansion (G5) |
| **G model-breadth planning** | Codex | next-family manifests, tokenizer revisions, run queue | yes | GPU waits on gemma+slice gates |
| **H deferred** | nobody | submissions, full KLD, bespoke agent world, full registry polish | — | later |

## Gates (serialize these for correctness — NO skipping)
- **G0 safe-publish:** no answer-only gemma in headline rank; no ambiguous cross-lane composite;
  site+methodology agree; old gemma clearly diagnostic. → v1 may publish.
- **G1 static harness:** gemma native activation renders; correct thought/answer format + `<turn|>`
  stop; exactly one BOS; no pre-closed empty thought channel; stable prompt-fixture hash; Qwen
  BYTE-EQUIVALENT to today; answer_budget fails closed on missing max_tokens; pytest green.
- **G2 gemma conformance:** smoke + forced-close + negative-control + 30-50 item slice all pass
  (parse 100%, nonempty-answer ~100%, leak 0%); any cap-hit-correct manually audited. Else STOP+fix.
- **G3 public gemma Q4:** manifest complete; registry id + tokenizer revision + chat_template hash
  recorded; parser/leak pass; cap-hits visible+audited; scorecard frozen; old gemma kept diagnostic.
- **G4 release consistency:** site, methodology, scorecards, manifests, docs tell ONE story.
- **G5 slice freeze:** slice manifests committed; hashes stable; old-vs-new scorecard distinguished;
  no first-N mixed with stratified.

## Do NOT mix (separate scorecard identities)
pre/post-registry · first-N/stratified · answer-only/capped-thinking · native/non-native activation ·
old gemma diagnostic / new gemma headline. Mode selection: NO `max(answer_only, thinking)`.

## Defer (avoid the "benchmark zoo" death)
full gemma quant ladder (Q4 first; Q6 only if decision-relevant; Q3/Q5 only for a quant-sensitivity
article) · KLD campaign · v2 submissions · bespoke agent world (AppWorld-lite first) · Overall Local
Score (use Best Local Operating Mode — Core Text) · BFCL-as-agentic · deep ladders · GUI/WebArena/SWE-bench.

## 2-week shape
- **Wk1 (Jun23-29):** Lane A site safety + G0 → publish v1 if safe; Lane B registry spine + G1; Lane
  C gemma validation C1→C4 + G2 → full Q4 + G3; Lane D docs + G4; Lane E agentic design.
- **Wk2 (Jun30-Jul7):** Lane F stratified freeze + G5; GPU queue = Qwen anchor(new scorecard) →
  gemma Q4(stratified) → gemma Q6(if relevant) → 1 new family Q4 → Q6; site v1.1 polish; AppWorld-lite scaffold.
