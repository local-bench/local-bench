<task>
Acquire the suite-v1 MATH datasets (AMO-Bench and OlymMATH-HARD) and turn them into frozen
localbench item files + a reproducible build script. This is the DATA layer for the olympiad math
axis whose scorer (cli/src/localbench/scorers/math_symbolic.py, function verify_math) already exists
and is committed.

Repo root: C:/Users/Michael/local-bench (your cwd). Python venv: cli/.venv
(use ./.venv/Scripts/python.exe from the cli/ dir). The `datasets` (HuggingFace) library is installed.
</task>

<context>
- localbench item schema — MATCH the existing suite/v0/genmath_*.jsonl exactly: one JSON object per
  line: {"id": "<stable unique id>", "statement": "<full problem text>", "answer": "<final answer>"}.
  `answer` must be the FINAL answer (a number or LaTeX/symbolic expression), NOT a proof or worked
  solution.
- The scorer that grades these (cli/src/localbench/scorers/math_symbolic.py):
    verify_math(response_text, gold) -> bool   # extracts the answer from response_text, then checks
                                               # mathematical equivalence to gold (LaTeX/symbolic OK)
  So every item's `answer` must be a form verify_math can parse and self-verify.
- These belong to suite-v1 (a NEW frozen suite). Put files under suite/v1/. Do NOT touch suite/v0/.
- Do NOT create or edit any suite.json, and do NOT edit cli/src/localbench/_scoring.py or _suite.py
  — the manager (Claude) owns the suite-v1 manifest + dispatch wiring. You produce ITEM FILES + a
  build script + a test + a datasheet ONLY.
</context>

<deliverables>
1. Locate the CANONICAL HuggingFace dataset for each and confirm the license is MIT (or clearly
   permissive + redistributable). If you cannot confirm a clean canonical source for one, STOP for
   that dataset and report it — do NOT grab an unverified mirror or a license-unclear copy.
     - AMO-Bench (advanced mathematical olympiad benchmark; ~39 problems).
     - OlymMATH, the HARD subset, English split (~100 problems).
2. suite/v1/amo.jsonl and suite/v1/olymmath_hard.jsonl — transformed item files in the schema above.
   Stable ids ("amo-001", "olymmath-hard-001", ...). statement = problem text. answer = the dataset's
   final/gold answer normalized to a single final expression (extract the boxed/final answer if the
   source stores a fuller solution).
3. suite/build_v1_math.py — a reproducible script that regenerates those two jsonl files from the
   pinned HF sources. Record the dataset id + revision/commit hash in the script. Re-running it must
   reproduce the committed jsonl byte-for-byte. (Look at suite/build_itemsets.py for house style.)
4. cli/tests/test_v1_math_items.py — asserts: each file loads as JSONL, every row matches the schema,
   ids are unique, AND the self-consistency GATE: for every item,
   verify_math(f"Final answer: {item['answer']}", item['answer']) is True (our scorer can parse +
   verify the gold). If ANY gold fails to self-verify, the test FAILS and names the offending id —
   do not silently drop it.
</deliverables>

<action_safety>
Touch ONLY: suite/v1/amo.jsonl, suite/v1/olymmath_hard.jsonl, suite/build_v1_math.py,
cli/tests/test_v1_math_items.py (create the suite/v1/ directory as needed). Network access is for the
HuggingFace dataset download ONLY. DO NOT edit suite/v0/, any suite.json, _scoring.py, _suite.py,
math_symbolic.py, math_numeric.py, anything under web/, or any existing test file.
</action_safety>

<verification_loop>
From cli/: ./.venv/Scripts/python.exe -m pytest tests/test_v1_math_items.py -q must pass, and the full
suite ./.venv/Scripts/python.exe -m pytest -q must stay green (currently 356). Report both counts.
</verification_loop>

<completeness_contract>
End with a datasheet (plain text):
- Exact HF dataset id + revision used for each, and the confirmed license (quote the license field).
- Item counts per file.
- Answer-type distribution (integer / decimal / fraction / symbolic / set-or-interval counts).
- Self-verify gate result: X/Y golds self-verify; list any that do NOT (those are scorer gaps to fix).
- 3 sample (statement-truncated, answer) pairs per file.
- Anything dropped or normalized, and why.
Do NOT claim the math axis is wired or runnable — wiring is Claude's next step.
</completeness_contract>
