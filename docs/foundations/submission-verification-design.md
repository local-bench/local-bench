# Community submission + verification — design (oracle-red-teamed)

Date: 2026-06-23. Source: GPT-5.5 Pro (oracle) red-team `community-submission-verification-design`,
weighed against our locked methodology + /trust page. This is the **v2** spec (v1 ships
read-only, curated, no submissions). Final call: **GO, but only with conservative trust
labels + a private sentinel for top entries.**

## Two non-negotiable changes vs the naive design
1. **Conservative trust LABELS** — never a broad "verified". A few deterministic spot checks
   verify a *sampled reproduction event*, not the universe of fraud.
2. **Private SENTINEL challenge** for top/new-record entries — without it, public-suite
   memorization is the largest unaddressed hole.

## Cross-cutting correction (affects ALL runs, not just submissions)

**VERIFIED 2026-06-23:** `suite/v1/suite.json` sets every bench's `decoding` to
`{"max_tokens": ..., "temperature": 0}` — `temperature: 0` ONLY, no `top_k` (8 benches);
the harness forwards it verbatim (confirmed in the baked run manifests: top_k/top_p/min_p/seed
all null). PLAN: after the current campaign, add `"top_k": 1` to each `decoding` block and
empirically verify it is a **NO-OP** (re-run a sample both ways on an idle single-slot server,
diff transcripts byte-for-byte). No-op ⇒ existing Qwen/gemma numbers stand, spec just made
explicit (clarifying note, not a re-baseline). Divergence ⇒ re-baseline (unlikely; modern
llama.cpp short-circuits temp≤0 to argmax). Do NOT change mid-campaign (breaks comparability).
**Do NOT define the lane as `temperature=0` in llama.cpp.** Current llama.cpp guidance: temp=0
is not guaranteed fully greedy. Pin canonical greedy as **`top_k=1` / single sampler**
(`--sampling-seq k --top-k 1`). ACTION: verify what our harness actually sends; if it's
temp=0-only, re-pin to top_k=1 going forward and note the lane spec evolved (existing runs get
a reproducibility caveat; don't silently mix).

## Trust tier taxonomy (replaces "verified")
| Label | Meaning |
|---|---|
| **Community re-scored** | Submitted transcripts schema-valid + re-scored by the locked scorer. NO model-identity claim. |
| **Spot-reproduced on localbench rig** | localbench re-ran a hidden-after-upload sample on its pinned stack; no score-changing mismatch (or only adjudicated benign divergence). |
| **Project anchor / full rerun** | localbench ran the whole benchmark itself, pinned stack. |
| **Replicated** | Multiple independent, non-Sybil accounts and/or project reruns converge for the same model artifact. |

## Attacks (ranked) + mitigations
1. **Public-suite memorization / benchmark-specific model** (TOP threat — passes re-score AND
   public-item spot re-runs). → private rotating sentinel (trust signal only, not headline score).
2. **Model-identity fraud** (claim "Model X Q4", generate with a stronger model/proxy/adapter).
   → require a resolvable artifact (model URL + GGUF SHA256 + tokenizer/chat-template hash +
   quant metadata) for "spot-reproduced"; else stays "community re-scored".
3. **Surgical transcript tampering** (edit only rank-moving items). → top entries need 64-128
   re-runs + adaptive sampling (5-10 items is theater: 5% tamper + 32 checks = 19% miss).
4. **Determinism-as-deniability** (blame CUDA/batch/version nondeterminism). → pinned verifier
   stack; adjudicate by first-divergent-token + margin.
5. **Transcript replay / attribution theft.** → bundle SHA dedup, per-item hashes, run nonce,
   account-bound signed submission; replays collapse to "already submitted".
6. **Sybil replication.** → diversity signals (GitHub age/rep, IP/ASN, run times, independent
   bundles) + at least one project anchor.
7. **Reviewer-agent compromise (prompt injection in transcripts).** → LOW severity IF the agent
   has no scoring/publish authority (see Agent section).
- Don't matter: simple score lies (killed by server re-score); low-effort fabrication (caught
  by artifact re-run); timing (anomaly signal only, never proof).

## Spot re-run economics
`P(miss) ≈ (1-p)^n`; `n ≥ log(alpha)/log(1-p)`. 5% tamper → 59 items (95%) / 90 (99%);
3% → 99/152; 1% → 299/459. Policy:
| Submission | Public re-run sample | Sentinel |
|---|---|---|
| Low-rank / first-pass | 0-16, anomaly-triggered | none |
| New family / low-rep account | 32 | optional 16-32 |
| Top 25 / near frontier / suspicious | 64 | 32-64 |
| Top 10 / new record / big jump | 96-128 | 64 |
| Project anchor | full run | optional |
Selection **hidden-after-upload** via `sample_seed = HMAC(server_secret, bundle_sha256 || submission_id)`.
Three buckets: stratified (axis/bench/difficulty/length) + score-impact (rank-affecting items) +
suspicion (anomalies). SPRT as scheduler; **any score-changing mismatch on a top entry → repeat
re-run + human review**, never auto-accept.

## Public vs private
- **Public frozen suite = official score** (stays fully reproducible — do NOT make the headline
  depend on a private holdout).
- **Private rotating sentinel = trust signal ONLY** (pass / soft-warn / fail + sample size; never
  per-item transcripts, never the official number). Generated/parameterized canaries
  (math/symbolic/IF exact-answer) > static MCQ (which leak). Bank: 500-1000 static or 128-256
  generated, ≥10× per-submission challenge size, rotate before exposure burns it. Minimal: 64
  challenge items for top entries (24 math + 24 IF/format + 16 paraphrase/canary).

## Determinism: two modes
Greedy reproducibility needs same: model bytes, GGUF metadata, tokenizer, chat template, prompt
serialization, scorecard ID, llama.cpp commit, build flags, backend, GPU/driver/CUDA/cuBLAS,
batch size, slot count, prompt cache, flash-attn, KV precision, context/RoPE, sampler sequence,
threading. Plus top_k=1 (not temp=0).
- **Strict mode** (same pinned verifier stack): only mode eligible for "spot-reproduced";
  token-for-token match expected; any mismatch adjudicated. (one slot, continuous batching off,
  prompt cache off, batch/FA/KV pinned, model SHA verified.)
- **Compatibility mode** (community stack differs): "community re-scored" only. Classify
  divergence: exact match=pass; different prose+same parsed answer/late divergence=benign;
  low-margin first divergence=benign+note; high-margin answer change=suspicious; verifier
  disagrees across many items=likely fake; divergences only on rank-improving items=tampering.
  **localbench's re-run is authoritative for the trust decision; the transcript is evidence, not truth.**

## Identity / anti-spam
GitHub OAuth default; email magic-link fallback (+ Turnstile + stricter quota); anonymous =
private/unlisted only. Quotas scale with account age/reputation. CLI signs the manifest (Ed25519
key linked to account); no hardware attestation for v2.
**Cloudflare specifics:** do NOT proxy full transcript bundles through a Worker (body limit
100 MB Free/Pro → 413s). Worker authenticates + issues a short-lived **R2 presigned PUT URL**;
client uploads the bundle directly to R2. Turnstile only at ticket issuance, not in the CLI loop.
Replay fields: submission_id, server nonce, account_id, suite_hash, scorecard_id, manifest_sha256,
bundle_sha256, created_at, CLI version, signature.

## Agent reviewer (never authoritative)
- **Automated (deterministic):** schema/suite-hash/scorecard/manifest validation, model-SHA
  format, bundle hashes, server re-score, lane conformance, token-cap, duplicate detection,
  timing plausibility, queue prioritization, spot-rerun + sentinel job creation.
- **Human-gated:** top-25 acceptance, new record, new family, high-ranking first submission, any
  score-changing mismatch, any sentinel warn/fail, appeals, fraud labels.
- **Agent allowed:** summarize deterministic evidence, cluster anomalies, draft notes, suggest
  next items, render diffs. **Forbidden:** approve labels, delete, publish, change scores/tiers,
  run shell from transcript content, fetch URLs, read secrets, write to prod except review-notes.
- **Hardening:** transcripts are DATA never instructions (typed JSON fields, not pasted into the
  prompt); deterministic checks before any LLM reasoning; escape/delimit/truncate; no secrets in
  context; tool allowlist; output is a note not an action; separate read-only identities + a
  deterministic publisher.

## Minimal trustworthy v2
- **P0 (must):** conservative labels; full transcript bundle + manifest; server re-score
  authoritative; strict schema/scorecard validation; pinned top_k=1 verifier stack; spot-rerun
  for leaderboard-impacting entries (32 / 64-128); human gate for "spot-reproduced"; R2 presigned
  upload; GitHub OAuth + email + quotas; duplicate/replay detection; no LLM reviewer authority.
- **P0.5 (strongly recommended):** private sentinel for top/new-record (32-64 fresh exact items).
- **P1 (defer):** full SPRT automation, reputation scoring, replication badge, large holdout bank,
  logit-divergence UI, artifact mirroring, hardware attestation, anomaly ML, public fraud reports.
- **P2 (avoid):** LLM judge in scoring; private holdout as headline; auto-verified by agent;
  claims that transcripts prove model identity or that public score proves uncontaminated quality.

## Build order (for the Codex v2 plan)
1. Fix lane spec (top_k=1, pinned one-slot/no-cache verifier mode).
2. Rename tiers ("community re-scored" / "spot-reproduced", not "verified") before shipping.
3. Ingest: GitHub/email auth, upload ticket, R2 presigned PUT, bundle limits, SHA, D1 status row.
4. Deterministic validation + server re-score.
5. Spot-rerun sampler (HMAC hidden selection; stratified + suspicion + high-impact).
6. Top-entry policy (64-128 + human approval).
7. Private sentinel (32-64 fresh canaries; show pass/warn/fail only).
8. Constrain the agent (deterministic-first, advisory-only, no write authority).
9. Update /trust page (submissions aren't proof of identity; define each tier honestly).
10. Launch with a narrow promise: "re-scored community results with sampled reproduction for
    high-impact entries," not "fraud-proof leaderboard."

Full oracle transcript: oracle session `community-submission-verification-design` (2026-06-23).
