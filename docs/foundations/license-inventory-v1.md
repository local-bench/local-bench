# License and Redistribution Inventory — v1

**Scope:** local-bench.ai v1 public launch (direct-upload of `web/out/`).
**Date:** 2026-06-23
**Model:** Claude Sonnet 4.6

This document inventories every dataset, model, and artifact the project references or
redistributes, with license terms and redistribution implications.

---

## 1. Benchmark datasets (items in `suite/v1/`)

The suite item sets **are git-tracked** in `suite/v1/` (not gitignored). They are
**not served** in `web/out/` — the published site serves only scores and metadata.
The raw items are a private-repo artefact for v1. If the repo is ever published
publicly or the item sets are served directly, redistribution terms below apply.

### 1.1 MMLU-Pro

| Field | Value |
|---|---|
| Source | `TIGER-Lab/MMLU-Pro` on Hugging Face |
| Upstream revision | `b189ec765aa7ed75c8acfea42df31fdae71f97be` |
| License | **MIT** |
| Items in suite | 400 (sampled from 12,032 test items, 14 categories) |
| What we publish | Scores and accuracy metrics only; no question text in `web/out/` |
| What we redistribute (repo) | 400 items as `suite/v1/mmlu_pro.jsonl` (git-tracked, private repo) |
| Attribution required | MIT requires copyright notice in distributions of the software/data |
| Naming restrictions | None |
| **Action** | NOTICE file already credits TIGER-Lab MMLU-Pro under MIT. Sufficient for v1. If the item set is ever served publicly, verify TIGER-Lab's preferred attribution text. |

### 1.2 IFBench

| Field | Value |
|---|---|
| Source | `allenai/IFBench_test` on Hugging Face |
| Upstream revision | `2e8a48de45ff3bf41242f927254ca81b59ca3ae2` |
| License | **Apache-2.0** (Allen AI / AllenAI, confirmed by HuggingFace card) |
| Items in suite | 294 (293 after excluding `words:start_verb`) |
| What we publish | Scores only; no prompt text in `web/out/` |
| What we redistribute (repo) | 294 items as `suite/v1/ifbench.jsonl` (git-tracked, private repo) |
| Attribution required | Apache 2.0: retain copyright notice and provide notice of modifications |
| Naming restrictions | None |
| **Action** | NOTICE file credits IFEval (Google) under Apache 2.0 but does not separately credit AllenAI IFBench. Recommend adding an IFBench line to NOTICE. See §5 for draft. |

> Note: The NOTICE file credits "IFEval by Google Research" (the checker framework),
> which is correct. The IFBench dataset itself (AllenAI) is a separate entry that
> should also appear in NOTICE.

### 1.3 AMO-Bench (Olympiad Math component)

| Field | Value |
|---|---|
| Source | `meituan-longcat/AMO-Bench` on Hugging Face |
| Upstream revision | `2f422616c25d862984408fbbfaed63a961e8e025` |
| License | **MIT** |
| Items in suite | 39 (from 50, after dropping "description" answer type) |
| What we publish | Scores only |
| What we redistribute (repo) | 39 items as part of `suite/v1/amo.jsonl` (git-tracked, private repo) |
| Attribution required | MIT: retain copyright notice |
| Naming restrictions | None |
| **Action** | Add AMO-Bench attribution to NOTICE before any public-repo or item-serving scenario. |

### 1.4 OlymMATH-Hard

| Field | Value |
|---|---|
| Source | `RUC-AIBOX/OlymMATH` on Hugging Face |
| Upstream revision | `2c6532ea2cf929ac1c421532af5951553eaee727` |
| License | **MIT** |
| Items in suite | 100 (en-hard config) |
| What we publish | Scores only |
| What we redistribute (repo) | 100 items as part of `suite/v1/olymmath_hard.jsonl` (git-tracked, private repo) |
| Attribution required | MIT: retain copyright notice |
| Naming restrictions | None |
| **Action** | Add OlymMATH attribution to NOTICE before any public-repo or item-serving scenario. |

### 1.5 SuperGPQA

| Field | Value |
|---|---|
| Source | `m-a-p/SuperGPQA` on Hugging Face |
| Upstream revision | `4430d4458112c7d4497fdcf94d7cc223313d6acf` |
| License | **ODC-BY** (Open Data Commons Attribution License) |
| Items in suite | Sampled subset (build script validates against 26,529 source rows) |
| What we publish | Scores only; SuperGPQA is a legacy bench not in the v1.2 composite |
| What we redistribute (repo) | Items in `suite/v1/supergpqa.jsonl` (git-tracked, private repo) |
| Attribution required | ODC-BY requires attribution for any public use or database distribution |
| Naming restrictions | None; ODC-BY attribution must credit m-a-p/SuperGPQA |
| **Action** | Add SuperGPQA attribution to NOTICE. ODC-BY is more permissive than CC-BY-SA but does require attribution for public dataset distributions. |

### 1.6 Berkeley Function-Calling Leaderboard (BFCL)

| Field | Value |
|---|---|
| Source | `gorilla-llm/Berkeley-Function-Calling-Leaderboard` on HuggingFace + `ShishirPatil/gorilla` on GitHub |
| Upstream revisions | Dataset `61fc0608cfd831fcfbbaa676ebdfef0ed963eeda`; eval repo `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` |
| License | **Apache-2.0** (dataset + eval harness) |
| Items in suite | 300 (single/multiple/parallel/parallel_multiple, 75 each) + 100 multi-turn |
| What we publish | Scores only |
| What we redistribute (repo) | Items in `suite/v1/bfcl.jsonl` and `bfcl_multi_turn.jsonl` (git-tracked, private repo). Some multi-turn data is vendored from the eval repo. |
| Attribution required | Apache 2.0: retain notices |
| Naming restrictions | None |
| **Action** | Add BFCL attribution to NOTICE. The vendored multi-turn data from gorilla eval repo requires a `NOTICE`-level credit since it is embedded in the item set. |

### 1.7 LiveCodeBench (LCB)

| Field | Value |
|---|---|
| Source | `livecodebench/test_generation` on HuggingFace |
| Upstream revision | `6f3ac40bbecf81eba15899139d279b077f2816fd` |
| License | **CC-BY-4.0** (dataset); MIT (LiveCodeBench harness) |
| Items in suite | 129 items, window 2023-12-01 to 2024-03-02 |
| What we publish | Scores only |
| What we redistribute (repo) | 129 items in `suite/v1/lcb.jsonl` (git-tracked, private repo) |
| Attribution required | CC-BY-4.0 requires attribution for any redistribution. Must credit LiveCodeBench. |
| ToS note | Problem statements originate from LeetCode; LeetCode Terms of Service apply to problem text. Build script flags this as `SOURCE_TOS_NOTE`. |
| Naming restrictions | CC-BY-4.0 requires credit, a link to the license, and indicating if changes were made. |
| **Action** | CC-BY-4.0 is the most demanding dataset license in the suite for redistribution. Add LiveCodeBench attribution to NOTICE now. If items are ever served publicly, the CC license statement and a link to `https://creativecommons.org/licenses/by/4.0/` are required. |

### 1.8 RULER (NIAH reimplementation)

| Field | Value |
|---|---|
| Source | NVIDIA/RULER (algorithmic reimplementation, not vendored data) |
| License | **Apache-2.0** |
| Items in suite | 60 synthetic needle-in-a-haystack items, generated locally |
| What we publish | Scores only |
| What we redistribute (repo) | 60 items in `suite/v1/ruler_32k.jsonl`; these are locally generated using the NIAH pattern, not upstream data. `itemsets.lock.json` notes: "Stores compact seed parameters only; no upstream RULER code, prompts, or haystack data are vendored." |
| Attribution required | Apache 2.0 if redistributing the algorithm code; the generated output items are our own synthetic data. |
| Naming restrictions | None |
| **Action** | Low risk. The items are synthetically generated, not upstream data. Attribution to NVIDIA/RULER in NOTICE covers the algorithmic inspiration. Already documented in `itemsets.lock.json`. |

### 1.9 BigCodeBench-Hard (opt-in execution axis, not yet active in v1)

| Field | Value |
|---|---|
| Source | `bigcode/bigcodebench-hard` on HuggingFace |
| License | **Apache-2.0** |
| Items in suite | 148 items in `suite/v1/bigcodebench_hard.jsonl` (git-tracked) |
| Status | Opt-in code-execution axis — not yet active in v1.2 composite |
| What we publish | Not scored for v1; no items in `web/out/` |
| What we redistribute (repo) | 148 items git-tracked but inert for v1 |
| Attribution required | Apache 2.0 |
| **Action** | Add BigCodeBench attribution to NOTICE before the execution axis goes live. |

---

## 2. Models — names, scores, and GGUF references

The site **references** model names and publishes benchmark **scores** only. No model
weights, GGUF files, or embeddings are hosted or redistributed by the site.

### 2.1 License classes in the model catalog

| License class | Example models | Redistribution of weights? | Name/attribution requirements for a benchmarking site |
|---|---|---|---|
| **Apache-2.0** | All Qwen3.x, Qwen3.6, Qwen2.5, QwQ, DeepSeek-R1 variants, Mistral family, Phi family, GLM-5, most others | We do not redistribute | No special naming requirements; may publish scores and model names freely |
| **MIT** | DeepSeek-R1 (base), DeepSeek-V3-0324, DeepSeek R1 Distill variants | We do not redistribute | No special requirements |
| **Gemma license** (Google Terms of Use) | All gemma-3, gemma-3n, gemma-4 models | We do not redistribute | Gemma Terms of Use prohibit use of "Gemma" to endorse derived products without written permission, but benchmarking/evaluation and publishing scores is generally considered permissible. No branding endorsement claimed. |
| **Llama 3.x licenses** | meta-llama/Llama-3.1-*, Llama-3.2-*, Llama-3.3-* | We do not redistribute | Meta Llama 3 licenses permit benchmarking and publishing scores. If the site serves 700M+ MAU, a separate Meta licence is required for Llama 3.x use — not applicable at v1 scale. No branding endorsement claimed. |
| **CC-BY-NC-4.0** | Cohere Command R, Command R+, Command R7B | We do not redistribute | NC clause restricts commercial redistribution of the model weights. Publishing benchmark scores is not commercial redistribution. Attribution not required for evaluation-only use. |
| **Other / null** | Llama-4-Scout, Llama-4-Maverick (Meta Llama 4 license), DeepSeek-V3 (DeepSeek-V3 Terms), Qwen2.5-3B / Qwen2.5-72B (Tongyi Qianwen Community License) | We do not redistribute | Various; all permit benchmarking and score publication. |

### 2.2 Gemma — naming and attribution detail

Google's Gemma Terms of Use (https://ai.google.dev/gemma/terms) state:
- You must include a notice on derivative works: "Built with Gemma."
- You may not use the Gemma name to imply Google endorsement of a derived product.

**Interpretation for local-bench:** Publishing benchmark scores of Gemma models is
evaluation, not a derivative product. The site does not modify Gemma weights or build
a product that includes them. No "Built with Gemma" notice is required. Avoid any
language implying Google endorsement of the leaderboard itself.

**Action:** Review any copy on the methodology or model pages that mentions Gemma to
ensure it reads as benchmark evaluation, not endorsement.

### 2.3 Llama 3.x — naming and attribution detail

Meta Llama 3 license (applicable to Llama 3.1, 3.2, 3.3) permits:
- Benchmarking and publishing results — explicitly permitted as research.
- No attribution on the leaderboard is required beyond accurately naming the model.
- The MAU threshold (700M) for a separate license is not applicable at v1 scale.

**Action:** None required. Name models accurately (e.g., "Llama 3.3 70B Instruct"),
do not imply Meta endorsement.

### 2.4 Qwopus (community distill)

The `qwopus3-6-27b-v2-mtp` entry in the catalog references
`Jackrong/Qwopus3.6-27B-v2-MTP-GGUF` on Hugging Face. This is a community-created
GGUF fine-tune of Qwen3.6-27B. It inherits Qwen3.6-27B's Apache-2.0 base license
but the fine-tune itself may have additional terms set by Jackrong. Publishing
benchmark scores of it is evaluation use.

**Action:** Verify Jackrong's HuggingFace card for any restrictions before featuring
Qwopus prominently. Apache-2.0 base strongly suggests no restrictions on score
publication.

### 2.5 GGUF quantisations

The local machine runs GGUF quantisations (Q2_K through Q8_0) of publicly released
models. The site does not host, link to, or redistribute GGUF files. The leaderboard
references them by label only (e.g., "Q4_K_M") and maps runs to the canonical HuggingFace
model ID.

**Action:** None required. GGUF files are not redistributed.

---

## 3. IFEval checker (code vendored in CLI)

| Field | Value |
|---|---|
| Source | Google Research `instruction_following_eval` |
| License | **Apache-2.0** |
| What we vendor | Scoring logic adapted in `cli/src/localbench/scorers/ifeval/` |
| What we publish | Compiled into the CLI, not served in `web/out/` |
| Attribution required | Apache 2.0; NOTICE file already credits this |
| **Status** | PASS — NOTICE file covers this. |

---

## 4. Site codebase (web/) and CLI

The site and CLI are original work by the operator. No third-party open-source libraries
are vendored into `web/out/` in a way that requires additional attribution on the public
page beyond what npm licenses normally provide. Next.js (MIT), React (MIT), Tailwind
(MIT) — all permissive, no attribution required on public pages.

---

## 5. Recommended NOTICE additions

The current `NOTICE` file covers MMLU-Pro (MIT) and IFEval (Apache-2.0). The following
entries should be added before any public-repo or item-serving scenario:

```
This repository includes frozen benchmark item sets derived from:

- IFBench by Allen Institute for AI (AllenAI), distributed under the Apache License,
  Version 2.0. Source: https://huggingface.co/datasets/allenai/IFBench_test

- AMO-Bench by Meituan, distributed under the MIT License.
  Source: https://huggingface.co/datasets/meituan-longcat/AMO-Bench

- OlymMATH (en-hard) by RUC-AIBOX, distributed under the MIT License.
  Source: https://huggingface.co/datasets/RUC-AIBOX/OlymMATH

- SuperGPQA by m-a-p, distributed under the Open Data Commons Attribution License
  (ODC-BY). Source: https://huggingface.co/datasets/m-a-p/SuperGPQA

- Berkeley Function-Calling Leaderboard (BFCL) by Gorilla LLM / UC Berkeley,
  distributed under the Apache License, Version 2.0.
  Source: https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard

- LiveCodeBench (test_generation subset, 2023-12-01 to 2024-03-02) distributed under
  the Creative Commons Attribution 4.0 International License (CC-BY-4.0).
  Source: https://huggingface.co/datasets/livecodebench/test_generation
  License: https://creativecommons.org/licenses/by/4.0/

- RULER NIAH patterns (algorithmic reimplementation) by NVIDIA, distributed under the
  Apache License, Version 2.0.
  Source: https://github.com/NVIDIA/RULER

- BigCodeBench-Hard by BigCode, distributed under the Apache License, Version 2.0.
  Source: https://huggingface.co/datasets/bigcode/bigcodebench-hard
```

---

## 6. Summary: launch-blocking items

| Item | Severity | Action |
|---|---|---|
| IFBench (AllenAI) not in NOTICE | Moderate — Apache 2.0 attribution; items in private repo only for v1 | Add to NOTICE; resolve before any public-repo or item-serve |
| LiveCodeBench CC-BY-4.0 | High if items served publicly — CC requires attribution + licence link | Add to NOTICE now; if items ever served, add visible credit + licence URL |
| SuperGPQA ODC-BY | Moderate — ODC-BY attribution required for public distribution | Add to NOTICE before any public-repo |
| AMO-Bench, OlymMATH, BFCL, RULER, BigCodeBench | Low-moderate — MIT/Apache-2.0/Apache-2.0 | Add to NOTICE before public-repo |
| Gemma "Built with Gemma" clause | Non-issue for benchmarking | Confirm copy reads as evaluation, not endorsement |
| Llama 3.x MAU threshold | Non-issue at v1 scale | N/A |

For the **v1 Wrangler direct-upload launch**, where `web/out/` contains only scores
and metadata (no benchmark items), and the repo remains private, no redistribution
terms are currently violated. The primary pre-launch action is updating NOTICE to
reflect all datasets, which is best practice regardless of the deployment model.
