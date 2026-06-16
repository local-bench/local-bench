# Axis Acquisition & Licensing Dossier

**Purpose.** Per-axis dataset acquisition + license dossier for the local-bench scorers.
The orchestrator uses this to write implementation briefs. Research-only — nothing here was
downloaded, cloned, or installed. Every claim cites a canonical URL.

**Verdict legend.**
- **GREEN** — clearly permits commercial use AND redistribution of a derived fixed subset.
- **AMBER** — permits use, but redistribution and/or commercial use is unclear, or it is share-alike (copyleft attaches to our subset).
- **RED** — gated, non-commercial, or no license at all (default copyright → redistribution not permitted; authors may request non-republication).

**Important standing distinction.** For every benchmark there are TWO licenses to track:
(a) the **DATA** (the items we would freeze + serve), and (b) the **SCORER/eval CODE** (which we may vendor or parity-test against). They frequently differ. Where the DATA license is the redistribution-blocking one, that is the governing risk for serving a frozen subset.

_Compiled 2026-06-14._

---

## SuperGPQA

**Verdict: GREEN** — DATA `odc-by` (ODC-BY 1.0, commercial + redistribution OK with attribution); CODE not separately licensed in-repo but eval is trivial to reimplement. Attribution + downstream-source-license compliance required.

1. **Canonical source.**
   - Data: `m-a-p/SuperGPQA` — https://huggingface.co/datasets/m-a-p/SuperGPQA
   - Code: https://github.com/SuperGPQA/SuperGPQA
   - Paper (ByteDance Doubao/Seed + M-A-P): https://arxiv.org/abs/2502.14739 ; blog https://seed.bytedance.com/en/blog/doubao-seed-team-launched-supergpqa-an-open-source-benchmark-test-set-covering-285-disciplines

2. **License.**
   - **(a) DATA:** `odc-by` — "Open Data Commons Attribution License (ODC-BY)". License field on the dataset card reads exactly `odc-by` (https://huggingface.co/datasets/m-a-p/SuperGPQA). ODC-BY permits commercial use and redistribution provided attribution is given. **Caveat the card states explicitly:** the set "is primarily composed of newly created data" but "incorporates a small fraction of transformed content from other datasets" (MMLU-Pro, MedMCQA, etc.) and "you are required to give appropriate credit to the original creators of any third-party data … and comply with the respective licenses of the referenced datasets." → If we freeze a stratified subset we must (i) carry the ODC-BY attribution and (ii) ideally avoid or separately track items transformed from non-redistributable upstreams. **Verdict GREEN with an attribution + upstream-license-hygiene condition.**
   - **(b) CODE:** The repo (https://github.com/SuperGPQA/SuperGPQA) does not surface a top-level LICENSE in the card/repo description checked; eval lives at `eval/eval.py`. Because scoring is plain MCQ-letter matching, vendoring our own scorer (rather than their code) sidesteps any code-license ambiguity. **Flagged: confirm the repo LICENSE before vendoring their `eval/` code; reimplement to be safe.**

3. **Format.** Multiple-choice (MCQ). Item schema fields: `uuid`, `question`, `options` (list), `answer`, `answer_letter`, `discipline`, `field`, `subfield`, `difficulty`, `is_calculation` (https://github.com/SuperGPQA/SuperGPQA). Options are a variable-length list — **4 to 10 options**, answer letters **A through J** (https://huggingface.co/datasets/m-a-p/SuperGPQA). Scoring = **exact match on the MCQ answer letter** (extract the chosen letter from model output, compare to `answer_letter`). The variable option count is a scorer gotcha: the letter-extraction regex must span A–J, not just A–D.

4. **Size + subsetting.** **26,129 items** total (repo-stated; viewer shows ~26.5k), across 285 disciplines / 13 top fields. Field distribution (repo): Science 9,838; Engineering 7,892; Medicine 2,755; Literature&Arts 1,676; Economics 873; History 674; Law 656; Management 501; Agronomy 485; Education 484; Philosophy 347; Military Science 205; Sociology 143. **Frozen stratified subset:** stratify on `field` (and optionally `difficulty`: easy/middle/hard), sample proportionally or with a floor per small field (e.g. Sociology, Military Science) so thin disciplines aren't dropped; pin the HF commit hash for reproducibility (commits at https://huggingface.co/datasets/m-a-p/SuperGPQA/commits/main).

5. **Contamination posture.** **Static** dataset with an explicit construction-time decontamination story rather than a date window. Three-stage "Human-LLM collaborative filtering": >80 expert annotators iteratively refine to "eliminate trivial or ambiguous questions" via LLM-response + expert feedback loops (https://huggingface.co/datasets/m-a-p/SuperGPQA ; arXiv 2502.14739). Items are graduate-level and partly newly authored, lowering pretraining-overlap risk — but because a fraction is transformed from public MCQ sets, **our own pre-serve filter should still screen for items traceable to known-leaked sources** (the brief's "item provenance/contamination filtering before serving" concern). Practical lever: prefer `is_calculation=true` and higher-difficulty items, which are less likely to be memorized verbatim.

6. **Reference scorer.** `eval/eval.py` in https://github.com/SuperGPQA/SuperGPQA (flags `--evaluate_all`, `--excel_output`, `--json_output`). License of that code unconfirmed (see 2b). Scorer logic is simple letter-matching → **recommend vendoring our own, parity-checked against a handful of their outputs**, rather than importing their package.

7. **Gotchas.** No heavy deps, no judge model, no network at eval — pure string/letter matching, Windows-friendly. The two real traps: (i) **A–J letter space** (not A–D) — extraction must handle up to 10 options and the "answer letter vs answer text" distinction; (ii) **attribution + upstream-license hygiene** on the transformed-content fraction.

---

## IFBench

**Verdict: GREEN** — DATA `ODC-BY-1.0`; CODE `Apache-2.0`. Both permit commercial use + redistribution with attribution. One caveat: items contain "output data generated from third-party models … subject to separate terms."

1. **Canonical source.**
   - Code + verifiers: https://github.com/allenai/IFBench
   - Data: `allenai/IFBench_test` — https://huggingface.co/datasets/allenai/IFBench_test (also `allenai/IFBench_multi-turn`, and training set `allenai/IF_multi_constraints_upto5`)
   - Paper "Generalizing Verifiable Instruction Following": https://arxiv.org/abs/2507.02833 (html https://arxiv.org/html/2507.02833v1)

2. **License.**
   - **(a) DATA:** `ODC-BY-1.0`. Card states verbatim: "This dataset is licensed under ODC-BY-1.0. It is intended for research and educational use in accordance with Ai2's Responsible Use Guidelines." (https://huggingface.co/datasets/allenai/IFBench_test). **Caveat (repo README):** "The dataset includes output data generated from third party models that are subject to separate terms governing their use" — relevant if any served prompt text was model-generated; the *constraints themselves* are the IP we care about and are ODC-BY.
   - **(b) CODE:** **Apache-2.0** (repo states code is Apache-2.0, data ODC-BY — https://github.com/allenai/IFBench). This is the important one: the programmatic **constraint verifiers are Apache-2.0**, so we may **vendor them directly**.

3. **Format.** Instruction-following with **programmatic verification** (no judge model). Item schema: `key` (id), `prompt` (string), `instruction_id_list` (list of constraint ids), `kwargs` (list of per-constraint parameter dicts) — same schema family as IFEval (https://huggingface.co/datasets/allenai/IFBench_test). Scoring = **run each constraint's Python verifier against the model response**; report strict (all constraints pass) and loose accuracy, per-instruction and per-prompt — identical methodology to IFEval, extended with new constraints.

4. **Size + subsetting.** `IFBench_test` is small (the test split is on the order of a few hundred rows; the related training/constraint files list 300 rows for one split). IFBench adds **58 new out-of-distribution constraints** (with verifier functions) on top of IFEval's set, plus **29 additional constraints** for IF-RLVR training (https://github.com/allenai/IFBench ; arXiv 2507.02833). **Frozen subset:** because it's already small and each item is a (prompt, constraint-set), freeze the whole `IFBench_test` (and optionally `IFBench_multi-turn`); stratify by `instruction_id` family if you must downsample. Pin the HF commit.

5. **Contamination posture.** **Static**, but designed as **OOD/novel constraints** specifically so models can't have trained on the verifier behaviors — the contribution is "challenging, new" constraints distinct from IFEval. Verification is mechanical, so even if a prompt leaks, the constraint must still be *satisfied*, which is harder to game than MCQ recall. Low contamination concern relative to knowledge benches.

6. **Reference scorer.** Verifiers live **in-repo**: constraint registry at `instructions_registry.py`, verification logic in the evaluation modules (`evaluation_lib.py` and the `eval/` dir) — https://github.com/allenai/IFBench/blob/main/instructions_registry.py . Training-time constraint verifiers are mirrored in `open_instruct/IFEvalG` in AllenAI's open-instruct repo. All **Apache-2.0** → **vendor the registry + verifier functions** and parity-test. (HF `lighteval` also ships an IFBench task at `src/lighteval/tasks/tasks/ifbench/main.py` if a second reference is wanted — https://github.com/huggingface/lighteval.)

7. **Gotchas.** Verifiers pull in NLP helper deps (the IFEval lineage uses `nltk`, `langdetect`, and language/word-frequency resources) — first run may try to **download NLTK corpora** (network); pre-vendor those for an offline box. Some constraints are language-specific (e.g. "Japanese words at intervals") and depend on Unicode handling — test on Windows for encoding edge cases. No judge model required (this is the whole point — purely programmatic), which makes it ideal for local-bench.

---

## LiveCodeBench — Test-Output-Prediction scenario

**Verdict: AMBER** — CODE `MIT` (clean); DATA license is the ambiguity: the HF card declares only `license: cc` (bare "Creative Commons", **variant unspecified**). Cannot confirm commercial-redistribution rights from the card. **Do not guess the variant.**

1. **Canonical source.**
   - Harness: https://github.com/LiveCodeBench/LiveCodeBench
   - Data (this scenario): `livecodebench/test_generation` — https://huggingface.co/datasets/livecodebench/test_generation (pretty_name in card: "LiveCodeBench Test Output Prediction")
   - Project site: https://livecodebench.github.io/ ; paper arXiv 2403.07974 (https://arxiv.org/abs/2403.07974)
   - **Naming gotcha:** the test-**output**-prediction items live in the dataset named `test_generation` (the card's tags are "Test Generation, Test Output Prediction"). The `--scenario` flag value, however, is **`testoutputprediction`** (see 6). Don't confuse with `code_generation` / `code_generation_lite` (those are the codegen scenario).

2. **License.**
   - **(a) DATA:** card YAML is literally `license: cc` (verified raw: https://huggingface.co/datasets/livecodebench/test_generation/raw/main/README.md). "cc" is the generic Creative Commons tag with **no variant** (not CC-BY, not CC0, not CC-BY-NC). The repo README contains **no** data-license statement, and the repo LICENSE applies to code, not data. → **Redistribution + commercial status of a frozen subset is UNRESOLVED.** Note one third-hand search hit suggested the *website repo* (`livecodebench.github.io`) is CC-BY-SA-4.0, but that governs the website, not the benchmark data, and is unconfirmed. **AMBER. Action: open a dataset-card discussion / email the authors to pin the CC variant before redistributing; until then treat as "use locally, do not republish the items."**
   - **(b) CODE:** **MIT** — LICENSE file header reads verbatim "MIT License / Copyright (c) 2024 LiveCodeBench", no non-commercial clause (https://github.com/LiveCodeBench/LiveCodeBench/blob/main/LICENSE). Clean to vendor.

3. **Format.** Execution-FREE scenario. The model is given the problem statement + a test input and must produce the expected output; "outputs are evaluated using an **exact match** checker" (https://livecodebench.github.io/ , project description). No code execution needed (that's why this scenario is attractive for a no-sandbox local bench). Items derive from contest problems; the test_generation card notes **442 instances sampled from 185 LeetCode problems** (text2text-generation task, size `n<1K`).

4. **Size + subsetting.** ~**442 items** in `test_generation` (https://huggingface.co/datasets/livecodebench/test_generation). Small enough to freeze whole. **Date-window subsetting is the native mechanism:** filter on problem `release`/contest date (see 5) to a fixed window so the frozen set is reproducible and post-cutoff for a given model cohort.

5. **Contamination posture.** **Date-windowed** — this is LiveCodeBench's headline feature. Problems carry publication dates; the harness exposes `--start_date` / `--end_date` (YYYY-MM-DD) and versioned releases (`release_v1`…`v6`; v6 = 1055 codegen problems May-2023→Apr-2025) via `--release_version` (https://github.com/LiveCodeBench/LiveCodeBench/blob/main/README.md ; https://huggingface.co/blog/leaderboard-livecodebench). For a contamination-controlled local-bench, **pick a window after the eval-cohort's training cutoff** and pin it. (The test-output-prediction split is smaller and not re-versioned as often as codegen — confirm the date coverage of the 442 items when freezing.)

6. **Reference scorer.** In-harness (MIT): run `python -m lcb_runner.runner.main --model {name} --scenario testoutputprediction --evaluate` (https://github.com/LiveCodeBench/LiveCodeBench/blob/main/README.md). Scoring code path is the exact-match output checker in `lcb_runner`. **Vendor-safe (MIT).** The DATA, separately, is the AMBER item.

7. **Gotchas.** (i) The MIT/`cc` **split-license** is the trap: code is fine to reuse, data republication is not cleared. (ii) Don't pull the wrong dataset — `test_generation` (this scenario) vs `code_generation_lite` (codegen). (iii) Loading via the `livecodebench` package expects HF `datasets` and specific `release_version` tags; some versions require `trust_remote_code`. (iv) Exact-match on stdout is whitespace/format-sensitive — replicate their normalization exactly or scores drift.

---

## RULER (NVIDIA, long-context)

**Verdict: GREEN** — single repo, **Apache-2.0** for both generator code and (synthetic) data. We generate items ourselves, so there is no third-party dataset to redistribute — cleanest of the set.

1. **Canonical source.** https://github.com/NVIDIA/RULER (README: https://github.com/NVIDIA/RULER/blob/main/README.md). Paper "RULER: What's the Real Context Size of Your Long-Context Language Models?" — https://openreview.net/pdf?id=kIoBbc76Sy . RULER is a **synthetic generator**, not a fixed HF dataset.

2. **License.** **Apache-2.0**, confirmed from the LICENSE file header verbatim "Apache License / Version 2.0, January 2004" (https://github.com/NVIDIA/RULER/blob/main/LICENSE). Applies to the generation code; because items are **synthesized locally** from that code (no copyrighted corpus shipped as the answer key beyond optional public QA sources), the data we produce is ours to serve. **(a) DATA = GREEN (we generate it). (b) CODE = Apache-2.0 GREEN.**

3. **Format.** 13 tasks across **4 categories** (https://github.com/NVIDIA/RULER/blob/main/README.md):
   - **Retrieval (NIAH family):** Single NIAH, Multi-key NIAH, Multi-value NIAH, Multi-query NIAH (key-value "needles" inserted into a "haystack").
   - **Multi-hop tracing:** Variable Tracking (chase variable-assignment chains).
   - **Aggregation:** Common-Words Extraction, Frequent-Words Extraction.
   - **Question Answering:** QA over long context built on SQuAD / HotpotQA passages.
   Scoring is **recall / string-match based**: e.g. NIAH and variable-tracking are scored by whether the target string(s) (the needle value(s) / traced variables) appear in the output — effectively recall@expected-tokens / partial-match accuracy rather than a single exact-match boolean. Aggregation tasks check the set of extracted words. (Verify exact match-vs-recall per task in `scripts/eval` when implementing — RULER computes a per-task partial-credit recall.)

4. **Size + subsetting.** Item count is **whatever you generate** (`num_samples` per task). To build a frozen 32k-context set: configure the synthetic data prep under `scripts/data/synthetic/` with the target sequence length and your tokenizer/model template, generate N samples per task, then **persist the generated jsonl + the generator config + RNG seed** as the frozen artifact (so it's reproducible without re-running). The README's `run.sh MODEL synthetic` path wraps prep+predict+eval; for local-bench, decouple the *prepare* step, freeze its output, and serve that.

5. **Contamination posture.** **Generator-based / synthetic** → inherently low contamination: needles, keys, distractor word-lists and variable chains are randomized at generation time, so there is no static item to leak. This is the strongest contamination posture in the suite. Only the QA sub-tasks reuse public passages (SQuAD/HotpotQA) and could in principle overlap pretraining — prefer the NIAH/variable-tracking/aggregation tasks if maximal cleanliness is wanted.

6. **Reference scorer.** In-repo, Apache-2.0: data prep in `scripts/data/` (per-task generators, e.g. `niah`, `variable_tracking`, `common_words_extraction`), evaluation in `scripts/eval/`. Vendor freely.

7. **Gotchas.** (i) **Generation needs a tokenizer/model template** to hit an exact token length and to format prompts — the length parameter is in *tokens*, so the served context length depends on the target model's tokenizer (a 32k set built with one tokenizer isn't exactly 32k for another). (ii) Deps include word/name generators (`wonderwords`) and `nltk`-style resources + HF `datasets` for the QA passages → first run may **download corpora** (pre-vendor for offline). (iii) The repo's end-to-end path historically assumes a Linux/Docker + an inference server (vLLM/TRT-LLM); on Windows, **use only the data-generation + scoring modules** (pure Python) and drive inference through your own local-bench harness rather than their `run.sh`.

---

## BFCL (Berkeley Function-Calling Leaderboard) + ToolHop

### BFCL

**Verdict: GREEN** — DATA and CODE both **Apache-2.0** (gorilla repo + `bfcl-eval` PyPI). AST-based, execution-free for the AST categories. Cleanest agentic option.

1. **Canonical source.**
   - Code (in gorilla monorepo): https://github.com/ShishirPatil/gorilla — subdir `berkeley-function-call-leaderboard/` (README https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/README.md ; data dir `bfcl_eval/data` https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard/bfcl_eval/data).
   - PyPI: `bfcl-eval` — https://pypi.org/project/bfcl-eval/ (current ~`2026.3.23`).
   - Data mirror: `gorilla-llm/Berkeley-Function-Calling-Leaderboard` — https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard
   - Paper (ICML 2025): https://proceedings.mlr.press/v267/patil25a.html

2. **License.**
   - **(a) DATA:** **Apache-2.0** (HF dataset card for `gorilla-llm/Berkeley-Function-Calling-Leaderboard`; gorilla project releases models + data under Apache-2.0 — https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard).
   - **(b) CODE:** **Apache-2.0** — gorilla repo LICENSE header "Apache License / Version 2.0" (https://github.com/ShishirPatil/gorilla/blob/main/LICENSE); `bfcl-eval` PyPI metadata states "License: Apache 2.0" (https://pypi.org/project/bfcl-eval/). Both data and scorer are vendor-safe. **GREEN.**

3. **Format.** Function/tool-calling. An item provides a user query + one or more **function/tool schemas** (JSON: name, description, parameters with types); the model must emit the correct call(s). Scoring uses **AST matching, not execution** for the core categories: the predicted call is parsed into an abstract syntax tree and structurally compared to the reference (function name match + required params present + argument types/values within allowed sets), which "looks at the structure of each tool call rather than running every tool for real" and scales to thousands of functions (https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/README.md). Categories include simple / parallel / multiple / parallel-multiple (AST-scored), plus **executable** and **multi-turn/agentic** categories (V3/V4) that do run code or simulate state. **For a no-sandbox local-bench, use the AST categories** (simple_python, parallel, multiple, parallel_multiple) and skip the executable ones.

4. **Size + subsetting.** Several thousand items partitioned by category (each category is its own file in `bfcl_eval/data`). **Frozen subset:** pick the AST-scored categories, take all (or a stratified sample across categories), and pin the `bfcl-eval` version (the data evolves V1→V4, so **freeze a version tag** for reproducibility).

5. **Contamination posture.** **Static**, versioned (V1→V4 add categories/scenarios over time). Tool-calling correctness is structural, so verbatim memorization helps less than on QA; still, pin a version and prefer the newer categories for freshness. No date-window mechanism.

6. **Reference scorer.** `bfcl-eval` (PyPI, Apache-2.0) bundles **both the datasets and the AST evaluation code** + model handlers (https://pypi.org/project/bfcl-eval/). For local-bench we can either `pip install bfcl-eval` and call its AST checker, or **vendor the AST-match functions** from `bfcl_eval`. Set `BFCL_PROJECT_ROOT` if installed from PyPI (results path).

7. **Gotchas.** (i) Package requires **Python ≥3.10**. (ii) Heavy optional extras (`oss-eval-vllm`, `oss-eval-sglang`, `wandb`) and **web_search / executable / multi-turn categories require network or live tool execution** — exclude them for an offline AST-only run. (iii) Don't `pip install bfcl` (a different, unrelated PyPI project) — the correct name is **`bfcl-eval`**. (iv) AST scoring has subtle "possible_answers" allow-sets per argument — replicate their matcher rather than rolling a naive equality check.

### ToolHop

**Verdict: GREEN** — DATA **CC BY 4.0**; CODE **Apache-2.0**. Locally executable tools → can run non-networked in-process. Commercial + redistribution OK with attribution.

1. **Canonical source.** `bytedance-research/ToolHop` — https://huggingface.co/datasets/bytedance-research/ToolHop (model/code mirror https://huggingface.co/bytedance-research/ToolHop). Paper "ToolHop: A Query-Driven Benchmark for Evaluating LLMs in Multi-Hop Tool Use" (Fudan + ByteDance, ACL 2025) — https://arxiv.org/abs/2501.02506 ; https://aclanthology.org/2025.acl-long.150/

2. **License.**
   - **(a) DATA:** **CC BY 4.0** (dataset card — https://huggingface.co/datasets/bytedance-research/ToolHop). Attribution required; commercial + redistribution permitted.
   - **(b) CODE:** **Apache-2.0** (card states code is Apache-2.0). **GREEN.**

3. **Format.** Multi-hop tool use. Each item = a user query + a set of associated tool definitions whose outputs feed subsequent calls (interdependent), with **locally executable tool implementations** and **verifiable answers**. Scoring is **answer-correctness** (final-answer accuracy) over the multi-hop chain (leading model GPT-4o ≈ 49.04%, indicating headroom) (https://arxiv.org/html/2501.02506v2). Exact per-field schema isn't fully enumerated on the card (viewer needs custom config), so **inspect the jsonl schema on first acquisition**.

4. **Size + subsetting.** **995 user queries** with **3,912 tools** (https://arxiv.org/abs/2501.02506). Small — freeze whole, or stratify by hop-count if you want a difficulty gradient.

5. **Contamination posture.** **Static**, constructed via a query-driven pipeline (tool creation → document refinement → code generation). Newer (Jan 2025) and tool-execution-grounded, so lower memorization risk than old QA sets; no date window.

6. **Reference scorer.** Ships with the dataset/code release (Apache-2.0). Because tools are **locally executable**, evaluation runs **in-process, non-networked** — no external API calls — which is exactly what we want for an offline agentic axis. Vendor the executor + answer-checker.

7. **Gotchas.** (i) "Locally executable tools" means the harness **executes generated/packaged Python tool code** — sandbox it (untrusted-code-execution surface), even though it doesn't hit the network. (ii) Schema/field names aren't documented on the card → confirm by reading the jsonl. (iii) Multi-hop answer-matching may need normalization (numbers/strings) — replicate their checker.

---

## ZebraLogic and AutoLogi (logic / CSP)

### ZebraLogic

**Verdict: AMBER** — eval CODE is clean (`WildEval/ZeroEval`, **Apache-2.0**), but the canonical AllenAI DATA card declares **no `license:` field at all**, and a separate **`-private` gated** variant exists. Redistribution rights for the items are unconfirmed. **Do not assume a license.**

1. **Canonical source.**
   - Data (public): `allenai/ZebraLogicBench` — https://huggingface.co/datasets/allenai/ZebraLogicBench (also `WildEval/ZebraLogic`; AllenAI collection https://huggingface.co/collections/allenai/zebra-logic-bench-6697137cbaad0b91e635e7b0).
   - **Gated variant:** `allenai/ZebraLogicBench-private` exists as a separate repo (surfaced in HF search) — confirms a gated copy is in play.
   - Eval code: `WildEval/ZeroEval` — https://github.com/WildEval/ZeroEval (a.k.a. `yuchenlin/ZeroEval`). Paper "ZebraLogic: On the Scaling Limits of LLMs for Logical Reasoning" arXiv 2502.01100 (https://arxiv.org/abs/2502.01100); leaderboard space https://huggingface.co/spaces/allenai/ZebraLogic.

2. **License.**
   - **(a) DATA:** **UNSPECIFIED.** The `allenai/ZebraLogicBench` card README has **no YAML `license:` field** (verified raw: https://huggingface.co/datasets/allenai/ZebraLogicBench/raw/main/README.md — front matter begins at `dataset_info:` with no license key) and no license name renders on the card. Combined with the existence of a `-private` gated mirror, **redistribution of a frozen subset is NOT cleared.** **AMBER (leaning RED for republication).** Action: confirm with authors / check the gated variant's terms before serving the items publicly; safe interim posture = generate/serve locally, don't redistribute.
   - **(b) CODE:** **Apache-2.0** — `WildEval/ZeroEval` About sidebar shows "Apache-2.0 license" (https://github.com/WildEval/ZeroEval). Scorer is vendor-safe.

3. **Format.** Logic-grid (Zebra) puzzles from CSPs. Two configs (https://huggingface.co/datasets/allenai/ZebraLogicBench): `grid_mode` (1,000 rows — fill the full solution table) and `mc_mode` (3,260 rows — multiple choice). grid_mode fields: `id`, `size` (e.g. "5*6"), `puzzle` (text + constraints), `solution` (answer table), `created_at`. **Scoring (grid_mode)** = parse the model's JSON solution and compare cell-by-cell to ground truth: **puzzle-level exact match** (solved only if every cell correct: `if this_correct_cells == this_total_cells: solved_puzzles += 1`) **plus cell-level accuracy** (`Cell Acc = correct_cells/total_cells*100`); cells normalized via `.lower().strip()` (https://github.com/WildEval/ZeroEval/blob/main/src/evaluation/zebra_grid_eval.py). mc_mode = MCQ exact-match.

4. **Size + subsetting.** 1,000 (grid) + 3,260 (mc) = **4,260 items**. **Frozen subset:** for a reasoning axis use `grid_mode`; stratify on `size` (grid dimensions = difficulty proxy, e.g. 2×2 … 6×6) to get a clean difficulty curve; pin the commit. (Scoring needs robust JSON extraction from model output — `extract_last_complete_json` in their code.)

5. **Contamination posture.** **Static**, CSP-derived. Puzzles are procedurally constructed across a complexity range; the strict full-grid exact-match makes shallow memorization unlikely to suffice. But because items are static and widely circulated, treat as moderate contamination risk and consider regenerating fresh puzzles (the construction is CSP-based) if maximal cleanliness is wanted. (Note: the brief's "ZebraLogic repo license — verify it exists" → the **dataset** repo has no license field; the **eval** repo is Apache-2.0.)

6. **Reference scorer.** `src/evaluation/zebra_grid_eval.py` in `WildEval/ZeroEval` (Apache-2.0); task id `zebra-grid` (`-d zebra-grid`). Vendor freely.

7. **Gotchas.** (i) **Data license gap** is the blocker for redistribution (see 2a). (ii) Scoring depends on the model emitting parseable JSON grids — brittle for small models that format poorly; the harness's JSON-repair/extraction must be replicated or scores false-floor. (iii) The `-private` variant means the public copy may be a subset — don't mix sources.

### AutoLogi

**Verdict: RED** — **NO LICENSE FILE** in the canonical repo (`8188zq/AutoLogi`). Default copyright ⇒ redistribution NOT permitted and commercial use undefined. The CC-BY-SA mentioned in the brief is **only the arXiv submission's listing**, which does NOT grant a license over the repo's data/code. **This is the single biggest licensing risk in the suite.**

1. **Canonical source.** Repo: https://github.com/8188zq/AutoLogi (contains dataset, synthesis methods, program-based verifiers, eval). Paper "AutoLogi: Automated Generation of Logic Puzzles for Evaluating Reasoning Abilities of LLMs" arXiv 2502.16906 (https://arxiv.org/abs/2502.16906 ; html https://arxiv.org/html/2502.16906v1). Alibaba-affiliated.

2. **License.**
   - **(a) DATA:** **NONE DECLARED.** The repo root has **no LICENSE file** — directory listing shows only `eval_results/`, `evaluation/`, `model_output/`, `pic/`, `synthesize/`, `testing-data/`, `training-data/`, `README.md`, and the GitHub "About" sidebar shows **no license** ("No description, website, or topics provided") (https://github.com/8188zq/AutoLogi ; the `/blob/main/LICENSE` path returns **HTTP 404**). Under default copyright, **all rights reserved** → we may not redistribute a derived subset; commercial use is not granted. The arXiv abstract page may list a CC license for the **paper/preprint**, but that license **does not extend to the GitHub data/code** — the brief's caution is correct, and the actual repo confirms the worst case. **RED.**
   - **(b) CODE:** Same — **no license** on the program-based verifiers either. Vendoring their verifier code is **not cleared**.

3. **Format.** Open-ended (not MCQ) bilingual logic puzzles with **program-based verifiers** (the eval ships executable checkers rather than reference answers) — the design point is that AutoLogi auto-synthesizes puzzles + a verifier per puzzle, scoring by running the verifier on the model's answer (constraint satisfaction → pass/fail). Performance range 35–73% across 8 LLMs vs 21–37% on the source MCQ set (https://arxiv.org/html/2502.16906v1).

4. **Size + subsetting.** Provided as `testing-data/` and `training-data/` in-repo plus a **synthesis pipeline** (`synthesize/`) to generate more. Item counts per the paper/repo (confirm on acquisition). **Because the static data is unlicensed, the only clean path is to re-generate puzzles ourselves using the *method*** (re-implementing the synthesis described in the paper) rather than redistributing their `testing-data/` — but even the synthesize code is unlicensed, so a from-scratch reimplementation from the paper would be required to be safe.

5. **Contamination posture.** **Generator-based** (auto-synthesis) — good in principle for freshness, but moot until the licensing is resolved.

6. **Reference scorer.** Program-based verifiers under `evaluation/` in https://github.com/8188zq/AutoLogi — **unlicensed; do not vendor.** Parity-testing against it is also legally murky; prefer a clean-room reimplementation if AutoLogi is pursued.

7. **Gotchas.** (i) **No license = hard stop for our use case** (we need redistribution of a fixed subset). (ii) Verifiers execute code (sandbox needed). (iii) Single-maintainer personal repo (`8188zq`) → license could appear later; **the action is to open an issue asking the authors to add an explicit license** before any adoption. Until then, **exclude AutoLogi from the redistributable suite.**

---

## Summary table

| Benchmark | Data license | Code (scorer) license | Verdict | Scorer type |
|---|---|---|---|---|
| **SuperGPQA** | ODC-BY 1.0 (`odc-by`) — attribution; upstream-fraction hygiene | Repo LICENSE unconfirmed (reimplement) | **GREEN** (attribution + upstream caveat) | MCQ exact-match on answer letter (A–J) |
| **IFBench** | ODC-BY-1.0 | Apache-2.0 (verifiers in-repo) | **GREEN** | Programmatic constraint verifiers (no judge) |
| **LiveCodeBench (test-output-pred)** | `cc` — **CC variant unspecified** on card; no data-license statement | MIT (harness) | **AMBER** | Exact-match on predicted stdout (exec-free) |
| **RULER** | Apache-2.0 (self-generated synthetic) | Apache-2.0 | **GREEN** | Recall / string-match per task (synthetic) |
| **BFCL** | Apache-2.0 | Apache-2.0 (`bfcl-eval` PyPI) | **GREEN** | AST structural match of tool calls (exec-free for AST cats) |
| **ToolHop** | CC BY 4.0 | Apache-2.0 | **GREEN** | Final-answer correctness over multi-hop (locally executable, in-process) |
| **ZebraLogic** | **UNSPECIFIED** (no `license:` field; `-private` gated variant exists) | Apache-2.0 (`WildEval/ZeroEval`) | **AMBER** (lean RED for republication) | Grid exact-match (puzzle-level) + cell-level accuracy |
| **AutoLogi** | **NONE** (no LICENSE file in repo; arXiv CC ≠ repo) | NONE (verifiers unlicensed) | **RED** | Program-based verifier (CSP pass/fail) |

### Cross-cutting notes
- **Split-license pattern is the norm:** code is usually permissive (Apache/MIT) even where data is not. The redistribution-blocking license is almost always the **DATA** one.
- **Safe-to-vendor scorer code:** IFBench (Apache), RULER (Apache), BFCL/`bfcl-eval` (Apache), ZeroEval/ZebraLogic (Apache), LiveCodeBench harness (MIT). **Not safe:** AutoLogi (unlicensed); SuperGPQA `eval/` (unconfirmed — reimplement).
- **Generate-don't-redistribute escape hatch:** RULER (synthetic) is fully clean this way; ZebraLogic and AutoLogi are CSP/auto-generated in principle, so a clean-room generator sidesteps their data-license gaps if those axes are wanted.
- **Pin commit hashes / version tags** for every adopted set (HF dataset revision; `bfcl-eval` version; LiveCodeBench release_version + date window) so the frozen subset is reproducible.
