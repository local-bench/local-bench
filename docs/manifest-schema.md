# Canonical run manifest — schema v0

"Model × quant" is meaningless without identity. Every run uploads this manifest; runs
missing required identity fields are flagged **non-canonical** (shown, never ranked).

```jsonc
{
  "schema_version": "0.1",

  "suite": {
    "suite_version": "v0",
    "tier": "quick | standard",
    "item_set_hash": "sha256 of the exact item set served",
    "lane": "answer-only | capped-thinking | api-uncapped",   // reasoning-policy lane — boards never merge lanes
    "caps": { "max_tokens_mcq": 0, "max_tokens_math": 0, "thinking_budget": 0 }
  },

  "endpoint": {
    "kind": "local | api | byok",
    "runtime_reported_model": "id from /v1/models",           // exact string
    "api_provider": null                                       // api/byok only
  },

  "model": {                                                   // REQUIRED for canonical (local runs)
    "family": "qwen3.6-27b",
    "quant_label": "Q4_K_M | fp16 | awq-int4 | ...",
    "file_name": "qwen3.6-27b-Q4_K_M.gguf",
    "file_size_bytes": 0,
    "file_sha256": "… | UNHASHED",                             // UNHASHED allowed but → non-canonical
    "format": "gguf | safetensors | awq | gptq | exl3",
    "tokenizer_digest": "sha256 of tokenizer config/vocab | unknown",
    "chat_template_digest": "sha256 of template string | endpoint-applied-unknown"
  },

  "runtime": {                                                 // REQUIRED for canonical
    "name": "llama.cpp | ollama | vllm | lmstudio | exllamav3 | other",
    "version": "…",
    "kv_cache_quant": "f16 | q8_0 | q4_0 | unknown",
    "ctx_len_configured": 0,
    "parallel_slots": 0,
    "build_flags": "optional"
  },

  "hardware": {
    "gpus": [{ "name": "RTX 5090", "vram_mb": 0, "driver": "…" }],
    "cpu": "…", "ram_gb": 0, "os": "…"
  },

  "sampling": {                                                // REQUIRED for canonical
    "temperature": 0.0, "top_p": 1.0, "top_k": 0, "min_p": 0.0,
    "seed": null, "thinking_mode": "on | off | n/a"
  },

  "execution": {
    "client_version": "localbench x.y.z",
    "concurrency": 4,
    "started_at": "ISO8601", "finished_at": "ISO8601",
    "wall_clock_s": 0,
    "measured_tok_s": { "prompt": 0.0, "completion": 0.0 },    // free speed-board byproduct
    "per_item_timing": "included in run record (plausibility analysis)"
  },

  "rendered_prompt_sample": { "item_id": "…", "messages": [] }, // first item verbatim — template forensics

  "integrity": {
    "canonical": true,
    "missing_fields": []
  }
}
```

## Collection mechanics (CLI fills what it can, marks gaps)

| Runtime | Sources |
|---|---|
| Ollama | `/api/show` → quant, template, params, file digest; `/api/version` |
| llama.cpp server | `/props` → model path, ctx, build; hash file if path readable |
| vLLM | `/v1/models`, `/version`; model dir hash if local path known |
| LM Studio | `/v1/models`; limited — likely UNHASHED → non-canonical warning to user |
| GPU/driver | `nvidia-smi --query-gpu=...` (fallback: WMI/rocm-smi) |

## Canonical rule (v0)

`canonical = file_sha256 present (local) ∧ runtime.name+version ∧ quant_label ∧ sampling
complete ∧ ctx_len ∧ lane`. API/BYOK runs: provider + model id + sampling + lane suffice.
Non-canonical runs display with a grey badge and are excluded from ranked boards and
replication matching.
