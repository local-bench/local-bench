# RULER 32k Long-Context Axis

`ruler_32k` is a compact, deterministic RULER-style needle-in-haystack axis for
suite-v1. The itemset stores seeds and generation parameters only. Runtime prompt
rendering regenerates the 32k whitespace-token synthetic haystack from each
row's `seed`, `haystack_token_count`, `target_depth_percent`, key(s), and
needle value(s).

Implemented task types:

- `niah_single`: one key-value needle; the model returns the value for that key.
- `niah_multikey`: four key-value needles, two queried keys, and two distractor
  needles; the model returns the queried values in key order.

The generator is an Apache-2.0-compatible local reimplementation of the
NVIDIA/RULER NIAH task pattern. No upstream RULER code, prompts, or haystack
data are vendored.

## Serving-Truncation Assertion

For `ruler_32k` only, `run_localbench` compares each response's reported
`usage.prompt_tokens` with a whitespace-token estimate of the rendered prompt.
The run is flagged when:

`usage.prompt_tokens < 0.80 * rendered_prompt_estimate`

and the absolute gap is at least 2,048 tokens. Missing `usage.prompt_tokens`
also emits a warning because full-context serving cannot be verified. Warnings
are stored both in top-level run `warnings` and on the affected item under
`warnings`, so a silently truncated endpoint is not mistaken for ordinary
long-context capability failure.
