# Model Catalog

This is scaffolding metadata for the local-bench benchmark website. It defines data-ready model-page shells only; it does not contain benchmark scores. Benchmark runs should attach scores later by the stable key pair `[model id + quant label]`.

## Size And VRAM Formula

For every quant entry:

`file_gb = params_b * bpw / 8`

`vram_gb_8k = file_gb + 1.0 + 0.05 * params_b`

Values are rounded to one decimal place. For MoE models, `params_b.total_b` is used for these estimates so file sizes stay conservative and consistent.

## Included Families

The catalog currently contains 102 base model shells across 33 families, with 10 attached community distill/finetune children. Included coverage spans Qwen3, Qwen3.6, Qwen2.5, Qwen2.5 Coder, Qwen2.5 Math, QwQ, Llama 3/4, Gemma 3/3n/4, DeepSeek R1/V3/V4, Mistral/Mixtral/Ministral/Devstral, Phi 3/4, GLM 5, GPT OSS, Yi 1.5, Command R/A, and Nex N2.

The list intentionally filters out test stubs, tiny-random/trl-internal models, ancient or seldom-run lines such as GPT-2/BLOOM/OPT, non-generation reward/classifier models, and pure vision models.

## Popularity Snapshot

Popularity values were pulled from the Hugging Face API during generation. Hugging Face does not provide a single catalog snapshot timestamp in the model metadata used here, so the snapshot date is treated as unknown. Each entry stores the API-provided downloads, likes, and trending score where available.

## Omissions And Notes

Requested ids or variants that did not resolve publicly through the Hugging Face API, or were represented by a nearby canonical repo, are omitted from `model_catalog.json`:

- google/gemma-4-27B (HF search did not resolve this exact id; included google/gemma-4-26B-A4B-it as the closest canonical Gemma 4 mid-size repo)
- zai-org/GLM-5-Air (HF API returned 401/not public to this request)
- zai-org/GLM-5.1-Air (HF API returned 401/not public to this request)
- zai-org/GLM-5.2-Air (HF API returned 401/not public to this request)
- Official Qwen3.6 MTP base repos (MTP appears in popular community GGUF finetunes, attached as children where resolved)

Qwen3.6 MTP variants are represented through resolved popular community GGUF children where available rather than separate base shells.

## Website Consumption

The website can load `web/model_catalog.json` as a model registry. Each object renders an empty model-page shell, each quant renders a selectable local-run target with estimated file and 8k VRAM requirements, and real benchmark scores should be joined later from run data keyed by `[model id + quant label]`.
