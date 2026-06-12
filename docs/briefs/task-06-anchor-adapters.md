<task>
Build per-provider API anchor adapters for local-bench so we can run frontier reasoning
models (OpenAI GPT-5.x, Anthropic Claude, Google Gemini) through the SAME frozen suite as
local models. P0 found GPT-5-series reject max_tokens (need max_completion_tokens) and
temperature!=1; Anthropic isn't OpenAI-shaped natively; Gemini needs its OpenAI-compat layer.

Core principle: adapters change only HOW a request is formatted per provider, NEVER what is
asked. Same item sets, same rendered prompts, same semantic decoding intent (greedy where the
provider allows). Any unavoidable divergence (e.g. a reasoning model that won't honor greedy)
must be RECORDED in the run manifest so it's transparent, not hidden.

1. cli/src/localbench/providers/ — a small provider-profile layer:
   - A Provider protocol: build_payload(model, messages, decoding, lane) -> dict,
     endpoint_url(base) -> str, headers(api_key) -> dict, parse_response(json) ->
     ParsedCompletion (reuse existing ParsedCompletion incl. reasoning_text), and
     a name + notes() describing divergences.
   - Profiles:
     * openai_chat — classic models (gpt-4.1-mini etc.): max_tokens, temperature passthrough.
       Native /chat/completions.
     * openai_reasoning — GPT-5.x / o-series: max_completion_tokens (NOT max_tokens), OMIT
       temperature/top_p (they're rejected), read usage.completion_tokens_details.reasoning_tokens
       into the parsed result. Records divergence note "greedy not enforceable; provider-default sampling".
     * anthropic — /v1/messages, x-api-key + anthropic-version headers, system/messages shape,
       max_tokens required, optional extended-thinking (thinking: {type:enabled, budget_tokens})
       for the native-reasoning lane; map stop reasons; pull thinking blocks into reasoning_text.
     * gemini_openai — Google OpenAI-compat base
       https://generativelanguage.googleapis.com/v1beta/openai/ , bearer key, max_tokens ok,
       temperature ok; model ids like gemini-2.5-flash / gemini-3.x.
   - Auto-select profile from an explicit --provider flag (openai-chat|openai-reasoning|
     anthropic|gemini); do NOT auto-guess from model name (too brittle). Default for local
     endpoints stays the existing OpenAI-compatible path (a "local" profile == openai_chat
     semantics) so nothing about local runs changes.

2. Wire into the runner/orchestrator:
   - Add --provider (default "local" = current behavior) and thread a Provider into
     run_benchmark so payload/headers/url/parse go through it. Keep the existing thin path as
     the local/openai_chat profile — existing 104 tests must still pass unchanged.
   - The manifest's endpoint block records provider + any divergence notes() so a run that
     couldn't enforce greedy is self-describing.

3. Tests (no network): for each profile, unit-test build_payload (correct param names:
   max_completion_tokens vs max_tokens; temperature omitted for openai_reasoning; anthropic
   message shape; gemini base url) and parse_response (including reasoning_tokens / thinking
   blocks → reasoning_text, and the empty-content truncation case per provider). Use recorded
   sample JSON bodies, not live calls.

4. docs/anchor-adapters.md — short: each provider's endpoint, auth, param mapping, decoding
   divergences, and which model ids are current anchors (leave the exact ids as TODO for the
   manager to fill from a live /models check).
</task>

<action_safety>
Only touch cli/ (src + tests + pyproject if needed) and docs/anchor-adapters.md. Do NOT make
any network calls, do NOT touch suite/v0, attack/, or other docs. No git. No API keys in code
or tests — the runner reads keys from an env var named by --api-key-env (existing mechanism).
</action_safety>

<completeness_contract>
Done = full pytest green via cli/.venv (existing 104 + new provider tests); the local/default
path is behaviorally unchanged (existing runner/orchestrator tests untouched and passing);
`python -m localbench run --help` shows the new --provider flag.
</completeness_contract>

<verification_loop>
Run the full suite; confirm the default/local path is unchanged (diff behavior, not just
pass count). Do NOT make real API calls — the manager runs the live probes separately.
</verification_loop>

<missing_context_gating>No questions; choose sensible shapes from each provider's public API and note assumptions.</missing_context_gating>

<compact_output_contract>
Final message: (1) files created/modified, (2) pytest line, (3) the param-mapping table you
implemented per provider, (4) <=6 bullets decisions/assumptions to verify against live APIs.
</compact_output_contract>
