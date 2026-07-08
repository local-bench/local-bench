<task>
Perform a rigorous, READ-ONLY code review of the local-bench repository — the quality of this
code matters (it's a public benchmark whose credibility rests on correctness). Review BOTH:
- cli/src/localbench/** (runner, orchestrate, providers/*, scorers/*, scoring/* [signed_score,
  bootstrap, paired_delta, subgroups], manifest, _response, _suite, _requests, cli) and the
  generated-math engine suite/genmath_gen/**.
- web/build_data.py (the static data pipeline) and web/{lib,components,app}/** (Next.js prototype).
Do NOT review node_modules, .next, out, .venv, or web/public/data (generated).

Focus, in priority order:
1. CORRECTNESS — especially the statistics and scoring: chance-correction (signed_score), the
   stratified/paired bootstrap CIs (bootstrap.py), composite weighting, paired quant-delta math,
   answer extraction/scoring for MCQ/IFEval/genmath, and web/build_data.py's CI transform
   (mapping raw per-bench CI bounds through signed_score). Flag any statistical or logic error.
2. SECURITY — API key handling (must never be logged/persisted), any path traversal (e.g.
   web/lib/data.ts getModelData/getRunData reading models/${slug}.json — is slug constrained?),
   SSRF/endpoint handling, unsafe deserialization, prompt/HTML injection in the web render path.
3. ROBUSTNESS — error handling, truncation/empty-response handling, division-by-zero, null/None
   field handling, off-by-one in percentiles/bootstrap, determinism (seeds).
4. EFFICIENCY — obvious inefficiencies (redundant re-reads, O(n^2), unbounded work). Only flag if
   it matters at realistic scale (hundreds of items, single-digit models).
5. BEST PRACTICE / MAINTAINABILITY — typing, naming, dead code, duplicated logic, missing edge
   tests. No pure-style nitpicks unless they hurt clarity or correctness.
6. HONESTY/INTEGRITY of the product surface — does any label/number overclaim (e.g. presenting an
   unranked Quick estimate as ranked, calling self-repeats "Replicated", mixing reasoning lanes
   without disclosure, a CI that doesn't match its estimand)? This product's value is honest measurement.
</task>

<grounding_rules>
Cite every finding as file:line from the ACTUAL code you read. Do not invent issues. If something
is a hypothesis you could not fully verify, label it [hypothesis]. Distinguish real bugs from
style preferences. Prefer fewer, real, high-value findings over a long list of nits.
</grounding_rules>

<dig_deeper_nudge>
Look hard at: bootstrap.py percentile + stratified resample correctness; signed_score edge cases
(chance=1, raw<chance → negative scores and whether CIs handle that); build_data.py composite-match
assertion + the per-axis CI transform monotonicity; answer extraction regexes (false positives,
multiple-answer lines, case); IFEval checker fidelity; genmath public/private disjointness; the
web scatter's handling of null footprint and anchor reference lines; Promise.all fan-out re-reading
index per page. Try to find at least one real correctness issue before concluding it's clean.
</dig_deeper_nudge>

<structured_output_contract>
Output ONLY a findings report (no preamble) as your final message:
1. One-line verdict (SOLID / MINOR ISSUES / NEEDS FIXES).
2. Findings as a flat list, each: `[SEVERITY crit|high|med|low] file:line — issue — concrete fix`.
   Ordered by severity. Group nothing; one finding per line.
3. A 2-3 line "what's solid" note.
Keep it scannable. Cap at the ~20 highest-value findings.
</structured_output_contract>

<action_safety>READ-ONLY. Do not modify any file, run benchmarks, make network calls, or git-commit.
Analysis only.</action_safety>
