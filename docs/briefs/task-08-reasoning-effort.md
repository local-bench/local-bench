<task>
Add reasoning-effort control to local-bench so frontier anchors run at a chosen thinking
level (Michael wants high/xhigh). Today the openai-reasoning adapter sends no effort param,
so anchors run at provider-default effort. Thread an effort setting end-to-end and record it
in the manifest (it materially changes both scores and cost, so it MUST be captured).

1. CLI/orchestrator: add `--reasoning-effort {minimal,low,medium,high,xhigh}` (default: unset
   = provider default). Carry it on OrchestrateConfig and pass into the provider layer
   alongside lane.

2. Provider mapping (cli/src/localbench/providers/):
   - openai-reasoning: add `reasoning_effort: <value>` to the payload when set. "xhigh" may
     not be accepted by the standard API — send it as given; the live caller will see an
     error if rejected. Do NOT silently downgrade (we want to know). Add a note() if set.
   - anthropic: map effort → extended-thinking budget_tokens (minimal→thinking off; low→4096;
     medium→8192; high→16384; xhigh→32768), clamped to < the request max_tokens. Use the
     existing thinking block plumbing. Record the budget in note().
   - gemini: best-effort — pass reasoning_effort through the OpenAI-compat body if set
     (Google's compat layer accepts it for thinking models); note() that it's passthrough.
   - openai-chat / local: ignore effort (non-reasoning) — no-op, no error.
   - The Provider.build_payload signature gains an `effort: str | None` param (default None);
     update all profiles + callers. Keep default/local behavior byte-identical when effort is
     None (existing tests must pass unchanged).

3. Manifest: record sampling.reasoning_effort (the requested value) and the provider's
   effort note() in the endpoint block, so a run is self-describing.

4. Tests (extend test_provider_profiles.py): openai-reasoning includes reasoning_effort only
   when set; anthropic maps each effort level to the right budget and clamps to max_tokens;
   gemini passthrough; local/openai-chat unaffected; effort=None changes nothing.
</task>

<action_safety>
Only cli/ (providers/*, runner.py, orchestrate.py, cli.py, manifest.py, _types.py if needed,
tests). No suite/v0, no docs except you MAY update docs/anchor-adapters.md with the effort
mapping table. No git. No network/live calls.
</action_safety>

<completeness_contract>
Done = full pytest green via cli/.venv (127 existing + new, all passing); `python -m localbench
run --help` shows --reasoning-effort; effort=None leaves the default/local path byte-identical.
</completeness_contract>

<verification_loop>
Run the suite; confirm the None-effort path is unchanged (existing provider + orchestrator
tests untouched and green). No live API calls.
</verification_loop>

<missing_context_gating>No questions; pick sensible budget mappings and note them.</missing_context_gating>

<compact_output_contract>
Final: (1) files, (2) pytest line, (3) the effort→param mapping table per provider, (4) <=5
bullets decisions/assumptions to verify live.
</compact_output_contract>
