<task>
Fix the Anthropic provider (cli/src/localbench/providers/_anthropic.py) to use the CURRENT
extended-thinking API. The existing budget_tokens approach is the year-old Claude-3.7 format
and is REJECTED by current models (claude-opus-4-8, claude-sonnet-4-6). All formats below
were verified LIVE against the real API today — implement exactly these.

CONFIRMED live findings (do not second-guess):
1. Current models reject `thinking: {"type":"enabled","budget_tokens":N}` with:
   "thinking.type.enabled is not supported for this model. Use thinking.type.adaptive and
   output_config.effort to control thinking behavior."
2. The WORKING format (verified OK on claude-opus-4-8): add BOTH
   `"thinking": {"type": "adaptive"}` and `"output_config": {"effort": <level>}`.
   (effort-only also works, but include both for clarity.)
3. With thinking enabled, Anthropic REJECTS temperature/top_p/top_k != default:
   "temperature may only be set to 1 when thinking is enabled." → when thinking is enabled,
   DROP temperature, top_p, top_k, min_p, seed from the payload (greedy is not enforceable
   with Anthropic thinking — record a divergence note).
4. Thinking-token usage is reported at `usage.output_tokens_details.thinking_tokens` (int).
   anthropic-version header "2023-06-01" works with this format — keep it.

Implement:
- Effort → output_config.effort mapping (Anthropic valid set is minimal|low|medium|high):
  minimal → thinking OFF (no thinking/output_config); low→"low"; medium→"medium";
  high→"high"; **xhigh → "high" (clamp; add a note that xhigh clamped to Anthropic high)**.
- build_payload: when effort is low/medium/high/xhigh, set
  `payload["thinking"] = {"type":"adaptive"}` and `payload["output_config"] = {"effort": <mapped>}`,
  and OMIT the sampling keys (temperature/top_p/top_k/min_p/seed) in addition to the existing
  omit set. When effort is None, keep the lane-based path BUT it must also use the current
  adaptive format if it ever enables thinking (the old capped-thinking budget_tokens path is
  dead — replace it: capped-thinking lane with no effort → treat as medium effort, or leave
  thinking off if that's simpler; pick one and note it).
- parse_response/_parse_usage: capture thinking_tokens from
  usage.output_tokens_details.thinking_tokens into Usage["reasoning_tokens"] (NotRequired).
- notes(): replace budget_tokens notes with effort-mapping notes + the greedy-divergence note
  + the xhigh→high clamp note.
- Rewrite the 6 now-obsolete tests in test_provider_profiles.py to assert the new payload
  shape (output_config.effort, thinking.type=adaptive, sampling dropped) and the new notes.
  Add a test that thinking_tokens is parsed into reasoning_tokens.
</task>

<action_safety>
Only cli/src/localbench/providers/_anthropic.py and cli/tests/test_provider_profiles.py (and
docs/anchor-adapters.md effort table if present). Do NOT touch other providers, the runner,
orchestrator, suite, or make network calls. No git.
</action_safety>

<completeness_contract>
Done = full pytest green via cli/.venv (all, including the rewritten Anthropic tests);
no remaining reference to the old `{"type":"enabled","budget_tokens"...}` thinking format.
</completeness_contract>

<verification_loop>
Run the full suite; ensure no other provider's tests regressed. You cannot make live calls —
trust the confirmed formats above; build payload shape to match them exactly.
</verification_loop>

<missing_context_gating>No questions; the live-confirmed formats above are authoritative.</missing_context_gating>

<compact_output_contract>
Final: (1) files, (2) pytest line, (3) the exact thinking/output_config payload shape you now
emit for effort=high, (4) <=5 bullets on the effort mapping + capped-thinking-lane decision.
</compact_output_contract>
