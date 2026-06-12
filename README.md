# local-bench

Community quality leaderboard for local AI setups — "Geekbench for local AI intelligence."

Run a frozen benchmark suite against your own rig (model × quant × runtime × settings) with
one command; results are server-scored and placed alongside frontier models measured on the
identical suite. Launch wedge: the quant-degradation dataset nobody publishes.

## Layout

- `cli/` — Python benchmark runner + submission client (`localbench`)
- `suite/` — versioned suite definitions: item sets, prompts, scorers, generated-math templates
- `web/` — leaderboard site (Next.js, P1)
- `docs/` — manifest schema, licensing audit, threat model, methodology

## Status

P0 validation spike (2026-06). Working name "local-bench" — naming TBD before launch.
