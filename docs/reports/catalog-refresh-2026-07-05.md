# Catalog refresh report

Generated 2026-07-05 07:49 UTC by `scripts/catalog_refresh.py` against the public Hugging Face API.
Catalog: `web/model_catalog.json` (102 entries, refreshed in a catalog worktree). Proposed catalog: `model_catalog.proposed.json` (same shape, additive `base_model` only).

## Summary

| Metric | Count |
| --- | ---: |
| Entries checked | 102 |
| Verified clean (repo ok, sizes match, all catalog quants exist) | 56 |
| Entries with file_gb corrections | 4 (21 quant rows) |
| Entries with catalog quants MISSING from the repo | 35 (94 quant rows) |
| Entries whose repo ships quants NOT in the catalog | 95 |
| Dead / inaccessible gguf repos | 0 |
| Gated gguf repos | 0 |
| Fetch/parse errors | 2 |
| License differences | 0 |
| GGUF repo points at a different model (see mismatch table) | 11 |
| ... of which WRONG SCALE (>2x params off; sizes not applied) | 0 |
| Catalog `params_b` disagrees with the repo's GGUF param count | 6 |
| Entries gaining a `base_model` lineage field | 52 |
| New candidates discovered (not in catalog) | 2216 |

HTTP: 4 network requests, 501 cache hits, 0 transport errors.

## Dead or unreadable GGUF repos

| Entry | gguf_repo | Status | Note |
| --- | --- | --- | --- |
| deepseek-ai/DeepSeek-V4-Flash |  | error | no gguf_repo in catalog |
| microsoft/Phi-3-small-8k-instruct | LiteLLMs/Phi-3-small-8k-instruct-GGUF | error | no parsable .gguf files in repo listing |

## GGUF repo base-model mismatches

The GGUF repo's own metadata points at a different model than the catalog entry id. Rows marked **WRONG SCALE** quantize a model >2x params away from the entry (e.g. an 8B distill linked from a 671B entry) — their file sizes were **not** applied to the proposal; re-point `gguf_repo` instead. Same-scale rows are usually renames/variants (Meta- prefix, org renames, -BF16): sizes applied, link worth a look.

| Entry | gguf_repo | Repo declares base | Repo ~params B | Sizes applied |
| --- | --- | --- | ---: | --- |
| Qwen/Qwen3-30B-A3B | unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF | Qwen/Qwen3-30B-A3B-Instruct-2507 | 30.5 | yes |
| meta-llama/Llama-3.1-8B-Instruct | bartowski/Meta-Llama-3.1-8B-Instruct-GGUF | meta-llama/Meta-Llama-3.1-8B-Instruct | 8 | yes |
| meta-llama/Llama-3.1-70B-Instruct | MaziyarPanahi/Meta-Llama-3.1-70B-Instruct-GGUF | meta-llama/Meta-Llama-3.1-70B-Instruct | 70.6 | yes |
| meta-llama/Llama-3.1-405B-Instruct | MaziyarPanahi/Meta-Llama-3.1-405B-Instruct-GGUF | meta-llama/Meta-Llama-3.1-405B-Instruct | 410.1 | yes |
| deepseek-ai/DeepSeek-R1-Distill-Llama-70B | mradermacher/DeepSeek-R1-Distill-Llama-70B-heretic-GGUF | Total04/DeepSeek-R1-Distill-Llama-70B-heretic | 70.6 | yes |
| deepseek-ai/DeepSeek-V3 | MaziyarPanahi/DeepSeek-V3-0324-GGUF | deepseek-ai/DeepSeek-V3-0324 | 671 | yes |
| mistralai/Mistral-Small-3.1-24B-Instruct-2503 | MaziyarPanahi/mistral-small-3.1-24b-instruct-2503-hf-GGUF | mrfakename/mistral-small-3.1-24b-instruct-2503-hf | 23.6 | yes |
| mistralai/Ministral-3-3B-Instruct-2512 | lmstudio-community/Ministral-3-3B-Instruct-2512-GGUF | mistralai/Ministral-3-3B-Instruct-2512-BF16 | 3.4 | yes |
| microsoft/Phi-4-reasoning | lmstudio-community/Phi-4-reasoning-plus-GGUF | microsoft/Phi-4-reasoning-plus | 14.7 | yes |
| CohereLabs/c4ai-command-r-plus | bartowski/c4ai-command-r-plus-08-2024-GGUF | CohereForAI/c4ai-command-r-plus-08-2024 | 103.8 | yes |
| CohereLabs/c4ai-command-r7b-12-2024 | bartowski/c4ai-command-r7b-12-2024-abliterated-GGUF | huihui-ai/c4ai-command-r7b-12-2024-abliterated | 8 | yes |

## Catalog params_b vs repo GGUF param count

The linked repo IS this model (name-equivalent), but its GGUF metadata reports a parameter count >2x away from the catalog's `params_b` — usually an effective-vs-raw discrepancy (Gemma E-series) or a stale/underscoped MoE total. File sizes from the repo were applied (they are real files); review `params_b` (it drives the bpw-estimate formula and the VRAM overhead term).

| Entry | Catalog params_b (total) | Repo GGUF params B |
| --- | ---: | ---: |
| google/gemma-3n-E2B-it | 2 | 4.5 |
| google/gemma-4-E2B-it | 2 | 4.6 |
| deepseek-ai/DeepSeek-V4-Pro | 739 | 1573 |
| zai-org/GLM-5 | 355 | 753.9 |
| zai-org/GLM-5.1 | 355 | 753.9 |
| zai-org/GLM-5.2 | 355 | 753.9 |

## file_gb corrections (from actual repo file sizes)

Sizes are decimal GB (bytes / 1e9), rounded to 1 dp to match the catalog convention; `vram_gb_8k` is recomputed with the catalog formula `file_gb + 1.0 + 0.05 * params_b(total)`. Multi-part GGUFs are summed.

| Entry | Quant | file_gb old | file_gb new | vram_8k old | vram_8k new |
| --- | --- | ---: | ---: | ---: | ---: |
| deepseek-ai/DeepSeek-R1 | Q8_0 | 712.9 | **713.3** | 747.5 | 747.8 |
| deepseek-ai/DeepSeek-R1 | Q6_K | 553.6 | **550.8** | 588.1 | 585.3 |
| deepseek-ai/DeepSeek-R1 | Q5_K_M | 478.1 | **475.4** | 512.6 | 509.9 |
| deepseek-ai/DeepSeek-R1 | Q4_K_M | 406.8 | **404.4** | 441.3 | 438.9 |
| deepseek-ai/DeepSeek-R1 | Q3_K_M | 327.1 | **319.2** | 361.7 | 353.8 |
| deepseek-ai/DeepSeek-R1 | Q2_K | 251.6 | **244** | 286.2 | 278.6 |
| deepseek-ai/DeepSeek-R1-0528 | Q8_0 | 712.9 | **713.3** | 747.5 | 747.8 |
| deepseek-ai/DeepSeek-R1-0528 | Q6_K | 553.6 | **551** | 588.1 | 585.5 |
| deepseek-ai/DeepSeek-R1-0528 | Q5_K_M | 478.1 | **475.8** | 512.6 | 510.4 |
| deepseek-ai/DeepSeek-R1-0528 | Q4_K_M | 406.8 | **404.9** | 441.3 | 439.4 |
| deepseek-ai/DeepSeek-R1-0528 | Q3_K_M | 327.1 | **319.8** | 361.7 | 354.4 |
| deepseek-ai/DeepSeek-R1-0528 | Q2_K | 251.6 | **244.8** | 286.2 | 279.4 |
| microsoft/phi-4 | Q8_0 | 14.9 | **15.6** | 16.6 | 17.3 |
| microsoft/phi-4 | Q6_K | 11.5 | **12** | 13.2 | 13.7 |
| microsoft/phi-4 | Q2_K | 5.3 | **5.5** | 7 | 7.2 |
| zai-org/GLM-5 | Q8_0 | 377.2 | **801.3** | 395.9 | 820 |
| zai-org/GLM-5 | Q6_K | 292.9 | **619.4** | 311.6 | 638.1 |
| zai-org/GLM-5 | Q5_K_M | 252.9 | **535.2** | 271.7 | 554 |
| zai-org/GLM-5 | Q4_K_M | 215.2 | **455.9** | 234 | 474.6 |
| zai-org/GLM-5 | Q3_K_M | 173.1 | **360.3** | 191.8 | 379.1 |
| zai-org/GLM-5 | Q2_K | 133.1 | **276** | 151.9 | 294.8 |

## Catalog quants that do NOT exist in the GGUF repo

These stay in the proposed catalog (owner's call to prune or re-point `gguf_repo`), but the site is currently advertising files nobody can download.

| Entry | gguf_repo | Missing quants |
| --- | --- | --- |
| Qwen/Qwen3-0.6B | MaziyarPanahi/Qwen3-0.6B-GGUF | Q8_0 |
| Qwen/Qwen3-1.7B | MaziyarPanahi/Qwen3-1.7B-GGUF | Q8_0 |
| Qwen/Qwen3-4B | Qwen/Qwen3-4B-GGUF | Q3_K_M, Q2_K |
| Qwen/Qwen3-8B | MaziyarPanahi/Qwen3-8B-GGUF | Q8_0 |
| Qwen/Qwen3-14B | MaziyarPanahi/Qwen3-14B-GGUF | Q8_0 |
| Qwen/Qwen3-32B | MaziyarPanahi/Qwen3-32B-GGUF | Q8_0 |
| Qwen/Qwen3-4B-Instruct-2507 | MaziyarPanahi/Qwen3-4B-Instruct-2507-GGUF | Q8_0 |
| Qwen/Qwen3-4B-Thinking-2507 | MaziyarPanahi/Qwen3-4B-Thinking-2507-GGUF | Q8_0 |
| Qwen/Qwen3-Next-80B-A3B-Thinking | Qwen/Qwen3-Next-80B-A3B-Thinking-GGUF | Q3_K_M, Q2_K |
| Qwen/Qwen3.6-27B | unsloth/Qwen3.6-27B-MTP-GGUF | Q2_K |
| Qwen/Qwen3.6-35B-A3B | unsloth/Qwen3.6-35B-A3B-GGUF | Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| Qwen/Qwen2.5-Math-1.5B-Instruct | bartowski/Qwen2.5-Math-1.5B-Instruct-GGUF | Q3_K_M, Q2_K |
| meta-llama/Llama-3.1-70B-Instruct | MaziyarPanahi/Meta-Llama-3.1-70B-Instruct-GGUF | Q8_0 |
| meta-llama/Llama-3.1-405B-Instruct | MaziyarPanahi/Meta-Llama-3.1-405B-Instruct-GGUF | Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M |
| meta-llama/Llama-3.2-1B-Instruct | hugging-quants/Llama-3.2-1B-Instruct-Q8_0-GGUF | Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| meta-llama/Llama-3.2-3B-Instruct | bartowski/Llama-3.2-3B-Instruct-GGUF | Q3_K_M, Q2_K |
| google/gemma-4-12B-it | unsloth/gemma-4-12b-it-GGUF | Q2_K |
| google/gemma-4-26B-A4B-it | unsloth/gemma-4-26B-A4B-it-GGUF | Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| google/gemma-4-31B-it | unsloth/gemma-4-31B-it-GGUF | Q2_K |
| google/gemma-4-E2B-it | unsloth/gemma-4-E2B-it-GGUF | Q2_K |
| google/gemma-4-E4B-it | unsloth/gemma-4-E4B-it-GGUF | Q2_K |
| deepseek-ai/DeepSeek-V3 | MaziyarPanahi/DeepSeek-V3-0324-GGUF | Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M |
| deepseek-ai/DeepSeek-V3-0324 | MaziyarPanahi/DeepSeek-V3-0324-GGUF | Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M |
| deepseek-ai/DeepSeek-V3.2-Exp | sszymczyk/DeepSeek-V3.2-Exp-light-GGUF | Q6_K, Q5_K_M, Q3_K_M, Q2_K |
| deepseek-ai/DeepSeek-V4-Pro | teamblobfish/DeepSeek-V4-Pro-GGUF | Q6_K, Q5_K_M, Q3_K_M |
| mistralai/Mixtral-8x22B-Instruct-v0.1 | MaziyarPanahi/Mixtral-8x22B-Instruct-v0.1-GGUF | Q6_K |
| mistralai/Ministral-3-3B-Instruct-2512 | lmstudio-community/Ministral-3-3B-Instruct-2512-GGUF | Q5_K_M, Q3_K_M, Q2_K |
| mistralai/Ministral-3-8B-Instruct-2512 | mistralai/Ministral-3-8B-Instruct-2512-GGUF | Q6_K, Q3_K_M, Q2_K |
| microsoft/Phi-3-mini-4k-instruct | microsoft/Phi-3-mini-4k-instruct-gguf | Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| microsoft/phi-4 | microsoft/phi-4-gguf | Q5_K_M, Q4_K_M, Q3_K_M |
| microsoft/Phi-4-reasoning | lmstudio-community/Phi-4-reasoning-plus-GGUF | Q5_K_M, Q3_K_M, Q2_K |
| zai-org/GLM-5.1 | unsloth/GLM-5.1-GGUF | Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| zai-org/GLM-5.2 | unsloth/GLM-5.2-GGUF | Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |
| 01-ai/Yi-1.5-6B-Chat | MaziyarPanahi/Yi-1.5-6B-Chat-GGUF | Q8_0 |
| nex-agi/Nex-N2-Pro | paragon-of-brah/Nex-N2-Pro-397B-A17B-GGUF | Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M, Q2_K |

## Repo quants not in the catalog (available but unlisted)

Informational: the catalog intentionally carries a fixed 6-step ladder, but these labels are published in the linked repo.

| Entry | Additional repo quants |
| --- | --- |
| Qwen/Qwen3-0.6B | F16, Q3_K_L |
| Qwen/Qwen3-1.7B | F16, Q3_K_L |
| Qwen/Qwen3-4B | Q5_0 |
| Qwen/Qwen3-8B | F16, Q3_K_L |
| Qwen/Qwen3-14B | F16, Q3_K_L |
| Qwen/Qwen3-32B | Q3_K_L |
| Qwen/Qwen3-30B-A3B | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| Qwen/Qwen3-235B-A22B | BF16, IQ4_XS, Q2_K_L, Q3_K_S, Q4_1, Q4_K_S, Q5_K_S, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| Qwen/Qwen3-4B-Instruct-2507 | F16, Q3_K_L |
| Qwen/Qwen3-4B-Thinking-2507 | F16, Q3_K_L |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| Qwen/Qwen3-30B-A3B-Thinking-2507 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| Qwen/Qwen3-235B-A22B-Instruct-2507 | BF16, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| Qwen/Qwen3-235B-A22B-Thinking-2507 | BF16, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| Qwen/Qwen3-Coder-30B-A3B-Instruct | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| Qwen/Qwen3-Coder-Next | BF16, IQ4_NL, IQ4_XS, MXFP4_MOE, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_S, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| Qwen/Qwen3-Next-80B-A3B-Instruct | IQ1_M, IQ1_S, IQ2_M, IQ2_S, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_XS, IQ3_XXS, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_1, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| Qwen/Qwen3-Next-80B-A3B-Thinking | Q5_0 |
| Qwen/Qwen3.6-27B | BF16, IQ4_NL, IQ4_XS, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| Qwen/Qwen3.6-35B-A3B | BF16, MXFP4_MOE, UD-IQ1_M, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_NL_XL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_S, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL |
| Qwen/Qwen2.5-0.5B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-1.5B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-3B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-7B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-14B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-32B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-72B-Instruct | IQ1_M, IQ2_M, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_XXS, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0 |
| Qwen/Qwen2.5-Coder-7B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-Coder-14B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-Coder-32B-Instruct | F16, Q4_0, Q5_0 |
| Qwen/Qwen2.5-Math-1.5B-Instruct | F16, IQ3_M, IQ4_XS, Q3_K_L, Q3_K_XL, Q4_0, Q4_0_4_4, Q4_0_4_8, Q4_0_8_8, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| Qwen/Qwen2.5-Math-7B-Instruct | F16, IQ2_M, IQ3_M, IQ3_XS, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_0_4_4, Q4_0_4_8, Q4_0_8_8, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| Qwen/QwQ-32B | Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| meta-llama/Llama-3.1-8B-Instruct | F32, IQ2_M, IQ3_M, IQ3_XS, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0_4_4, Q4_0_4_8, Q4_0_8_8, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| meta-llama/Llama-3.1-70B-Instruct | IQ1_M, IQ1_S, IQ2_XS, IQ3_XS, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| meta-llama/Llama-3.1-405B-Instruct | Q3_K_S |
| meta-llama/Llama-3.2-3B-Instruct | F16, IQ3_M, IQ4_XS, Q3_K_L, Q3_K_XL, Q4_0, Q4_0_4_4, Q4_0_4_8, Q4_0_8_8, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| meta-llama/Llama-3.3-70B-Instruct | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| meta-llama/Llama-4-Scout-17B-16E-Instruct | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| meta-llama/Llama-4-Maverick-17B-128E-Instruct | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| google/gemma-3-1b-it | F16 |
| google/gemma-3-4b-it | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| google/gemma-3-12b-it | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| google/gemma-3-27b-it | Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| google/gemma-3n-E2B-it | F16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-3n-E4B-it | F16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-4-12B-it | BF16, F16, IQ4_NL, IQ4_XS, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-4-26B-A4B-it | BF16, F16, MXFP4_MOE, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-4-31B-it | BF16, F16, IQ4_NL, IQ4_XS, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-4-E2B-it | BF16, F16, IQ4_NL, IQ4_XS, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| google/gemma-4-E4B-it | BF16, F16, IQ4_NL, IQ4_XS, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| deepseek-ai/DeepSeek-R1 | BF16, Q2_K_L, Q2_K_XS, UD-IQ1_M, UD-IQ1_S, UD-IQ2_XXS, UD-Q2_K_XL |
| deepseek-ai/DeepSeek-R1-0528 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B | BF16, Q2_K_L, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-7B | F16, F32, IQ2_M, IQ3_M, IQ3_XS, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_1, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-14B | F16, Q2_K_L |
| deepseek-ai/DeepSeek-R1-Distill-Qwen-32B | F16, Q2_K_L |
| deepseek-ai/DeepSeek-R1-Distill-Llama-8B | BF16, F16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| deepseek-ai/DeepSeek-R1-Distill-Llama-70B | IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| deepseek-ai/DeepSeek-V3 | IQ1_M, IQ1_S, Q3_K_S |
| deepseek-ai/DeepSeek-V3-0324 | IQ1_M, IQ1_S, Q3_K_S |
| deepseek-ai/DeepSeek-V3.1 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| deepseek-ai/DeepSeek-V3.1-Terminus | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| deepseek-ai/DeepSeek-V3.2 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| mistralai/Mistral-7B-Instruct-v0.2 | Q3_K_L, Q3_K_S, Q4_0, Q4_K_S, Q5_0, Q5_K_S |
| mistralai/Mistral-7B-Instruct-v0.3 | F16, IQ1_M, IQ1_S, IQ2_XS, IQ3_XS, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| mistralai/Mistral-Nemo-Instruct-2407 | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| mistralai/Mistral-Small-Instruct-2409 | F16, IQ1_M, IQ1_S, IQ2_XS, IQ3_XS, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| mistralai/Mistral-Small-3.1-24B-Instruct-2503 | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| mistralai/Mistral-Small-3.2-24B-Instruct-2506 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| mistralai/Mixtral-8x7B-Instruct-v0.1 | Q4_0, Q5_0 |
| mistralai/Mixtral-8x22B-Instruct-v0.1 | F16, IQ1_M, IQ1_S, IQ3_XS, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| mistralai/Devstral-Small-2505 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| mistralai/Devstral-Small-2-24B-Instruct-2512 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| mistralai/Ministral-3-8B-Instruct-2512 | BF16 |
| mistralai/Ministral-3-14B-Instruct-2512 | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| mistralai/Mistral-Medium-3.5-128B | BF16, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| microsoft/Phi-3-mini-4k-instruct | F16 |
| microsoft/Phi-3-medium-4k-instruct | F32, IQ2_M, IQ3_M, IQ3_XS, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| microsoft/phi-4 | BF16, IQ3_M, IQ3_S, IQ3_XS, IQ3_XXS, IQ4_NL, IQ4_XS, Q3_K, Q3_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K, Q4_K_S, Q5_0, Q5_1, Q5_K, Q5_K_S, TQ1_0, TQ2_0 |
| microsoft/Phi-4-mini-instruct | F16, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| microsoft/Phi-4-reasoning | Q3_K_L |
| zai-org/GLM-5 | BF16, IQ4_NL, IQ4_XS, MXFP4_MOE, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL, UD-TQ1_0 |
| zai-org/GLM-5.1 | BF16, MXFP4_MOE, UD-IQ1_M, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_S, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL |
| zai-org/GLM-5.2 | BF16, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL |
| openai/gpt-oss-20b | F16, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-Q4_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| openai/gpt-oss-120b | F16, Q2_K_L, Q3_K_S, Q4_0, Q4_1, Q4_K_S, Q5_K_S, UD-Q4_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 01-ai/Yi-1.5-6B-Chat | Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| 01-ai/Yi-1.5-9B-Chat | F32, IQ1_M, IQ1_S, IQ2_M, IQ2_S, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_S, IQ3_XS, IQ3_XXS, IQ4_NL, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| 01-ai/Yi-1.5-34B-Chat | F32, IQ1_M, IQ1_S, IQ2_M, IQ2_S, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_S, IQ3_XS, IQ3_XXS, IQ4_NL, IQ4_XS, Q3_K_L, Q3_K_S, Q4_K_S, Q5_K_S |
| CohereLabs/c4ai-command-r-v01 | Q3_K_L, Q3_K_S, Q4_0, Q4_K_S, Q5_0, Q5_K_S |
| CohereLabs/c4ai-command-r-plus | IQ1_M, IQ2_M, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_XXS, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_0_4_4, Q4_0_4_8, Q4_K_L, Q4_K_S |
| CohereLabs/c4ai-command-r7b-12-2024 | BF16, IQ2_M, IQ3_M, IQ3_XS, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_1, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| nex-agi/Nex-N2-mini | BF16, IQ2_M, IQ2_S, IQ2_XS, IQ2_XXS, IQ3_M, IQ3_XS, IQ3_XXS, IQ4_NL, IQ4_XS, Q2_K_L, Q3_K_L, Q3_K_S, Q3_K_XL, Q4_0, Q4_1, Q4_K_L, Q4_K_S, Q5_K_L, Q5_K_S, Q6_K_L |
| nex-agi/Nex-N2-Pro | IQ1_M, IQ2_M, IQ3_M, IQ3_XXS, IQ4_KSS, IQ5_KS |

## New candidates: fine-tunes / merges of catalogued bases

Discovered via `?filter=base_model:finetune:{id}` (HF lineage tags), ranked by downloads. `GGUF repo` is a best-effort probe for a community quantization of the fine-tune itself.

| # | Repo | Downloads | Likes | Relation (base_model) | ~Params B | GGUF of it |
| ---: | --- | ---: | ---: | --- | ---: | --- |
| 1 | farbodtavakkoli/OTel-LLM-E4B-IT | 1,920,953 | 0 | finetune of google/gemma-4-E4B-it | 4 |  |
| 2 | nvidia/Gemma-4-31B-IT-NVFP4 | 1,359,044 | 524 | finetune of google/gemma-4-31B-it | 31 |  |
| 3 | nvidia/LocateAnything-3B | 1,194,542 | 2,607 | finetune of Qwen/Qwen2.5-3B-Instruct | 3 | yuuko-eth/LocateAnything-3B-GGUF |
| 4 | litert-community/gemma-4-E2B-it-litert-lm | 1,036,070 | 302 | finetune of google/gemma-4-E2B-it | 2 |  |
| 5 | jinaai/jina-reranker-v3 | 946,788 | 142 | finetune of Qwen/Qwen3-0.6B | ? | jinaai/jina-reranker-v3-GGUF |
| 6 | nvidia/DeepSeek-R1-0528-NVFP4-v2 | 903,558 | 23 | finetune of deepseek-ai/DeepSeek-R1-0528 | ? |  |
| 7 | k2-fsa/OmniVoice | 877,952 | 1,117 | finetune of Qwen/Qwen3-0.6B | ? | Serveurperso/OmniVoice-GGUF |
| 8 | prefeitura-rio/Rio-3.0-Open-Mini | 796,955 | 9 | finetune of Qwen/Qwen3-4B-Thinking-2507 | ? | mradermacher/Rio-3.0-Open-Mini-i1-GGUF |
| 9 | allenai/Molmo2-8B | 603,471 | 189 | finetune of Qwen/Qwen3-8B | 8 |  |
| 10 | Qwen/Qwen3-30B-A3B-FP8 | 508,657 | 84 | finetune of Qwen/Qwen3-30B-A3B | 30 |  |
| 11 | nomic-ai/nomic-embed-code | 441,116 | 121 | finetune of Qwen/Qwen2.5-Coder-7B-Instruct | ? | nomic-ai/nomic-embed-code-GGUF |
| 12 | mlabonne/Qwen3-30B-A3B-abliterated | 417,108 | 38 | finetune of Qwen/Qwen3-30B-A3B | 30 | mradermacher/Qwen3-30B-A3B-abliterated-GGUF |
| 13 | litert-community/gemma-4-E4B-it-litert-lm | 394,732 | 153 | finetune of google/gemma-4-E4B-it | 4 |  |
| 14 | unsloth/Llama-3.1-8B-Instruct | 325,886 | 13 | finetune of meta-llama/Llama-3.1-8B-Instruct | 8 | tensorblock/Llama-3.1-8B-Instruct-GGUF |
| 15 | unsloth/Meta-Llama-3.1-8B-Instruct | 311,029 | 97 | finetune of meta-llama/Llama-3.1-8B-Instruct | 8 | NoCanGo/WaifuGPT |
| 16 | nvidia/Llama-3.1-8B-Instruct-FP8 | 250,637 | 37 | finetune of meta-llama/Llama-3.1-8B-Instruct | 8 |  |
| 17 | unsloth/Qwen2.5-14B-Instruct | 243,893 | 11 | finetune of Qwen/Qwen2.5-14B-Instruct | 14 | Flamesline/Qwen2.5-14B-Instruct-Q4_K_M-GGUF |
| 18 | unsloth/gemma-4-E4B-it | 225,448 | 23 | finetune of google/gemma-4-E4B-it | 4 | pankajpandey-dev/gemma-4-e4b-hindi-instruct-GGUF |
| 19 | Qwen/Qwen2.5-Math-PRM-7B | 213,953 | 90 | finetune of Qwen/Qwen2.5-Math-7B-Instruct | 7 |  |
| 20 | YannQi/R-4B | 210,366 | 183 | finetune of Qwen/Qwen3-4B | 4 | infil00p/R-4B-GGUF |
| 21 | Open-Bee/Bee-8B-RL | 210,201 | 79 | finetune of Qwen/Qwen3-8B | 8 |  |
| 22 | unsloth/Llama-3.2-1B-Instruct | 207,232 | 100 | finetune of meta-llama/Llama-3.2-1B-Instruct | 1 | skshmjn/llama-3.2-1B-Mongo-query-generator |
| 23 | unsloth/gemma-3-4b-it | 203,425 | 27 | finetune of google/gemma-3-4b-it | 4 | mfielding92/Grok-3-gemma3-4B-distilled |
| 24 | NousResearch/Hermes-4-14B | 196,705 | 167 | finetune of Qwen/Qwen3-14B | 14 | bartowski/NousResearch_Hermes-4-14B-GGUF |
| 25 | Qwen/Qwen3Guard-Gen-0.6B | 191,142 | 75 | finetune of Qwen/Qwen3-0.6B | 0.6 | mradermacher/Qwen3Guard-Gen-0.6B-GGUF |
| 26 | Applied-Innovation-Center/Karnak-40B-v1.0 | 188,866 | 37 | finetune of Qwen/Qwen3-30B-A3B-Instruct-2507 | 40 |  |
| 27 | TrevorJS/gemma-4-26B-A4B-it-uncensored | 184,116 | 51 | finetune of google/gemma-4-26B-A4B-it | 26 |  |
| 28 | google/gemma-4-12B-it-qat-q4_0-unquantized | 184,081 | 62 | finetune of google/gemma-4-12B-it | 12 |  |
| 29 | unsloth/Qwen3-0.6B | 178,471 | 22 | finetune of Qwen/Qwen3-0.6B | 0.6 |  |
| 30 | unsloth/gemma-4-12b-it | 175,814 | 14 | finetune of google/gemma-4-12B-it | 12 |  |

## New candidates: popular GGUF repos not in the catalog

From per-family GGUF search plus `base_model:quantized:{id}` lineage. Quants listed where the repo detail was fetched (top candidates only). Params from GGUF metadata where available, else parsed from the name.

| # | Repo | Downloads | base_model | ~Params B | Quants |
| ---: | --- | ---: | --- | ---: | --- |
| 1 | antirez/deepseek-v4-gguf | 6,434,676 | deepseek-ai/DeepSeek-V4-Flash | 284.3 | F32 |
| 2 | unsloth/Qwen3.5-4B-GGUF | 1,046,626 | Qwen/Qwen3.5-4B | 4.2 | BF16, IQ4_NL, IQ4_XS, Q3_K_M, Q3_K_S, Q4_0, Q4_1, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 3 | unsloth/Qwen3.5-9B-GGUF | 1,025,777 | Qwen/Qwen3.5-9B | 9 | BF16, IQ4_NL, IQ4_XS, Q3_K_M, Q3_K_S, Q4_0, Q4_1, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 4 | unsloth/gemma-4-26B-A4B-it-qat-GGUF | 942,587 | google/gemma-4-26B-A4B-it-qat-q4_0-unquantized | 25.2 | BF16, F16, Q4_0, Q8_0, UD-Q4_K_XL |
| 5 | unsloth/Qwen3-VL-2B-Instruct-GGUF | 856,615 | Qwen/Qwen3-VL-2B-Instruct | 1.7 | BF16, IQ4_NL, IQ4_XS, Q2_K, Q2_K_L, Q3_K_M, Q3_K_S, Q4_0, Q4_1, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 6 | lmstudio-community/gemma-4-E4B-it-GGUF | 770,548 | google/gemma-4-E4B-it | 7.5 | Q4_K_M, Q6_K, Q8_0 |
| 7 | unsloth/Qwen3.6-35B-A3B-MTP-GGUF | 725,918 | Qwen/Qwen3.6-35B-A3B | 35.5 | BF16, MXFP4_MOE, Q8_0, UD-IQ1_M, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_S, UD-IQ3_XXS, UD-IQ4_NL, UD-IQ4_XS, UD-Q2_K_XL, UD-Q3_K_M, UD-Q3_K_XL, UD-Q4_K_M, UD-Q4_K_S, UD-Q4_K_XL, UD-Q5_K_M, UD-Q5_K_S, UD-Q5_K_XL, UD-Q6_K, UD-Q6_K_XL, UD-Q8_K_XL |
| 8 | lmstudio-community/gemma-4-12B-it-QAT-GGUF | 711,351 | google/gemma-4-12B-it-qat-q4_0-unquantized | 11.9 | Q4_0 |
| 9 | unsloth/Qwen3.6-27B-GGUF | 588,160 | Qwen/Qwen3.6-27B | 26.9 | BF16, IQ4_NL, IQ4_XS, Q3_K_M, Q3_K_S, Q4_0, Q4_1, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 10 | google/gemma-4-12B-it-qat-q4_0-gguf | 564,056 | google/gemma-4-12B-it-qat-q4_0-unquantized | 11.9 | Q4_0 |
| 11 | huihui-ai/Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF | 520,880 | deepseek-ai/DeepSeek-V4-Flash | 284.3 | BF16, F32, Q2_K, Q4_K |
| 12 | HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive | 518,354 | google/gemma-4-e4b-it | 7.5 | IQ3_M, IQ4_XS, Q2_K_P, Q3_K_M, Q3_K_P, Q4_K_M, Q4_K_P, Q5_K_M, Q5_K_P, Q6_K_P, Q8_K_P |
| 13 | unsloth/gemma-4-12B-it-qat-GGUF | 509,756 | google/gemma-4-12B-it-qat-q4_0-unquantized | 11.9 | BF16, F16, Q4_0, Q8_0, UD-Q4_K_XL |
| 14 | DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF | 504,420 | DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking | 39.1 | IQ2_M, IQ3_M, IQ4_NL, IQ4_XS, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0 |
| 15 | HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive | 504,321 | Qwen/Qwen3.5-9B | 9 | BF16, Q4_K_M, Q6_K, Q8_0 |
| 16 | HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive | 452,577 | Qwen/Qwen3.6-27B | 26.9 | IQ2_M, IQ3_M, IQ3_XS, IQ4_XS, Q2_K_P, Q3_K_P, Q4_K_P, Q5_K_P, Q6_K_P, Q8_K_P |
| 17 | ggml-org/gemma-4-26B-A4B-it-GGUF | 423,769 | google/gemma-4-26B-A4B-it | 25.2 | BF16, Q4_K_M, Q8_0 |
| 18 | unsloth/gemma-4-31B-it-qat-GGUF | 413,255 | google/gemma-4-31B-it-qat-q4_0-unquantized | 30.7 | BF16, F16, Q4_0, Q8_0, UD-Q4_K_XL |
| 19 | bartowski/Llama-3.2-1B-Instruct-GGUF | 409,414 | meta-llama/Llama-3.2-1B-Instruct | 1.2 | F16, IQ3_M, IQ4_XS, Q3_K_L, Q3_K_XL, Q4_0, Q4_0_4_4, Q4_0_4_8, Q4_0_8_8, Q4_K_L, Q4_K_M, Q4_K_S, Q5_K_L, Q5_K_M, Q5_K_S, Q6_K, Q6_K_L, Q8_0 |
| 20 | lmstudio-community/gemma-4-12B-it-GGUF | 409,335 | google/gemma-4-12B-it | 11.9 | Q4_K_M, Q6_K, Q8_0 |
| 21 | lmstudio-community/Qwen3.5-9B-GGUF | 391,445 | Qwen/Qwen3.5-9B | 9 | Q4_K_M, Q6_K, Q8_0 |
| 22 | unsloth/Qwen2.5-VL-7B-Instruct-GGUF | 389,022 | Qwen/Qwen2.5-VL-7B-Instruct | 7.6 | BF16, IQ4_NL, IQ4_XS, Q2_K, Q2_K_L, Q3_K_M, Q3_K_S, Q4_0, Q4_1, Q4_K_M, Q4_K_S, Q5_K_M, Q5_K_S, Q6_K, Q8_0, UD-IQ1_M, UD-IQ1_S, UD-IQ2_M, UD-IQ2_XXS, UD-IQ3_XXS, UD-Q2_K_XL, UD-Q3_K_XL, UD-Q4_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, UD-Q8_K_XL |
| 23 | ggml-org/gemma-4-12B-it-GGUF | 354,677 | google/gemma-4-12B-it | 11.9 | BF16, Q4_K_M, Q8_0 |
| 24 | google/gemma-4-E2B-it-qat-q4_0-gguf | 343,230 | google/gemma-4-E2B-it-qat-q4_0-unquantized | 4.6 | Q4_0 |
| 25 | yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF | 342,752 | google/gemma-4-12B-it | 11.9 | BF16, F16, Q3_K_M, Q4_K_M, Q6_K, Q8_0 |
| 26 | google/gemma-4-26B-A4B-it-qat-q4_0-gguf | 338,364 | google/gemma-4-26B-A4B-it-qat-q4_0-unquantized | 25.2 | Q4_0 |
| 27 | paperscarecrow/Gemma-4-31B-it-abliterated | 330,654 | google/gemma-4-31B-it | 30.7 | F16, Q4_K_M, Q8_0 |
| 28 | lmstudio-community/Qwen3.6-27B-GGUF | 329,106 | Qwen/Qwen3.6-27B | 26.9 | Q4_K_M, Q6_K, Q8_0 |
| 29 | lmstudio-community/Qwen3.6-35B-A3B-GGUF | 308,105 | Qwen/Qwen3.6-35B-A3B | 34.7 | Q4_K_M, Q6_K, Q8_0 |
| 30 | douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF | 293,659 | google/gemma-4-31b-it | 30.7 | Q3_K_M, Q4_K_M, Q8_0 |

## API notes / adaptations

- The catalog file is snake_case (`gguf_repo`, `file_gb`), not camelCase; the additive lineage field follows suit as `base_model` (string, or array when HF declares multiple bases, e.g. merges).
- Unauthenticated HF returns **HTTP 401 ("Invalid username or password")** for nonexistent *and* private repos alike, so "dead" above means "missing or private".
- `?expand[]=` cannot be combined with `?blobs=true`; the script does two flavours of fetch (canonical id with expand for downloads/likes/trendingScore/cardData, GGUF repo with blobs for file sizes).
- `downloads` from HF is the rolling ~30-day count; `downloadsAllTime` exists via expand but the catalog's numbers track the standard 30-day metric.
- `cardData.base_model` can be a string **or a list**; single-element lists are collapsed to a string in the proposal.
- Quant labels are parsed from GGUF filenames (incl. `IQ*`, `UD-*` unsloth dynamic, `MXFP4`, split `-00001-of-000NN` shards summed; `mmproj-*` projector files ignored).
- Scale guard: when the repo's `gguf.total` parameter count is >2x off the entry's `params_b`, sizes are only applied if the repo is name-equivalent to the entry (then the *catalog params_b* is flagged instead, e.g. Gemma E-series effective-vs-raw). Non-equivalent repos (e.g. an 8B distill linked from a 671B entry) get NO size updates and land in the mismatch table.

## Review workflow

1. Read this report; spot-check a few corrections against the repo file listings on huggingface.co.
2. Diff the proposal: `git diff --no-index web/model_catalog.json catalog-refresh-out/model_catalog.proposed.json`
3. If happy: `cp catalog-refresh-out/model_catalog.proposed.json web/model_catalog.json` and rebuild site data.
4. New candidates are NOT auto-added; curate manually (the fine-tune table carries `base_model` lineage for the new `base_model` field).
