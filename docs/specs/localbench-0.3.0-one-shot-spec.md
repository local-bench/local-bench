# localbench 0.3.0 — one-shot bench (`localbench bench <model>`)

**Status:** v2 AMENDED after GPT-5.5 xhigh red-team, 2026-07-08 (verdict: BUILD WITH AMENDMENTS — all 11 findings folded in below).
**Owner decision (Michael, 2026-07-08):** Full one-shot v1. Ship 0.2.5 first; 0.3.0 build starts immediately after.

## 1. Problem

The current publishable flow is four command blocks (setup, model download + `llama-server` launch, a ~20-flag `localbench run`, submit). Every identity flag exists because the CLI does not own the model artifact or the server, so the user must declare what the tool could know. This is the single biggest funnel-killer for the public launch. The catastrophic failure mode to design against: **a user burns 24 hours of GPU and the submission bounces.** Everything that can reject a run must be checked *before* the run starts.

## 2. Target UX

```
pip install "local-bench-ai[hf]"
localbench bench qwen3-6-27b
```

```
localbench 0.3.0 · bounded-final-v2 ranked lane
Model    qwen3-6-27b · Q4_K_M (auto-picked for 24 GB VRAM) · 16.5 GB download
Suite    suite-v1-full-exec-6axis-v1 (already cached)
Runtime  llama-server b6210 (detected on PATH)
Preflight  publishable=true (suite pair + identity envelope validated by server)
Estimate ~18–30 h on this GPU (RTX 5090 measured anchor; refined after first items)
Disk     needs 18.2 GB free on C: (has 68.4 GB)

Proceed? [Y/n]

[download] qwen3.6-27b-Q4_K_M.gguf  ████████░░ 82%  13.5/16.5 GB  41 MB/s  eta 1m12s
[serve]    llama-server started (pid 4321, port 18434) · health OK · load dry-run OK
[bench]    agentic  ████░░░░░░  212/512 items · 41% · elapsed 6h02m · eta 8h40m
...
[done]     Local Intelligence Index: 38.09  (agentic 41.2 · knowledge 55.1 · ...)
           Run saved: ~/.localbench/runs/qwen3-6-27b__q4km__20260708.json

Submit to local-bench.ai for maintainer review? [y/N]
[submit]   ticket a1b2c3d4 uploaded · status: pending maintainer review
           Community submissions never auto-rank; a maintainer verifies before anything publishes.
```

Flags: `--yes` (confirms local execution only — **never implies submit**), `--submit` / `--no-submit`, `--quant Q5_K_M`, `--vram-gb 16`, `--llama-server-path <exe>`, `--out <path>`, `--offline` (local-only; forces `--no-submit`), `--resume <state>`, `--allow-sleep-risk`, `--purge-model`.
**Non-TTY/CI:** fail fast unless every choice is explicit: `--yes`, exactly one of `--submit`/`--no-submit`, `--accept-suite-terms` where needed, and `--vram-gb`/`--quant` if VRAM is undetectable. Submit prompt defaults to **No** in TTY mode.

## 3. What the command owns (pipeline stages)

1. **Resolve** — `<model>` is a catalog slug (resolved against `https://local-bench.ai/data/catalog.json`, cached with TTL) or a raw HF `owner/repo` GGUF (**0.3.0: raw repos run local-only, not publishable** — see §5). Quant: `--quant`, else auto-pick for detected VRAM (nvidia-smi; if undetectable, prompt, or require `--vram-gb` non-TTY). Auto-pick must budget model bytes + ctx-32768 KV cache + runtime overhead + safety margin — not file size alone.
2. **Preflight (local)** — disk space for partial + final GGUF + suite/run headroom; `llama-server` on PATH (or `--llama-server-path`); **Windows power check**: if sleep/hibernate timers could fire mid-run, warn + require confirmation (TTY) or `--allow-sleep-risk` (non-TTY); print the full plan + estimate; single confirm.
3. **Publishability preflight (server)** — *before download or run*, compute the planned lane id, CLI package/version, submit schema version, suite release id, suite manifest sha256, scorer identity, catalog model id, quant label, and runtime kind, and call a production preflight endpoint. **Refuse to start unless the server returns publishable=true** with a registered suite-release/scorer pair for this exact CLI+suite+submit contract. `--offline` skips this but forces `--no-submit` and prints: "local-only run; not publishable until preflight succeeds." *(Requires a small new site Functions endpoint — in 0.3.0 build scope.)*
4. **Identity envelope pre-validation** — build the planned run envelope (score fields empty) with the exact model/runtime/suite identity object that would be submitted; run the same identity rules the submit verifier applies, and have the server preflight validate the envelope shape. Block on any missing field, unknown enum, suite-pair mismatch, or runtime field unobservable before launch. `model.identity_missing` after a one-shot run must be impossible.
5. **Download** — GGUF via `huggingface_hub` **pinned to an immutable HF commit SHA**, with resume + progress; obtain expected size (and etag/sha where available) up front; stream to a `.partial` file; verify sha256 after close; **atomic rename only after verification**; never benchmark an unverified partial. Honor Retry-After / bounded exponential backoff; if antivirus or file locks block rename/hash, retry then fail with the resume command *before* any benchmark starts.
6. **Tokenizer/template** — cache from the same pinned HF revision; record tokenizer_repo, tokenizer_revision, sha256 of tokenizer.json + tokenizer_config.json, chat_template_digest, snapshot tree digest, all computed from the exact local snapshot after a verified **offline** load; then `HF_HUB_OFFLINE=1` for the run. If any of these files change between preflight and run start, abort and require fresh preflight. Never resolve from a mutable branch.
7. **Serve** — spawn `llama-server` via direct process creation (no shell), bound to `127.0.0.1` on a free port with the pinned deterministic config (ctx 32768, single slot, kv f16). **Windows: assign to a Job Object with KILL_ON_JOB_CLOSE**; register Ctrl-C/Ctrl-Break handlers; persist child pid/port/commandline in run state. Health-check, then a **same-config load dry-run** (one tiny completion) before committing to the run — catches OOM/misfit immediately instead of at item 1. Record server version.
8. **Run** — existing bounded-final-v2 engine with the 0.2.5 progress/ETA line. Estimate printed as a range tied to the anchor hardware, refined after early items. Detect monotonic-clock gaps (sleep/wake): re-health-check the same server pid/version/model/config after wake; abort to a resumable checkpoint if anything changed.
9. **Scorecard** — print composite + axes locally; save run JSON.
10. **Submit (opt-in, default No)** — existing ticket/pack/upload path, unchanged server-side; prints ticket id + explicit "pending review, never auto-ranks" line. On failure the run JSON is already saved; print the exact `localbench submit run --run <path>` retry command (0.2.5 fixes that path's ticket-shape bug).
11. **Cleanup** — terminate the child by Job Object / recorded PID only (never name-sweep); stale-state cleanup may kill only a recorded child whose parent is gone AND whose exe path + commandline fingerprint match the run state. Keep the model file by default; print its path + `--purge-model` hint.

## 4. Identity auto-derivation (kills the 20-flag block)

**Precedence rule: artifact facts beat catalog metadata.** Catalog values *select* the artifact; final run identity comes from the verified bytes and the observed runtime. If file name/size/sha256, quant_label, hf_model_id, family, served model name, or launch config conflict with the catalog (or with what the manual Option-B recipe would declare), **abort before the run** and print the conflicting fields.

| Field | Source |
|---|---|
| file_name / file_size_bytes / file_sha256 | the verified download (post-atomic-rename bytes) |
| quant_label / family / hf_model_id | catalog entry, cross-checked against artifact facts (conflict → abort) |
| tokenizer_digest / chat_template_digest | the pinned-revision snapshot actually loaded offline |
| runtime name/version, ctx, slots, kv | the server the CLI spawned (observed, not assumed) |
| sampler pins + determinism policy | constants of the ranked lane |

The one-shot must produce a run record **byte-equivalent in identity fields** to a correctly-typed manual Option-B recipe — the verifier contract does not change.

## 5. Non-goals / deferred to 0.3.1+

- Shipping/managing llama.cpp binaries (detect + print install one-liner instead).
- **Raw arbitrary HF GGUF publishability** — raw `owner/repo` runs are local-only in 0.3.0 (scorecard, no submit); publishable one-shot requires a catalog slug. (Red-team scope cut: derived identity for arbitrary repos has too many edge cases for v1.)
- Catalog offline fallback beyond the TTL cache.
- vLLM one-shot (manual advanced path remains), multi-GPU orchestration, remote endpoints, Windows service mode, cross-platform parity polish beyond best-effort POSIX process-group handling.
- Broad ETA guarantees: the ±40% acceptance target applies to listed anchor model/GPU pairs only.

## 6. Safety / trust invariants (must not regress)

- ZT-1: one-shot submissions are **untrusted community submissions exactly like manual ones**. Any `source=one-shot` marker is metadata only — it must not bypass verifier checks, maintainer review, outlier visibility, suite-pair registration, or identity recomputation. A spoofed local llama-server or manipulated PATH is evidence for maintainer review, not a trusted attestation.
- Child server binds localhost only; killed by Job Object / captured PID (never name-sweep).
- Artifact sha256 verified before use; identity derived from the artifact actually benchmarked.
- Suite-release-pair / scorer-identity gate unchanged; no new secrets; existing keypair signing unchanged.

## 7. Failure handling & resume

- Every stage writes `plan.lock.json`: catalog revision, HF commit SHA, artifact path/size/sha256, tokenizer/template digests, suite manifest sha, scorer identity, CLI version, server binary path/version, launch config, port, run id.
- `localbench bench --resume <state>` reuses locked values verbatim, re-runs the publishability preflight, and **refuses silent catalog/suite/CLI upgrades** (any drift → explicit error naming the changed field).
- Ctrl-C leaves a resumable state and prints the resume command; existing per-item resume semantics preserved; existing server-unreachable circuit breaker covers mid-run child death.
- Server startup failure → print server log tail + the exact manual command as fallback.

## 8. Acceptance criteria

1. Fresh Windows box with only Python + llama-server on PATH: `pip install "local-bench-ai[hf]" && localbench bench <slug> --yes --no-submit` completes end-to-end.
2. The produced run passes the live verifier when submitted (identity complete, suite pair registered) — and a deliberately version-skewed CLI is **refused at preflight, not at submit**.
3. Kill-tests: Ctrl-C, parent-process kill, and simulated sleep/wake each leave no orphaned llama-server and a working `--resume`.
4. Manual advanced path still works and is still documented.
5. Estimate printed before start is within ±40% of actual wall time for the anchor models on anchor hardware.
6. Clean-room rehearsal (same protocol as the 07-07 user-journey pass) before release.

## 9. Build-scope note

The publishability preflight (stage 3) needs one new site endpoint (Functions): accept the planned contract tuple + identity envelope, return publishable true/false + reasons. Read-only against existing registration tables; no trust-model change.
