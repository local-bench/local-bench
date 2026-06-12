# Licensing audit — suite v0

Audited 2026-06-12 (P0 gate). Verdict: **suite v0 passes as designed — no component swaps.**

## Included components

| Component | License | Verified | Verdict |
|---|---|---|---|
| MMLU-Pro (TIGER-Lab, HF) | **MIT** | 2026-06-12, HF dataset card | PASS — serving question subsets via our API is permitted; ship attribution + MIT notice. 12,032 Qs, 14 categories, 10-option MCQ. |
| IFEval (google/IFEval, HF) | **Apache 2.0** | 2026-06-12, HF dataset card (official; arXiv 2311.07911) | PASS — 541 prompts; official checker code (google-research repo) is also Apache 2.0 and vendorable with license headers + NOTICE. |
| Generated math (ours) | Our authorship | n/a | PASS by construction. |

## Excluded components (decided pre-audit, recorded here)

- **GPQA** — HF-gated with an explicit author request not to republish examples online.
  CC-BY metadata likely makes redistribution *legal*, but serving questions via a public
  API violates the authors' stated intent; unacceptable community-standing risk. Excluded.
- **AIME** — MAA-copyrighted competition problems. Excluded; replaced by generated math.
- **LiveCodeBench-style coding** — deferred axis (code-exec on user machines = security
  trap); contest-problem redistribution provenance also murky.
- **SimpleBench** — answers deliberately private; cannot self-host.
- **HLE / CritPt** — local models floor ≈0; HLE additionally judge-dependent + canary'd.

## Obligations

1. Repo ships `LICENSES/` with MIT (MMLU-Pro) and Apache-2.0 (IFEval) texts; attribution
   on the site methodology page and in CLI `--licenses` output.
2. Vendored IFEval checker files keep their Apache headers; add NOTICE entry.
3. Re-run this audit at every suite version bump (P0 gate item; quarterly revision window).
