# local-bench

Community quality leaderboard for local AI setups. The headline score is the **Local Intelligence Index** (`v1 · Core Text (Knowledge + Instruction)`): a reproducible Core Text tier with the Knowledge / Instruction profile shown beside the composite. Math, Coding-exec, and Agentic are candidate axes; a full Overall intelligence claim is earned only after those axes are validated and promoted.

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
