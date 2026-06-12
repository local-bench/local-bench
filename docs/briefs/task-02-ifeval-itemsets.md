<task>
Second slice for local-bench: vendor the official IFEval checkers and build the frozen
suite-v0 item sets. Work ONLY in this repo. The cli/ package from task-01 exists (runner +
mcq/math scorers); do not modify it except where stated.

1. Vendor IFEval checkers (Apache 2.0):
   - Source: the official google-research instruction_following_eval implementation
     (github.com/google-research/google-research/tree/master/instruction_following_eval).
     If network fetch is blocked, recreate the checker registry faithfully for the
     instruction types present in the google/IFEval HF dataset (instruction_id_list values)
     — exact behavioral parity matters more than file-identical copies; mark any
     reimplemented checker with a comment.
   - Destination: cli/src/localbench/scorers/ifeval/ — keep Apache-2.0 license headers,
     add LICENSES/Apache-2.0.txt at repo root and a NOTICE file crediting both datasets
     (MMLU-Pro MIT, IFEval Apache-2.0).
   - Expose: score_ifeval(prompt_item, response_text) -> {follow_all: bool,
     per_instruction: [bool], strict: bool result} (strict mode only for v0).
   - Tests: cli/tests/test_ifeval.py — for at least 8 distinct instruction types
     (e.g. exact paragraph count, forbidden words, all-caps frequency, json format,
     postscript, title brackets, word count bounds, bullet count): one passing and one
     failing response each, hand-written.

2. Item-set builder: suite/build_itemsets.py (standalone script, run with the cli venv):
   - Downloads TIGER-Lab/MMLU-Pro (test split) and google/IFEval via Hugging Face
     `datasets` (add as a dev/build dependency only — NOT a runtime dep of localbench)
     or direct parquet HTTP; cache under data/cache/ (gitignored).
   - MMLU-Pro stratified fixed subsets, seed=20260612, sampled per category:
     standard = 20 per category × 14 = 280 items; quick = 8 per category = 112 items
     (quick ⊂ standard where possible: sample quick from the standard set).
     Fields kept: question_id, category, question, options (list), answer (letter),
     answer_index. Drop cot_content.
   - IFEval subsets: standard = 250 prompts, quick = 100 (quick ⊂ standard), seed as above,
     uniform random; keep key, prompt, instruction_id_list, kwargs verbatim (checkers
     need them).
   - Output: suite/v0/mmlu_pro_standard.jsonl, mmlu_pro_quick.jsonl,
     ifeval_standard.jsonl, ifeval_quick.jsonl — one JSON object per line, sorted by id,
     COMMITTED to the repo (licenses permit; that is the point of a frozen suite).
   - Also write suite/v0/itemsets.lock.json: per file — item count, sha256 of file bytes,
     source dataset + revision/commit if available, seed, build timestamp.
   - Builder must be deterministic: same seed + same source revision → identical files.

3. Prompt templates: suite/v0/templates/mcq_cot.txt and ifeval.txt:
   - mcq_cot.txt: zero-shot chain-of-thought MCQ template — system-free single user
     message containing the question + lettered options + the exact instruction:
     "Think step by step, then give your final answer as a single line: Answer: <letter>".
   - ifeval.txt: the raw IFEval prompt verbatim (no wrapper — the dataset prompt IS the
     instruction).
   - suite/v0/suite.json: machine-readable suite spec — benches, item-set files + hashes,
     template files, decoding policy per bench (mcq: greedy temp 0, max_tokens 2048;
     ifeval: greedy temp 0, max_tokens 1280), chance-correction baseline per bench
     (mmlu_pro: 0.10; ifeval: 0.0), and lane caps placeholder.
</task>

<action_safety>
Touch only: cli/src/localbench/scorers/ifeval/, cli/tests/test_ifeval.py, suite/,
LICENSES/, NOTICE. Do not modify runner.py, mcq.py, math_numeric.py, pyproject beyond
adding the build/dev dependency, or repo-root README/.gitignore. No git commands.
</action_safety>

<completeness_contract>
Done = (a) pytest green including new IFEval tests via cli/.venv python; (b) running
`cli/.venv/Scripts/python suite/build_itemsets.py` produces the four JSONL files + lock
file with counts 280/112/250/100 and stable hashes on a second run; (c) LICENSES/NOTICE
present.
</completeness_contract>

<verification_loop>
Run the builder twice and diff outputs to prove determinism; run pytest; fix before
finishing. If network is blocked for dataset download, implement + unit-test the sampling
logic against a small inline fixture, and report exactly what the manager must run.
</verification_loop>

<missing_context_gating>
No questions; choose sensibly and note choices.
</missing_context_gating>

<compact_output_contract>
Final message: (1) files created/modified, (2) pytest line + builder determinism check
result, (3) item counts + lock hashes, (4) <=8 bullets decisions/deferred.
</compact_output_contract>
