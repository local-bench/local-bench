# local-bench v2 — execution plan (community submissions)

Date: 2026-06-23. Status: **DEFERRED until v1 is live.** This consolidates the existing
(oracle-reviewed) design into a sequenced, execution-ready roadmap. It is a PLAN, not a build:
nothing here is implemented yet.

Primary sources (build on these, do not contradict):
- `docs/foundations/submission-verification-design.md` — the verification design (oracle red-team
  `community-submission-verification-design`, 2026-06-23). The trust-tier taxonomy, attack ranking,
  spot-re-run economics, and Cloudflare/R2 specifics below are lifted from it.
- `docs/superpowers/specs/2026-06-23-benchmark-onramp-design.md` — the "Benchmark a model" on-ramp
  (the v2 front-of-house that ships in v1 with an honest ending: run it, save `my-run.json`, no
  Submit button yet).
- `docs/foundations/v1-launch-checklist.md` — the "Defer (NOT v1)" scope + anonymity vectors.
- `docs/foundations/board-v1-build-spec.md` — the immutable `board_v1.json` + `board_v1.manifest.json`
  artifact that v1 introduces and **v2 must extend, not bypass**.

Verified against code (read-only) on 2026-06-23:
- Run JSON top-level (`cli/runs/ladder-qwen36-27b-Q4_K_M.json`): `schema: "localbench-run-v0"`,
  `manifest`, `benches`, `composite`, `conformance`, `items[]` (per-item `response_text`,
  `extracted`, `correct`, `finish_reason`, `usage`, timing), `totals`, `output_path`.
- `cli/src/localbench/manifest.py` — for a plain local OpenAI-compatible run,
  `integrity.canonical = false`, `model.file_sha256 = "UNHASHED"`, tokenizer/chat-template digests
  `"unknown"`/`"endpoint-applied-unknown"`, runtime name/version/KV/ctx all null.
- `cli/src/localbench/lane_conformance.py` — conformance gates (leaked-reasoning ≥2% nonconformant /
  ≥25% diagnostic; truncation ≥10%; no-final-answer ≥10%/≥25%), run = WORST bench status.
- `cli/src/localbench/scoring/scorecard.py` — `scorecard_id` = hash(scorecard_version +
  registry_digest + reasoning_registry_digest + scorer_versions + ci_method); current
  `scorecard-v1.3`. `cli/src/localbench/scoring/axes.py` — the single weights registry.
- CLI commands today: `run`, `compare`, `kld`, `code`. No `submit`, no `verify`, no `board` yet
  (`board` is specced in board-v1-build-spec.md, to be built in v1). No R2/Ed25519/trust-tier code
  exists anywhere — v2 is entirely design-stage. [VERIFIED]

---

## 1. Scope + goal

**Goal:** let a stranger run our suite locally and have their result verified and merged into the
public leaderboard — turning a curated read-only board into a participation funnel — **without
exposing the owner's identity** and **without trusting the submitter**.

**The honest promise (the launch framing, from the verification design):**
> "Re-scored community results, with sampled reproduction for high-impact entries." NOT a
> "fraud-proof leaderboard," and NOT "verified" as a blanket claim.

### In v2 (the minimal trustworthy slice — P0/P0.5 from the verification design)
- An **upload path** for a self-produced run bundle (transcripts + manifest), anonymity-preserving
  for the owner (see §2).
- **Server-side re-score** of submitted transcripts with the locked scorer; the server's number is
  authoritative, the transcript is evidence.
- **Conformance + integrity gates** on intake (leaked-reasoning / truncation / no-answer; suite-hash;
  scorecard-id; decode-params; bundle/per-item hashes; duplicate/replay).
- **Conservative trust tiers** ("community re-scored" / "spot-reproduced on localbench rig" / "project
  anchor" / "replicated") — never a blanket "verified".
- **Spot-re-run sampler** for leaderboard-impacting entries (hidden-after-upload selection; 32 for new
  family / low-rep, 64–128 for top/near-frontier), human-gated to grant "spot-reproduced".
- **Private rotating sentinel** for top / new-record entries (pass / warn / fail signal only).
- **Identity / anti-spam:** GitHub OAuth default, email magic-link fallback (+ Turnstile + stricter
  quota), per-account quotas, Ed25519-signed manifest.
- **A `/trust` page** that defines each tier honestly.
- **A submitted row visually distinguished** from maintainer-run rows on the board.
- The on-ramp's final step **wired to the upload** (its v1 "no Submit button" ending is removed).

### Deferred AGAIN to v3 (P1 in the verification design — do not build in v2)
Full SPRT automation; reputation scoring; the "replicated" badge as an automated multi-account
converger; large holdout/sentinel banks; logit-divergence UI; artifact mirroring; hardware
attestation; anomaly-ML; public fraud reports. **Avoid entirely (P2):** any LLM judge in scoring;
a private holdout as the headline number; auto-verification by an agent; any claim that a transcript
proves model identity or that a public score proves uncontaminated quality.

**Non-goal restated:** v2 does not make the headline depend on anything private. The public frozen
suite stays the official, fully-reproducible score; the sentinel is a trust signal beside it.

---

## 2. Intake design (owner anonymity + untrusted submitters)

**The ruled-out option, and why.** The obvious intake — a public GitHub repo taking submissions as
PRs / issues — is **OUT for v1's lifetime and v2**. v1 ships from a PRIVATE repo via Cloudflare Pages
Direct Upload precisely to keep the owner anonymous (v1 checklist task #20). A public submissions repo
re-introduces every identity vector the launch closed: the maintainer's review comments, merge commits,
co-author lines, issue-template metadata, and CI identity all become public and all point at the owner.
Anonymity is a hard constraint, so PR/issue intake is rejected regardless of how convenient it is.

Three concrete options:

### Option A — Signed run-artifact upload to a serverless endpoint behind Cloudflare (RECOMMENDED)
The submitter runs `localbench submit` (new CLI verb); it authenticates, gets a short-lived **R2
presigned PUT URL** from a Worker, and the client uploads the bundle **directly to R2** (NOT through
the Worker — the verification design is explicit: Worker body limit is 100 MB on Free/Pro, full
transcript bundles 413 there). The Worker only authenticates, issues the ticket, and writes a status
row to **D1**. A separate re-score pipeline (§4) picks the bundle up.

- **Anonymity (owner):** strongest. No public repo, no human-readable maintainer surface. The owner
  is anonymous to the public and casual OSINT (not to Cloudflare/registrar/payment/legal — the same
  boundary v1 already accepts). The maintainer interacts only with a private dashboard + D1.
- **Anti-gaming:** strongest. The artifact is signed (Ed25519 key bound to the account), carries the
  replay fields (submission_id, server nonce, account_id, suite_hash, scorecard_id, manifest_sha256,
  bundle_sha256, created_at, CLI version, signature), and the server re-scores from the transcript —
  client-side score lies die on re-score. Auth (GitHub OAuth / email magic-link) + Turnstile at ticket
  issuance + quotas give Sybil/spam resistance.
- **Maintainer effort:** highest upfront (Worker + R2 + D1 + auth + the re-score pipeline), but it is
  the only option that scales past a handful of submissions and the only one the existing design
  already fully specifies. It is also the path the on-ramp already assumes.

### Option B — Moderated form/email intake (pseudonymous mailbox)
A static form (or the pseudonymous domain mailbox) takes a link to a submitter-hosted bundle (their
own HF repo / gist / R2). Maintainer downloads, runs an offline `localbench verify`, and regenerates
the board locally.

- **Anonymity (owner):** strong (pseudonymous mailbox already planned for contact). No public review
  surface.
- **Anti-gaming:** same *technical* core (offline re-score + conformance + spot-re-run all still run),
  but weaker operationally — no enforced signing/replay binding, no Turnstile/quota, submitter-hosted
  bundles can vanish or mutate, and there's no automatic duplicate/replay ledger.
- **Maintainer effort:** low to build, **high per-submission** (every submission is manual). Becomes
  "debug my LLM setup" the moment volume rises (the on-ramp doc flags exactly this support debt).
- **Good as:** a v2-phase-0 fallback / pilot to validate the re-score pipeline against real outside
  bundles before the upload plumbing exists. Not the destination.

### Option C — Pseudonymous-repo intake (fresh throwaway org)
A SEPARATE pseudonymous GitHub org (fresh, clean, no link to the owner) hosts a submissions repo;
contributors PR their bundle; a pseudonymous bot re-scores in CI.

- **Anonymity (owner):** conditional and **fragile**. Safe ONLY if the org is created from a clean
  identity with zero linkage (separate email, no reused SSH keys, no personal CI, no package account) —
  exactly the trap the v1 checklist warns about (PyPI Trusted Publishing / provenance / co-author lines
  re-leak identity). One careless commit or a CI provenance artifact deanonymizes the owner. High
  standing risk for low benefit.
- **Anti-gaming:** PRs give nice public diffs, but public submissions + public CI logs are themselves
  an attack surface (they teach gamers exactly which items the spot-re-run sampled — leaking the
  hidden-selection advantage) and invite prompt-injection via PR content.
- **Maintainer effort:** medium, but the anonymity-maintenance burden is permanent and unforgiving.

### Recommendation
**Option A (signed artifact upload to a Cloudflare-fronted serverless endpoint).** It is the only
option that simultaneously (a) holds the owner's anonymity by construction, (b) carries the full
anti-gaming machinery the verification design already specifies, and (c) is what the on-ramp's final
step is already written to plug into. **Use Option B (moderated mailbox) as the phase-0 pilot** to
exercise the re-score pipeline against a few real external bundles before the upload plumbing is built
— it de-risks §4 cheaply. **Reject Option C** — the anonymity maintenance cost is open-ended and a
single slip is unrecoverable.

---

## 3. Verification + anti-gaming

All of this is from `submission-verification-design.md`; reproduced here as the executable contract.

### 3.1 Re-score from submitted transcripts (authoritative)
The submitted run bundle's `items[]` ARE the transcripts. The server re-runs the **locked scorer**
(the same `cli/src/localbench/scorers/*` + `scoring/axes.py` registry that produced the board) over
the submitted per-item `response_text` and recomputes `extracted`/`correct`/composite. **The server's
recomputed number is the score; the submitter's `composite`/`benches` fields are ignored.** This kills
simple score lies and most low-effort fabrication outright.

### 3.2 Conformance gates on intake (reuse `lane_conformance.py` verbatim)
Run `assess_run_conformance` on the submitted items. A bundle whose worst bench is `nonconformant` or
`diagnostic-only` is **not** eligible for the ranked headline (it may be stored/shown as diagnostic):
- **Leaked reasoning** into scored content ≥2% → nonconformant, ≥25% → diagnostic-only (the most
  corrupting; it changes WHAT is scored).
- **Truncation** (`finish_reason == "length"`) ≥10% → nonconformant.
- **No final answer** ≥10% → nonconformant, ≥25% → diagnostic-only.
These are the SAME gates maintainer runs pass; submissions get no special leniency.

### 3.3 Suite-hash + scorecard + decode-param checks
- **Suite identity:** the bundle's `manifest.suite.item_set_hashes` must match the current
  `suite/v1/suite.json` per-bench hashes. A mismatch = a different/edited item set → reject (not the
  official suite).
- **Scorecard identity:** `manifest.scorecard.scorecard_id` must match the live scorecard
  (`scorecard-v1.3` today). A mismatch means the bundle was scored under a different registry/scorer —
  re-score under ours and label by the current scorecard; never trust the submitter's identity claim.
- **Decode params:** the lane is canonical greedy. **Per the verification design's cross-cutting
  correction, the lane must be pinned as `top_k=1` (single sampler), NOT defined as `temperature=0`**
  (llama.cpp does not guarantee temp=0 is fully greedy). Intake must check the bundle's sampling block
  against the pinned lane and flag divergence. (See §6 — this top_k=1 pin is a v1 action that affects
  ALL runs, not just submissions.)

### 3.4 Conformance/transcript-tampering defense (spot re-run)
Re-scoring catches lies about the SCORE but not a surgically edited transcript (flip only the
rank-moving items). Defense = **localbench re-runs a hidden-after-upload sample on its own pinned rig**
and compares. Sample sizes follow `P(miss) ≈ (1-p)^n` (5% tamper → 59 items for 95% / 90 for 99%):

| Submission class | Public re-run sample | Sentinel |
|---|---|---|
| Low-rank / first-pass | 0–16, anomaly-triggered | none |
| New family / low-rep account | 32 | optional 16–32 |
| Top 25 / near frontier / suspicious | 64 | 32–64 |
| Top 10 / new record / big jump | 96–128 | 64 |
| Project anchor | full run | optional |

Selection is **hidden-after-upload** via `sample_seed = HMAC(server_secret, bundle_sha256 ||
submission_id)` so a submitter can't pre-compute which items will be checked. Three buckets:
stratified (axis/bench/difficulty/length) + score-impact (rank-affecting items) + suspicion
(anomalies). **Any score-changing mismatch on a top entry → repeat re-run + human review; never
auto-accept.** localbench's re-run is authoritative for the trust decision.

### 3.5 Public-suite memorization (the TOP threat) → private sentinel
A model trained on / built for the public suite passes BOTH re-score AND public-item spot re-runs.
The only defense is a **private rotating sentinel**: generated/parameterized canaries (math/symbolic/
IF exact-answer beat static MCQ, which leaks). Bank ≥10× the per-submission challenge size; rotate
before exposure burns it; minimal top-entry challenge = 64 items (24 math + 24 IF/format + 16
paraphrase/canary). **The sentinel is a TRUST SIGNAL ONLY — pass / soft-warn / fail + sample size,
never per-item transcripts, never the official number.**

### 3.6 Model-identity fraud (claim "Model X Q4", generate with something stronger)
Re-score cannot prove identity. To earn "spot-reproduced", the submission must carry a **resolvable
artifact**: model URL + GGUF SHA256 + tokenizer/chat-template hash + quant metadata, so localbench can
fetch the same bytes and reproduce. **Without a resolvable artifact the entry can only ever be
"community re-scored"** — no identity claim. (This is exactly the gap in today's manifest: a plain
local run has `file_sha256 = "UNHASHED"` and `integrity.canonical = false`. v2 needs the CLI to
populate these for "spot-reproduced" eligibility — see §6.)

### 3.7 Duplicate / Sybil / replay resistance
- **Replay / attribution theft:** bundle-SHA dedup + per-item hashes + run nonce + account-bound signed
  submission; a replay collapses to "already submitted".
- **Sybil replication:** diversity signals (account age/reputation, IP/ASN, run times, independent
  bundles) + require at least one project anchor before "replicated". Quotas scale with account
  age/reputation; anonymous = private/unlisted only.

### 3.8 Trust tiers (replace "verified" — NEVER a blanket "verified")
| Tier | Meaning |
|---|---|
| **Community re-scored** | Schema-valid + re-scored by the locked scorer. **No model-identity claim.** |
| **Spot-reproduced on localbench rig** | localbench re-ran a hidden sample on its pinned stack; no score-changing mismatch (or only adjudicated-benign divergence). |
| **Project anchor / full rerun** | localbench ran the whole benchmark itself, pinned stack. |
| **Replicated** | Multiple independent non-Sybil accounts and/or project reruns converge for the same artifact. |

Determinism has **two modes**: *strict* (same pinned verifier stack — token-for-token match expected;
only mode eligible for "spot-reproduced") and *compatibility* (community stack differs — "community
re-scored" only; classify divergence: exact=pass, different-prose-same-answer/late-divergence=benign,
low-margin=benign+note, high-margin answer change=suspicious, rank-only divergences=tampering).

### 3.9 Visual distinction on the board (submitted vs maintainer-run)
Every row carries its tier as a first-class, visible field (already anticipated by the on-ramp's row
design: `tier: project anchor / community re-scored / spot-reproduced`). Concretely:
- A **tier badge column** on the board (e.g. a filled marker for "project anchor", an outline marker +
  account-handle for "community re-scored", a distinct marker for "spot-reproduced").
- **Default board view = maintainer-run ("project anchor") + "spot-reproduced" + "replicated"**; plain
  "community re-scored" rows are visible but visually subordinate (lighter, grouped, or behind a
  "show community-submitted" toggle) so an un-reproduced self-report can never be mistaken for a
  localbench-verified number.
- The `/trust` page explains each badge honestly (a submission is NOT proof of model identity; a public
  score is NOT proof of uncontaminated quality).

### 3.10 Reviewer agent — never authoritative
If an LLM agent helps triage: deterministic checks run FIRST; transcripts are typed DATA never pasted
as instructions; the agent may summarize/cluster/draft notes/render diffs but is **forbidden** from
approving labels, deleting, publishing, changing scores/tiers, running shell from transcript content,
fetching URLs, or reading secrets. Separate read-only identities + a deterministic publisher. Human
gate for: top-25 acceptance, new record, new family, high-ranking first submission, any score-changing
mismatch, any sentinel warn/fail, appeals, fraud labels.

---

## 4. Backend (the maintainer's co-deliverable)

The on-ramp (front-of-house) and this backend are a **single coupled deliverable** — sequence them
together (the on-ramp doc flags this explicitly).

### 4.1 Upload endpoint (Cloudflare)
- **Worker:** authenticate (GitHub OAuth / email magic-link), Turnstile at ticket issuance only (NOT in
  the CLI loop), enforce quota, issue a short-lived **R2 presigned PUT URL**, write a **D1** status row
  (submission_id, account_id, suite_hash, scorecard_id, bundle_sha256, created_at, state). Do **NOT**
  proxy the bundle through the Worker (100 MB body limit → 413).
- **R2:** receives the bundle directly from the client.
- **CLI:** new `localbench submit` verb signs the manifest (Ed25519 key bound to the account) and does
  the presigned PUT. (No hardware attestation in v2.)

### 4.2 Re-score pipeline
A worker/job that, on a new R2 bundle: validates schema + `schema_version`; checks suite-hash +
scorecard-id + decode-params; runs `assess_run_conformance`; **re-scores with the locked CLI scorer**;
dedups by bundle-SHA + per-item hashes; computes the HMAC spot-re-run selection; creates spot-re-run
and sentinel JOBS for leaderboard-impacting entries; writes a candidate row + status to D1. This is
**`localbench verify`** (a new CLI/library entrypoint reusing `scoring.axes`, the scorers,
`lane_conformance`, and `signed_score` — the SAME canonical scoring the board uses; do NOT fork a
second scorer).

### 4.3 Board-merge into the immutable artifact (extend `board_v1.json`, do NOT bypass it)
v1 introduces a scorer-generated immutable `board_v1.json` + `board_v1.manifest.json` (with
`board_sha256`), produced by `localbench board`; the site is a PURE renderer. **v2 must EXTEND this,
not write rows around it.** Concretely:
- The merge step takes accepted community rows and **regenerates the board through `localbench board`**
  (a new `--submissions <dir|D1-export>` input feeding the SAME generator), producing
  `board_v2.json` + `board_v2.manifest.json` with a fresh `board_sha256` and a bumped `index_version`.
  Community rows go through identical composite/CI/`signed_score`/conformance computation as maintainer
  rows — the registry stays the single source of truth.
- The generator's existing invariants carry over: only headline-lane + conformance-pass + measured rows
  are `ranked=true`; the **anonymity grep test** in board-v1 (no `C:\Users\`, `/home/`, `/Users/`,
  username, hostname, `github.com`/`gitlab.com`) must be **extended to scrub submitter-supplied fields**
  (a submitter's `output_path` also leaks `C:\Users\<them>\...`; their account handle is shown by
  design, but their local paths/hostnames must be stripped). [VERIFIED: a real run JSON's `output_path`
  is a full Windows user path.]
- Publishing the regenerated board is a **deterministic publish** (Direct Upload / Pages), gated by the
  human approvals in §3.10 — the agent never publishes.

### 4.4 Where re-scoring compute comes from (the single-GPU bottleneck — addressed)
The whole project runs on ONE RTX 5090 (32 GB), and **Michael gates all GPU use** (standing rule:
never launch GPU work without explicit go-ahead). So:
- **Re-SCORING is CPU-only** (it replays transcripts through the scorer — no model inference). This
  scales fine on the Worker/D1 side and needs no GPU. Most submissions never touch the GPU. This is the
  key unlock: the common path is GPU-free.
- **SPOT RE-RUNS and the SENTINEL DO need the GPU** (they generate fresh completions on the pinned rig).
  This is the real bottleneck and must be **batched, queued, and rate-limited**, not on-demand:
  - Only leaderboard-impacting entries trigger a re-run at all (§3.4); low-rank submissions get 0–16
    anomaly-triggered items, often none.
  - Re-runs are **queued for a human-scheduled GPU window** (consistent with the GPU-ask-first rule and
    the box's other duties), not fired automatically on upload. A submission can sit in
    "community re-scored, reproduction pending" indefinitely without blocking the board.
  - The pinned strict-mode verifier (one slot, continuous batching off, prompt cache off, batch/FA/KV
    pinned, model SHA verified) is the ONLY config eligible to grant "spot-reproduced".
  - **Decision needed (§7):** whether the spot-re-run GPU is the local 5090 in scheduled windows
    (cheapest, but contends with everything else and is gated) or a rented box (e.g. Michael's own vast
    host) spun up per verification batch. The design assumes the local rig; renting is an option to
    relieve contention if submission volume ever justifies it.

---

## 5. Sequencing (starts AFTER v1 is live)

Effort sizing is rough and relative (S ≈ a day or two, M ≈ a few days, L ≈ a week+), Claude/Codex
implementer + Michael review. **Phase 0 is the only thing that can overlap v1; everything else is
strictly post-launch.** Each phase maps to the verification design's build order.

| Phase | What | Build-order refs | Effort |
|---|---|---|---|
| **0. Pre-reqs (can overlap v1 tail)** | Pin the lane as `top_k=1` + verify it's a NO-OP vs current temp=0 runs (see §6); rename tiers to the conservative taxonomy in code/UI BEFORE any submission ships; lock the run `schema_version` for submission (§6). | design steps 1–2 | S–M |
| **1. Offline verify + pilot (Option B)** | Build `localbench verify` (re-score + conformance + suite/scorecard/decode checks + dedup) as a pure-CPU library/CLI reusing the canonical scorer. Pilot it on a few real external bundles via the moderated-mailbox intake. No cloud plumbing yet. | design step 4 | M |
| **2. Ingest plumbing (Option A)** | Worker auth (GitHub OAuth + email magic-link + Turnstile + quota), R2 presigned PUT, D1 status rows, `localbench submit` (Ed25519-signed manifest + presigned upload), replay/duplicate ledger. | design step 3 | L |
| **3. Board-merge** | Extend `localbench board` with a submissions input → `board_v2.json` + manifest + bumped `index_version`; extend the anonymity scrub to submitter fields; wire the deterministic publish + the human approval gate; ship the tier-badge board UI + `/trust` rewrite; wire the on-ramp's final step to `submit`. | design steps 2, 9 | M–L |
| **4. Spot-re-run sampler** | HMAC hidden selection; stratified + score-impact + suspicion buckets; SPRT-as-scheduler (manual SPRT ok to start); GPU-window queue (§4.4); strict-mode pinned verifier; adjudication-by-first-divergent-token. | design steps 5–6 | L |
| **5. Private sentinel** | 32–64 fresh generated canaries (math/IF/paraphrase); rotation discipline; pass/warn/fail signal only (never per-item, never headline). | design step 7 | M |
| **6. Agent hardening (only if an agent is used)** | Deterministic-first, advisory-only, no write authority, transcripts-as-data; separate read-only identities + deterministic publisher. | design step 8 | S–M |
| **7. Launch v2** | Narrow public promise ("re-scored community results with sampled reproduction for high-impact entries"); `/trust` final; changelog entry; quota/abuse monitoring. | design step 10 | S |

**Defer to v3 (do NOT schedule in v2):** full SPRT automation, reputation scoring, automated
"replicated" convergence, large holdout banks, logit-divergence UI, artifact mirroring, hardware
attestation, anomaly-ML, public fraud reports.

---

## 6. What v1 MUST NOT foreclose (most valuable section — be specific)

These are concrete things to get right **in the v1 build now**, so v2 doesn't need a painful retrofit.
Ordered by how expensive the retrofit would be.

1. **Version the run-JSON / bundle schema explicitly — and treat the run JSON as the future submission
   bundle.** Today the run top-level is `schema: "localbench-run-v0"` and the manifest is
   `schema_version: "0.1"`. v2 ingest will validate exactly these. **Action in v1:** confirm the run
   record carries an explicit, checked `schema_version` (not just a v0 string), and that the per-item
   shape (`id`, `bench`, `response_text`, `reasoning_text` channel, `extracted`, `correct`,
   `finish_reason`, `usage`) is FROZEN and documented as the re-score input. If v1 ships transcripts the
   server can't re-score deterministically (e.g. drops `reasoning_text` separation, or doesn't record
   `finish_reason`), v2 re-score and the conformance gates break. The separated reasoning channel
   matters: `lane_conformance` distinguishes leaked-into-`response_text` from a clean `reasoning_text` —
   that separation must be preserved in the artifact a submitter uploads.

2. **Keep `board_v1.json` the SINGLE scoring spine, generated only by `localbench board`, and design
   `index_version` to be bumpable for a growing/merged board.** v2 regenerates the board WITH community
   rows through the same generator. **Actions in v1:** (a) ensure the site is a pure renderer with ZERO
   score computation (the board-v1 spec already mandates this — hold the line; any score math that
   sneaks into `web/` becomes a second scorer v2 must reconcile); (b) make `index_version` a real,
   documented, monotonic field with a stated bump rule, not a constant, so adding submitted rows is a
   version bump not a schema change; (c) keep the `models[]` row schema (`IndexModelSchema`) able to
   carry a per-row **`tier`/`source`/`account` field even in v1** (it can be constant "project anchor"
   for every v1 row) so v2 adds rows of the same shape rather than migrating the schema. The on-ramp
   doc already says "design the row NOW" with display-name vs artifact-identity vs tier separated — do
   that in the v1 row schema.

3. **Pin the lane as `top_k=1` (canonical greedy), not `temperature=0`, and capture decode params +
   model artifact identity in the manifest now.** The verification design's cross-cutting correction
   says the lane MUST be `top_k=1` single-sampler (llama.cpp doesn't guarantee temp=0 is greedy), and
   that today the suite pins `temperature:0` only (top_k/top_p/min_p/seed all null — [VERIFIED in
   manifest.py + the run JSON sampling block]). **Actions in v1:** (a) after the current campaign, add
   `top_k=1` to each bench's decoding and empirically verify it's a NO-OP vs the existing numbers (re-run
   a sample both ways, diff byte-for-byte) — do this BEFORE v2 so the submission lane spec is stable and
   existing Qwen/gemma numbers don't get a reproducibility caveat mid-stream; (b) ensure the manifest
   records the decode params the intake will check; (c) give the CLI a path to populate
   `model.file_sha256` / tokenizer / chat-template digests (today `"UNHASHED"` / `"unknown"` with
   `integrity.canonical=false`) — **without a resolvable artifact hash, NO submission can ever reach
   "spot-reproduced"** (§3.6), so the field must exist and be populatable, even if v1 maintainer runs
   leave it null. This is the difference between v2 being able to offer the top trust tier and not.

4. **Make the v1 artifact bytes deterministic and anonymity-clean — and make the scrub reusable.** The
   board-v1 spec already requires `--frozen-timestamp` for a reproducible `board_sha256` and an
   anonymity grep test (no `C:\Users\`, hostname, username, git remotes). **Action in v1:** factor the
   anonymity scrub as a reusable function (not a one-off test), because v2 must run the SAME scrub over
   submitter-supplied metadata (a submitter's run JSON also carries a full `C:\Users\<them>\...`
   `output_path` — [VERIFIED]). If the scrub is welded into the board generator only, v2 re-implements it.

5. **Reserve the scorecard / suite-hash identity as the submission-acceptance key.** v2 intake accepts a
   bundle only if its `suite.item_set_hashes` and `scorecard.scorecard_id` match the live board's.
   **Action in v1:** ensure `board_v1.manifest.json` records the exact `item_set_hashes`,
   `scorecard_id`, `registry_digest`, and `reasoning_registry_hash` it was built under (the spec already
   asks for these — confirm they're the REAL values read from the scorer, not placeholders), so v2 has
   an authoritative "what counts as the same suite/scorecard" reference to match submissions against.

6. **Don't ship a public on-ramp ending that implies instant publish, and don't bind the CLI's
   `submit`-shaped surface to anything yet.** The on-ramp ships in v1 with the honest "save
   `my-run.json`; upload + server re-score land in v2" ending — keep it (no fake Submit button). **Minor
   action:** keep the `localbench run` output filename/flags stable (the on-ramp copy hard-codes
   `--out my-run.json` and the served-model-name conventions); a churn there silently breaks the v1 copy
   and the future `submit` UX.

7. **Keep the trust vocabulary honest from day one.** v1's board rows are all maintainer-run; label them
   the eventual tier name ("project anchor"), NOT "verified". **Action in v1:** if any v1 UI/string says
   "verified", change it now — renaming a public trust label after launch is a credibility cost, and the
   verification design's #2 non-negotiable is "never a blanket verified".

---

## 7. Open decisions for Michael + open questions for a future oracle consult

### Decisions for Michael
1. **Intake choice:** confirm Option A (signed upload behind Cloudflare) as the v2 destination, with
   Option B (moderated mailbox) as the phase-0 pilot. (Plan's recommendation.)
2. **Spot-re-run compute:** local 5090 in scheduled GPU windows (default; contends + gated) vs a rented
   box (e.g. the vast host) per verification batch. Affects §4.4 and how fast reproductions clear.
3. **Auth surface:** GitHub OAuth as default identity is in the design — confirm it's acceptable given
   anonymity is about the OWNER, not submitters (submitters authenticating via GitHub doesn't expose
   Michael, but confirm the OAuth app itself is registered under a pseudonymous account, not a personal
   one). Email magic-link is the anonymous-friendly fallback.
4. **How prominent are un-reproduced community rows?** Default-visible-but-subordinate vs behind-a-toggle
   vs private-until-spot-reproduced. Sets the bar for what the public sees as "on the leaderboard".
5. **Quota / cost posture:** R2 + D1 + Workers + Turnstile usage and abuse ceilings on the anonymous
   Cloudflare account; what submission volume is even desired (a niche board may never need Option A's
   scale).
6. **v2 timing:** explicitly gated on v1 being live AND stable; no v2 work except Phase 0 starts before
   then.

### Questions worth a future oracle consult (when v2 is scheduled)
1. **Sentinel bank design + rotation economics** at realistic submission volume: generated-canary
   families that resist memorization, how fast exposure burns a bank, and the minimum viable bank size
   for a low-traffic board (the design gives 128–256 generated / 500–1000 static as a starting point —
   validate against expected throughput).
2. **Strict-mode determinism reality on the 5090 specifically:** is token-for-token reproduction
   actually achievable across our own re-runs (CUDA/cuBLAS/batch/version nondeterminism), or does even
   "strict" need a first-divergent-token + margin adjudication as the normal case? This decides whether
   "spot-reproduced" is a clean match or an always-adjudicated tier.
3. **The `top_k=1` no-op verification result** (the §6.3 / design cross-cutting experiment): if it
   DIVERGES from the existing temp=0 numbers, that's a re-baseline question (which historical runs get a
   reproducibility caveat, and whether v1 ships before or after the re-pin) worth an explicit review.
4. **Minimal Sybil/replication policy** that's credible without heavy reputation machinery (deferred to
   v3): what's the smallest "replicated" definition that isn't trivially gamed by one motivated actor
   with two accounts.
5. **Whether an LLM reviewer agent is worth introducing at all in v2** vs pure-deterministic triage +
   human gates — the agent adds a prompt-injection surface for marginal triage benefit; the design
   already constrains it to advisory-only, but skipping it entirely in v2 may be cleaner.
