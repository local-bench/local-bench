# Anchor API Adapters

Provider adapters only change the request envelope. The rendered benchmark items,
messages, and scoring path stay shared with local model runs.

| `--provider` | Endpoint | Auth | Token cap mapping | Sampling mapping | Response parsing |
|---|---|---|---|---|---|
| `local` | `{endpoint}/chat/completions` | Optional `Authorization: Bearer $KEY` | `max_tokens` | Passes suite decoding through unchanged, including local runtime fields | OpenAI-compatible `choices[0].message.content`, `reasoning_content`, `finish_reason`, `usage` |
| `openai-chat` | `{endpoint}/chat/completions` | `Authorization: Bearer $KEY` | `max_tokens` | Passes `temperature`, `top_p`, and other suite decoding through unchanged | Same OpenAI-compatible parser as `local` |
| `openai-reasoning` | `{endpoint}/chat/completions` | `Authorization: Bearer $KEY` | `max_tokens` -> `max_completion_tokens` | Omits `temperature`, `top_p`, `top_k`, `min_p`, `seed`, `chat_template_kwargs`, and `thinking_budget` | OpenAI-compatible parser plus `usage.completion_tokens_details.reasoning_tokens` -> `usage.reasoning_tokens` |
| `anthropic` | `{endpoint}/v1/messages` or `{endpoint}/messages` when the base already ends in `/v1` | `x-api-key: $KEY`, `anthropic-version: 2023-06-01` | `max_tokens` | Passes sampling fields through unless thinking is enabled. For `--reasoning-effort low\|medium\|high\|xhigh`, or capped-thinking with a positive `thinking_budget`, omits `temperature`, `top_p`, `top_k`, `min_p`, and `seed`, then sends `thinking: {type: adaptive}` plus `output_config.effort` | Messages API content blocks: `text` -> response text, `thinking` -> `reasoning_text`; `usage.output_tokens_details.thinking_tokens` -> `usage.reasoning_tokens`; stop reasons map to OpenAI-style `stop`/`length`/`tool_calls` |
| `gemini` | `{endpoint}/chat/completions` using Google OpenAI-compatible base `https://generativelanguage.googleapis.com/v1beta/openai/` | `Authorization: Bearer $KEY` | `max_tokens` | Passes `temperature`, `top_p`, and other OpenAI-compatible decoding through unchanged | Same OpenAI-compatible parser as `local` |

## Decoding Divergences

`openai-reasoning` records the manifest note `greedy not enforceable; provider-default sampling`
because GPT-5/o-series chat endpoints reject the suite's greedy `temperature: 0`
and `top_p` controls. The adapter omits those fields rather than changing the
prompt, items, or scorer.

Anthropic extended thinking uses the current adaptive Messages API format:
`thinking: {type: adaptive}` plus `output_config.effort`. `--reasoning-effort
minimal` leaves thinking off; `low`, `medium`, and `high` map directly;
`xhigh` clamps to Anthropic `high`. When the lane is `capped-thinking` and no
explicit effort is supplied, a positive `thinking_budget` selects medium
effort. Anthropic thinking rejects non-default sampling controls, so the
adapter omits `temperature`, `top_p`, `top_k`, `min_p`, and `seed` whenever
thinking is enabled.

## Anchor Model IDs

The exact anchor IDs should be filled after the manager runs live `/models`
checks:

| Provider | Current anchor model IDs |
|---|---|
| OpenAI chat | TODO |
| OpenAI reasoning | TODO |
| Anthropic | TODO |
| Gemini OpenAI-compatible | TODO |
