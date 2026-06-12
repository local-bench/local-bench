# Anchor API Adapters

Provider adapters only change the request envelope. The rendered benchmark items,
messages, and scoring path stay shared with local model runs.

| `--provider` | Endpoint | Auth | Token cap mapping | Sampling mapping | Response parsing |
|---|---|---|---|---|---|
| `local` | `{endpoint}/chat/completions` | Optional `Authorization: Bearer $KEY` | `max_tokens` | Passes suite decoding through unchanged, including local runtime fields | OpenAI-compatible `choices[0].message.content`, `reasoning_content`, `finish_reason`, `usage` |
| `openai-chat` | `{endpoint}/chat/completions` | `Authorization: Bearer $KEY` | `max_tokens` | Passes `temperature`, `top_p`, and other suite decoding through unchanged | Same OpenAI-compatible parser as `local` |
| `openai-reasoning` | `{endpoint}/chat/completions` | `Authorization: Bearer $KEY` | `max_tokens` -> `max_completion_tokens` | Omits `temperature`, `top_p`, `top_k`, `min_p`, `seed`, `chat_template_kwargs`, and `thinking_budget` | OpenAI-compatible parser plus `usage.completion_tokens_details.reasoning_tokens` -> `usage.reasoning_tokens` |
| `anthropic` | `{endpoint}/v1/messages` or `{endpoint}/messages` when the base already ends in `/v1` | `x-api-key: $KEY`, `anthropic-version: 2023-06-01` | `max_tokens` | Passes supported sampling fields through; `thinking_budget` with `--lane capped-thinking` becomes `thinking: {type: enabled, budget_tokens}` | Messages API content blocks: `text` -> response text, `thinking` -> `reasoning_text`; stop reasons map to OpenAI-style `stop`/`length`/`tool_calls` |
| `gemini` | `{endpoint}/chat/completions` using Google OpenAI-compatible base `https://generativelanguage.googleapis.com/v1beta/openai/` | `Authorization: Bearer $KEY` | `max_tokens` | Passes `temperature`, `top_p`, and other OpenAI-compatible decoding through unchanged | Same OpenAI-compatible parser as `local` |

## Decoding Divergences

`openai-reasoning` records the manifest note `greedy not enforceable; provider-default sampling`
because GPT-5/o-series chat endpoints reject the suite's greedy `temperature: 0`
and `top_p` controls. The adapter omits those fields rather than changing the
prompt, items, or scorer.

Anthropic extended thinking is only emitted when the suite/run supplies a
positive `thinking_budget` and the lane is `capped-thinking`. Otherwise the
adapter keeps the normal Messages API envelope.

## Anchor Model IDs

The exact anchor IDs should be filled after the manager runs live `/models`
checks:

| Provider | Current anchor model IDs |
|---|---|
| OpenAI chat | TODO |
| OpenAI reasoning | TODO |
| Anthropic | TODO |
| Gemini OpenAI-compatible | TODO |
