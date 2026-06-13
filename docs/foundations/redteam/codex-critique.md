SUCCESS: The process with PID 56724 (child process of PID 47836) has been terminated.
SUCCESS: The process with PID 69704 (child process of PID 47836) has been terminated.
SUCCESS: The process with PID 40740 (child process of PID 47836) has been terminated.
SUCCESS: The process with PID 53376 (child process of PID 82080) has been terminated.
SUCCESS: The process with PID 82080 (child process of PID 47836) has been terminated.
**VERDICT**: REVISE — make the homepage a GPU-tier decision finder first; demote the quality-vs-VRAM scatter to exploration, not the lead.

**Killer homepage lead**

Lead with: **“Best measured setups for my GPU”**.

Default it to a common power-user case like **24 GB VRAM / answer-only lane**, with rows ranked by a conservative decision metric: model × quant × runtime, score lower bound, frontier gap, memory footprint, tokens/sec, replicate count, and a clear verdict like `best measured under 24 GB`, `statistical tie`, `needs replication`, or `not enough data`.

That beats the quality-vs-VRAM scatter because the user’s real question is not “where are dots?” It is: **“What should I run on my 3090/4090/5090 tonight?”** A scatter is useful once there are dozens of points. At launch, with a handful of community runs and four anchors, it will look empty, derivative, and overdesigned. A tier finder survives sparse data because empty cells become useful: `No Q5 run for this model yet`, `needs llama.cpp replication`, `submit your 24 GB result`.

The killer bookmarked view is not “all models ranked.” It is **the 24 GB board**: a living Pareto table of what fits, what quality it buys, what quantization costs, and how far it is from frontier anchors on the same suite. LocalScore owns speed vibes; Artificial Analysis owns API model ranking. local-bench should own **“what is the smartest thing I can actually fit locally?”**

**Model-page hero**

Keep the quant-degradation idea, but do not present it as a naked statistics strip. Reframe it as **“Which quant should I run?”**

The hero should combine three things in one row per quant:

`quality delta vs baseline ± paired CI`  
`memory saved / fits which VRAM tier`  
`speed or token-cost change`

A local user does not care that Q4_K_M is `-4.6 ± 1.9` in isolation. They care whether that drop is worth fitting the model on 12 GB instead of 24 GB, or whether Q5_K_M is statistically tied while still saving enough memory. The paired CI is the moat, but the decision is the product.

If there is no matched baseline or only one quant run, do not render a broken hero. Render a coverage card: `Q4 measured, Q5/Q8 missing, bf16 baseline needed for paired delta`. That is more credible than pretending a model page has a complete quant story.

**Biggest risk**

The biggest risk is **precision theater on sparse, messy community data**.

This audience will immediately ask: Was this Ollama or vLLM? Same prompt template? Same context length? Same quant file? Same reasoning mode? N=1? Windows or Linux? If the homepage leads with a composite rank and dense CI styling before showing replication and setup comparability, skeptical users will classify it as “AA clone with fewer rows.”

CIs help only if they change decisions. Replication count, run manifest comparability, lane separation, and coverage gaps must be visible in the primary views, not buried on Trust or Run Detail pages.

**Cut list**

- Cut **“all models ranked” as the homepage mental model**. Keep it as a secondary table, not the product promise.
- Cut **frontier anchors as table competitors**. Show them as gap references only: `local setup is 18 pts behind GPT-5.5 anchor`, not as leaderboard rows to chase.
- Cut **radar charts**. They distort uncertainty and add nothing a five-axis bar profile does not show better.
- Cut **Reported Elsewhere** from model pages. It muddies the core claim: measured here, same suite, same scoring. External benchmark trivia belongs off the critical path.
- Cut **log-scale toggles, chart mode toggles, and clever visual controls** until the dataset is dense enough to need them.
- Cut **Quick runs from ranked surfaces**. Quick can be preview/coverage data, but the primary board should not mix unranked one-offs with serious comparisons.
- Cut **CI maximalism in tiny table cells**. Use dominance labels, lower-bound ranking, and expandable intervals; do not turn every row into statistical confetti.

**Concrete alternative IA**

`/` — **GPU Tier Finder**  
Lead view: selector for `8 / 12 / 16 / 24 / 32 / 48 GB`, lane, runtime family. Primary table shows best measured model × quant setups that fit, ranked by conservative score lower bound. Each row shows frontier gap, quant penalty, tokens/sec, replicate count, and whether the result is ranked or needs replication. Below it: compact quality-vs-VRAM scatter for exploration.

`/explore` — **Quality vs VRAM Scatter**  
Lead view: the current scatter, but as an analyst view. Filters for lane, VRAM budget, runtime, quant, replicated-only. This is where the AA-inspired chart belongs.

`/model/[slug]` — **Quant Decision Page**  
Lead view: “Which quant should I run?” matrix/strip. Rows are Q3/Q4/Q5/Q8/bf16 with paired quality delta, CI verdict, footprint, fit tier, speed delta, and best-run axis profile. Then runs table.

`/tier/[vram]` — **Bookmarkable GPU Board**  
Lead view: permanent pages like `/tier/24gb`. This is the weekly-return surface: new winners, replicated changes, missing high-interest runs, and “best current setup under this budget.”

`/run/[id]` — **Evidence Page**  
Lead view: manifest, per-axis/rung breakdown, contamination canary, prompt/runtime/hash provenance, and why this run is or is not rankable.

`/methodology` — **Measurement Credibility**  
Lead view: discrimination diagnostics, weights, chance baselines, no-LLM-judge rule, paired-delta explanation, and the published threat model. Trust should be part of methodology, not a separate marketing-ish destination.

`/submit` — **Run Contribution Funnel**  
Lead view: one CLI command, what uploads, what does not upload, how to produce a ranked run, and which missing GPU/model/quant cells are most wanted.
