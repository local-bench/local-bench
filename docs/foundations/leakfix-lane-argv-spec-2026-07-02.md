# Spec: lane-aware strict argv — reasoning-channel leak fix (2026-07-02)

Implements P0 of `docs/deploy/plan-ranked-row-2026-07-02.md`. Empirical probe results (Claude,
2026-07-02, b9852 + gemma-4-12B-QAT-UD-Q4_K_XL on the 5090, temperature 0 / top_k 1 / seed 1234):

| config | content result |
|---|---|
| `--reasoning off --reasoning-format none` (CURRENT argv) | **LEAKS** `<|channel>thought\n<channel|>` prefix (empty thought block left unparsed in content) |
| `--reasoning off --reasoning-budget 0 --reasoning-format none` | LEAKS (budget irrelevant; `none` is the culprit) |
| `--reasoning off --reasoning-format deepseek` | **CLEAN** (`4`, strict-JSON parses at position 0), reasoning_content empty |
| `--reasoning on --reasoning-budget 8192 --reasoning-format deepseek` | **CLEAN**, thinking in `message.reasoning_content` (129/279 chars on probes) |
| format omitted (= `auto`) | identical to deepseek — auto resolves to the same parser for this template |

**Root cause:** `--reasoning-format none` means "leave thoughts unparsed in message.content"
(b9852 --help). The explicit `deepseek` parser handles Gemma-4's channel scaffolding. **No `auto`
value is needed** — the no-`auto` strict-argv rule stands untouched.

## Required changes (cli/ only)

1. **`serving/llama_cpp.py`** — `LlamaCppLaunchConfig` gains explicit reasoning fields, e.g.
   `reasoning: str` ("on"|"off"), `reasoning_budget: int | None`, `reasoning_format: str`
   (default "deepseek"). `strict_llama_cpp_argv` emits them instead of the hardcoded
   `--reasoning off --reasoning-format none`:
   - answer-only lane → `--reasoning off --reasoning-format deepseek` (no budget flag)
   - capped-thinking lane → `--reasoning on --reasoning-budget 8192 --reasoning-format deepseek`
   Never emit `--reasoning-format none` again. `validate_strict_argv_supported` must still pass
   (all flags present in --help; no `auto` token).
2. **Lane → reasoning mapping** lives where the launch config is assembled (`serving/assembly.py` /
   `serving/bench.py`): map from the bench lane (`answer-only` | `capped-thinking`). `api-uncapped`
   is not a local-serving lane → raise a clear RuntimeError for `bench --runtime llama.cpp
   --lane api-uncapped`. The capped-thinking budget (8192) comes from the locked lane spec
   (METHODOLOGY v1.2: reasoning-budget 8192, max_tokens 16384) — keep it a named constant, pinned,
   not user-tunable in v1.
3. **Provenance**: the reasoning config must be recorded — it already flows into
   `server_fingerprint` via the argv hash, but also surface structured fields (reasoning mode /
   budget / format) in the serving/provenance block (`serving/provenance.py`) and the campaign
   `serve_fingerprint` so resume-safety and audits see it explicitly.
4. **reasoning_content capture**: verify the shared client path (providers/_openai / orchestrate
   response handling) captures `message.reasoning_content` into the existing per-item
   reasoning/`reasoning_text` slot when present (capped-thinking bundles must keep the thinking
   audit trail the June-30 pilot had). If it already does, add a test proving it; if not, wire it.
5. **Tests**: update the serving tests for the new argv (both lanes); add lane-mapping tests
   (answer-only, capped-thinking, api-uncapped-rejected); keep the full suite green
   (994 passed / 13 skipped / 1 xfail baseline).

## Hard constraints
- `cli/` only. Do NOT touch `cli/runs/board/board_v1.json` (frozen, git blob `3d058e60…`).
- Do NOT change anything that alters `scorecard_identity()` / `registry_digest` / scorer_versions
  (the released suites embed frozen scorecards). If a change would, STOP and report instead.
- Out of scope (separate tasks): leak-vocabulary unification (lane_conformance /
  strip_reasoning), GGUF identity-digest plumbing, web-side changes.
- No GPU runs, no pushes, no deploys.
