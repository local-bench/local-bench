# SPEC — tc_json_v1 tool-calling conformance bench (code only, NO GPU)

Repo branch `suite/v1-quant-wedge`. Do NOT push or commit (leave for review). `cli/runs/board/board_v1.json` byte-identical. STAY IN `cli/` — do NOT touch `web/`, `axes.py`, or board/leaderboard wiring (a separate task edits `web/`). Python = `cli\.venv\Scripts\python.exe`. Build the bench CODE + items + tests only; do NOT run any model (separate GPU-gated step); do NOT wire into the board/axes/web.

## Frozen contract — implement exactly
- bench id `tc_json_v1`; module constant `tc_json_v1_scorer = 1`.
- TRANSPORT: plaintext JSON only. Tool catalog given in PROMPT TEXT; model prints exactly ONE JSON object as final answer. NO native tools=/tool_choice, no grammar-constrained decoding, no backend tool parser (the point is cross-backend comparability).
- RESPONSE SCHEMA (frozen, JSON Schema draft 2020-12): object {schema_version: const "localbench.tc.v1", calls: array (minItems 0, maxItems 8) of object {name: string pattern ^[A-Za-z_][A-Za-z0-9_.-]*$, arguments: object}} with additionalProperties:false throughout. calls may be [] for no-call items.
- ITEM MANIFEST per item: {id, source, stratum, prompt, tools:[{name, description, parameters:<JSON Schema>}], gold:{order_matters:bool, calls:[{name, arguments}]}, match_policy:{default:"typed_canonical_json_equality", normalizers:{<json-pointer>:<normalizer-id>}, allow_default_omission:bool, unordered_arrays:[<json-pointer>]}}.
- SCORER — item correct IFF: (1) final response text trimmed is exactly ONE JSON object and a full-string parse consumes the whole string (reject extra prose / multiple objects / markdown fences); (2) validates the frozen response schema; (3) schema_version == "localbench.tc.v1"; (4) len(calls)==len(gold.calls); (5) every call.name in the item's tool catalog; (6) every call.arguments validates against that tool's parameters schema; (7) predicted calls match gold by name + CANONICALIZED args; (8) no extra/missing calls/args. Canonical TYPED equality: object key order ignored; array order matters UNLESS the field is in unordered_arrays; numbers compared numerically; strings exact after Unicode NFC unless a field normalizer is declared; date/time normalized only for fields tagged iso_date/iso_datetime/hhmm_24h; enum case-sensitive unless a casefold normalizer; default-valued optional args omitted only if allow_default_omission. order_matters -> exact-order compare, else perfect bipartite match. Failure taxonomy per item: invalid_json, extra_text_or_multiple_json_objects, response_schema_invalid, wrong_schema_version, wrong_call_count, wrong_tool, arg_schema_invalid, call_or_arg_mismatch (+ diagnostics extra_call/missing_call/arg_mismatch).
- PROMPT WRAPPER: fixed template stating the conformance task, the JSON tool catalog, the user request, the exact output schema + rules (no markdown, no prose, only catalog tools, args match the tool schema, return {"schema_version":"localbench.tc.v1","calls":[]} if no tool needed).
- AGGREGATE: raw ASR (NO chance correction — it is a gate) + Wilson 95% CI + failure-rate diagnostics. Gate bands (compute + expose, do NOT rank): GREEN ASR>=80% AND invalid_json<=5%; AMBER ASR 60-80% OR invalid_json 5-15%; RED ASR<60% OR invalid_json>15%.

## Items (60-100 total)
(a) BACKBONE: reuse the existing single-turn BFCL items in `cli/src/localbench/scorers/bfcl/` re-expressed through the tc_json envelope (same semantics — catalog + gold call/args — only the OUTPUT envelope changes; do NOT rewrite BFCL semantics).
(b) 20-40 FRESH hand-authored common-tool items (calendar.create_event, weather.get, web.search, email.send, unit.convert, timer.set, etc.) as a SEPARATE stratum/subscore, including a few no-call, a few multi-call, and a few decoy-tool items.

## Validity gate (the ToolHop lesson)
A gold-self-score harness that feeds each item's GOLD calls through the scorer and asserts 100% pass — add as a TEST. Any item that fails self-score is an item bug; fix the item, not the scorer.

## Tests (pytest, adversarial, judge-free)
malformed JSON, markdown fence, extra prose, duplicate JSON objects, wrong schema_version, missing/extra args, wrong tool, wrong call count, invalid types, no-call correct/incorrect, unordered-array, normalizer (date/hhmm/enum-casefold), default-omission allowed/not; plus gold-self-score 100% over all items.

## Runner/CLI
Like the existing funnels: given a served model base-url + id, build prompts, call the chat endpoint (plaintext; canonical greedy temp 0 / top_k 1 if supported), parse + score, write a results JSON (per-item response_text/extracted/correct/failure_reason/diagnostics + aggregate + bands). Implement + UNIT-TEST with a MOCK client — do NOT call a real model.

## VERIFY before reporting (do not commit/push)
`cd cli && .venv\Scripts\python.exe -m pytest tests/ -q` -> green (incl. new tc_json tests + gold-self-score 100%); module imports clean; board_v1.json untouched; web/ + axes.py untouched. REPORT: files added/changed, pytest result, item counts (BFCL backbone N + fresh N), a sample scored gold item showing the failure-taxonomy fields.
