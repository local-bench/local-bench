<task>
Build the INSTRUCTION-FOLLOWING axis for local-bench suite-v1 by vendoring IFBench's fresh programmatic
constraint verifiers (Apache-2.0) and building a frozen IFBench itemset. IFBench was built because
IFEval saturated; it adds new verifiable instruction constraints.

Repo root: C:/Users/Michael/local-bench (cwd). Venv: cli/.venv (use ./.venv/Scripts/python.exe from
cli/). `datasets` is installed. There is an EXISTING vendored IFEval scorer at
cli/src/localbench/scorers/ifeval/ — study it for the interface + house style, but DO NOT modify it.
</task>

<context>
- The existing IFEval scorer (cli/src/localbench/scorers/ifeval/scorer.py) exposes:
    score_ifeval(prompt_item: Mapping, response_text: str) -> {"strict": bool, ...}
  where prompt_item carries the instruction spec (instruction_id_list + kwargs). The dispatch
  (_scoring.py) calls score_ifeval(source_item, response_text)["strict"], and the rendered prompt
  (_suite.py) is just source_item["prompt"]. MIRROR this interface for IFBench so wiring is trivial.
- Build a NEW self-contained package cli/src/localbench/scorers/ifbench/ exposing:
    score_ifbench(prompt_item: Mapping, response_text: str) -> {"strict": bool, ...}
  Vendor IFBench's constraint verifier functions (Apache-2.0) faithfully; keep attribution (license
  header / NOTICE in the package). You MAY import clean low-level helpers from the existing ifeval
  package, but do NOT modify the ifeval package.
- Dataset: IFBench (AllenAI). Confirm canonical HF id + ODC-BY data license + Apache verifier code
  license before use. Item schema mirrors ifeval: id/key, prompt, instruction_id_list, kwargs (use the
  fields the verifiers require). suite-v1 lives under suite/v1/.
- The manager (Claude) owns suite.json, dispatch (_scoring.py/_suite.py), and templates. You produce the
  scorer package + itemset + builder + tests + datasheet ONLY.
</context>

<deliverables>
1. cli/src/localbench/scorers/ifbench/ — vendored verifiers + score_ifbench (interface above). It must
   NEVER raise on malformed model output (return strict=False instead).
2. suite/v1/ifbench.jsonl — frozen IFBench items in the schema the verifiers consume. Stable sequential
   ids ("ifbench-001" ...).
3. suite/build_v1_ifbench.py — reproducible (pin dataset id + revision); re-running reproduces the jsonl
   byte-for-byte.
4. cli/tests/test_ifbench.py — unit tests for the verifiers (each constraint type: one passing + one
   failing response) AND a PARITY check vs the reference IFBench implementation if it is
   installable/cloneable in this environment (run a sample through both, assert agreement). If the
   reference cannot be run here, say so explicitly and instead assert against hand-verified expected
   outputs, explaining the gap.
5. cli/tests/test_v1_ifbench_items.py — gate: items load as JSONL, schema valid, ids unique, and EVERY
   item's instruction spec is RECOGNIZED by score_ifbench (no unknown/unsupported constraint ids — that
   would mean an unscorable item). Fail loudly and name offenders.
</deliverables>

<action_safety>
Touch ONLY: cli/src/localbench/scorers/ifbench/** , suite/v1/ifbench.jsonl, suite/build_v1_ifbench.py,
cli/tests/test_ifbench.py, cli/tests/test_v1_ifbench_items.py. Network is for the HF/GitHub fetch only.
Do NOT edit scorers/ifeval/**, _scoring.py, _suite.py, suite/v0/, any suite.json, any template, anything
under web/, or any existing test file.
</action_safety>

<verification_loop>
From cli/: ./.venv/Scripts/python.exe -m pytest tests/test_ifbench.py tests/test_v1_ifbench_items.py -q
must pass, and the full suite ./.venv/Scripts/python.exe -m pytest -q must stay green (currently 367).
Report counts and the exact pip/clone commands you ran.
</verification_loop>

<completeness_contract>
End with a datasheet: HF dataset id + revision + a quote of the data license; the verifier code source +
license; the list of constraint types you vendored (and any IFBench constraints you did NOT vendor +
why); item count; the parity result (vs reference, or why it could not be run); 3 sample items; anything
dropped. Do NOT claim the axis is wired or runnable — wiring is Claude's next step.
</completeness_contract>
