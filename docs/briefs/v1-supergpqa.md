<task>
Acquire SuperGPQA (the Knowledge & Reasoning axis for local-bench suite-v1), apply a provenance /
contamination filter, and build a frozen MCQ itemset + reproducible builder + a gate test. The scorer is
the EXISTING multiple-choice scorer (cli/src/localbench/scorers/mcq.py) — you are NOT writing a new
scorer, only the data layer.

Repo root: C:/Users/Michael/local-bench (cwd). Venv: cli/.venv (use ./.venv/Scripts/python.exe from cli/).
The `datasets` library is installed.
</task>

<context>
- MCQ item schema — MATCH the existing suite/v0/mmlu_pro_*.jsonl exactly: one JSON object per line:
    {"id": "<stable id>", "question": "<question text>", "options": ["opt A", "opt B", ...], "answer": "<GOLD LETTER>"}
  `answer` is the gold OPTION LETTER (A, B, C, ...) uppercase; option index i maps to letter
  chr(ord('A')+i). Confirm by reading a couple of suite/v0/mmlu_pro_standard.jsonl rows first.
- The scorer (cli/src/localbench/scorers/mcq.py): score_mcq_detailed(text, gold_letter, n_options). It
  supports AT MOST 10 options (letters A..J). So EVERY item you emit must have 2..10 options and a gold
  letter within range — anything else cannot be scored and must be dropped.
- SuperGPQA license = ODC-BY (confirm on the HF dataset card). It is partly transformed from upstream MCQ
  sets; the license audit flagged we must honor those upstream licenses. Your filter MUST drop any item
  whose provenance is a gated / non-commercial / non-redistributable upstream IF that provenance is
  identifiable from the dataset fields. Document what you filtered and what you could not determine — flag,
  do not guess.
- suite-v1 lives under suite/v1/. The manager (Claude) owns the manifest, dispatch, and template. You
  produce the ITEM FILE + builder + test + datasheet ONLY.
</context>

<deliverables>
1. Confirm the canonical HF dataset id + ODC-BY license; inspect the schema (fields, number of options,
   discipline/field/subfield columns, and any source/provenance column).
2. A documented provenance/contamination filter: drop non-redistributable-upstream items where
   identifiable; drop malformed / >10-option / missing-or-ambiguous-gold items.
3. suite/v1/supergpqa.jsonl — a frozen STRATIFIED subset of ~400 items, stratified across disciplines
   (and difficulty if the dataset exposes it) for breadth, in the MCQ schema above. Stable sequential ids
   ("supergpqa-001" ...).
4. suite/build_v1_supergpqa.py — reproducible: pin dataset id + revision, deterministic seed for the
   stratified sample. Re-running reproduces the jsonl byte-for-byte.
5. cli/tests/test_v1_supergpqa_items.py — asserts: loads as JSONL; schema exact; ids unique; EVERY item
   has 2..10 options and a gold letter within range (so mcq.py can score it); the target count is met.
   Fail loudly and name offenders on any violation.
</deliverables>

<action_safety>
Touch ONLY: suite/v1/supergpqa.jsonl, suite/build_v1_supergpqa.py, cli/tests/test_v1_supergpqa_items.py.
Network is for the HuggingFace download only. Do NOT edit suite/v0/, any suite.json, _scoring.py, _suite.py,
mcq.py, any template, anything under web/, or any existing test file.
</action_safety>

<verification_loop>
From cli/: ./.venv/Scripts/python.exe -m pytest tests/test_v1_supergpqa_items.py -q must pass, and the full
suite ./.venv/Scripts/python.exe -m pytest -q must stay green (currently 363). Report both counts.
</verification_loop>

<completeness_contract>
End with a datasheet: exact HF id + revision + a quote of the license field; total vs kept counts; the
filter rules applied + what you could NOT determine; the discipline (and difficulty) distribution of the
kept set; the options-count distribution; 3 sample items (question truncated, options count, gold letter);
anything dropped and why. Do NOT claim the axis is wired or runnable — that is Claude's next step.
</completeness_contract>
