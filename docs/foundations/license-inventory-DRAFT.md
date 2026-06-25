# License & Redistribution Inventory — DRAFT v1

> **STATUS: DRAFT — PENDING OWNER REVIEW + LEGAL REVIEW.**
> This is a working inventory produced for the owner's review, not a legal opinion and
> not a final compliance sign-off. Every "license" cell is sourced from evidence already
> in this repo (license files, machine-written lock files, build-script assertions) or
> from well-known public licensing; where the in-repo evidence is only an author
> assertion (a hardcoded constant, not a build-time check against the live source card)
> the row is marked **UNVERIFIED — owner to confirm**. Do not rely on this document for a
> public release until a human has verified each upstream license against its current
> source and a real legal pass is done.
>
> **Author:** automated draft pass, 2026-06-25. Supersedes nothing; sits alongside the
> earlier `license-inventory-v1.md` (which this draft *corrects* on IFBench — see
> "Conflicts found" below).

---

## 0. How to read this / evidence tiers

Each dataset's license is graded by how strongly it is evidenced **inside this repo**:

- **VERIFIED (build-gated):** the suite build script calls a `_require_license()` check
  that downloads the upstream Hugging Face dataset card at build time and *fails the
  build* if the card's license != the expected string. This is the strongest in-repo
  evidence — the recorded license could not have been written unless the live source
  card agreed at build time. Still "owner to confirm the card hasn't changed since," but
  high-confidence.
- **VERIFIED (license text in repo):** a full upstream license text file is committed in
  `LICENSES/` and the dataset's lock/notice consistently records the same license.
- **AUTHOR-ASSERTED (UNVERIFIED):** the license is only a hardcoded constant in the build
  script / lock file (no build-time card check). Consistent across repo artifacts, and
  matches each project's well-known public licensing, but not independently re-checked
  against the live source here. Owner/legal should confirm against the current source.

**Two distribution surfaces exist — they are not the same and the distinction is
load-bearing:**

| Surface | What ships | Who receives it |
|---|---|---|
| **A. Public CLI wheel** (`pipx install localbench`) | The **packaged** suite `cli/src/localbench/data/suites/core-text-v1/` → **only MMLU-Pro (400) + IFBench (294)** item sets, plus their NOTICE / ATTRIBUTION / LICENSES. Declared as `package-data` in `cli/pyproject.toml`. | Anyone who installs the CLI. **This is real public redistribution of item text.** |
| **B. Source repo** `suite/v1/*.jsonl` | All 9 datasets (MMLU-Pro, IFBench, AMO, OlymMATH, SuperGPQA, BFCL, BFCL-multi-turn, LCB, RULER, BigCodeBench-Hard) — git-tracked. | Currently **no git remote / never pushed** (per anonymity-audit-v1.md). Only matters if the repo is ever published or these files are served. |
| **C. Published web site** `web/out/` | **No benchmark items.** Scores + metadata only. | Public site visitors. Not a dataset-redistribution surface. |

> Earlier docs framed the items as "private-repo artefact only." That is true for
> surface B, but **surface A (the wheel) already redistributes MMLU-Pro + IFBench item
> text to the public** the moment the CLI is published to PyPI. Treat MMLU-Pro and
> IFBench attribution as already-public obligations, not future ones.

I confirmed item **text is redistributed verbatim** (not references/derived only): the
shipped `mmlu_pro.jsonl` contains full question + answer-option text; `ifbench.jsonl`
contains full prompt text. Line counts match the lock (400 / 294).

---

## 1. Dataset inventory

Columns: **Dataset** | **What's redistributed** | **Upstream + URL** | **License (evidence tier)** | **Required attribution** | **Where it lives in repo**

### 1.1 MMLU-Pro  — *shipped in public wheel (surface A)*

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 400 questions + options, sampled from the 12,032-item test split. |
| Upstream | `TIGER-Lab/MMLU-Pro` — https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro (rev `b189ec765aa7ed75c8acfea42df31fdae71f97be`) |
| License | **MIT — VERIFIED (build-gated).** `suite/build_v1_mmlu_pro.py` `EXPECTED_LICENSE="mit"` enforced by `_require_license()` against the live HF card; full MIT text committed at `LICENSES/MMLU-Pro-MIT.txt` and `cli/.../core-text-v1/LICENSES/MMLU-Pro-MIT`. |
| Required attribution | MIT: retain copyright + permission notice in distributions. Credit TIGER-Lab. |
| Where in repo | `suite/v1/mmlu_pro.jsonl`; **`cli/src/localbench/data/suites/core-text-v1/mmlu_pro.jsonl` (public wheel)**; release bundle `release/suites/core-text-v1/<hash>/`. |

### 1.2 IFBench  — *shipped in public wheel (surface A)* — ⚠ corrects prior doc

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 294 prompts (293 effective; `words:start_verb` excluded). Plus **vendored verifier code** adapted from upstream IFBench/IFEval — see §2. |
| Upstream | `allenai/IFBench_test` — https://huggingface.co/datasets/allenai/IFBench_test (rev `2e8a48de45ff3bf41242f927254ca81b59ca3ae2`); code https://github.com/allenai/IFBench |
| License | **DATASET: ODC-BY-1.0 — VERIFIED (license text in repo + 5 consistent machine artifacts).** Full ODC-BY-1.0 text committed at `LICENSES/IFBench-ODC-BY-1.0.txt` and `cli/.../core-text-v1/LICENSES/IFBench-ODC-BY-1.0`. The scorer NOTICE quotes the upstream card verbatim: *"This dataset is licensed under ODC-BY-1.0…"* **VERIFIER CODE: Apache-2.0** (separate; upstream IFBench repo LICENSE). |
| Required attribution | ODC-BY-1.0: attribution required for any public use / database distribution — credit `allenai/IFBench_test`. **Plus two upstream caveats that travel with the data:** (a) use per **Ai2 Responsible Use Guidelines**; (b) dataset **includes output generated from third-party models subject to separate terms**. Apache-2.0 for the vendored verifier code (retain notices). |
| Where in repo | `suite/v1/ifbench.jsonl`; **`cli/.../core-text-v1/ifbench.jsonl` (public wheel)**; release bundle. Verifier code: `cli/src/localbench/scorers/ifbench/` (+ its `NOTICE`). |
| ⚠ CONFLICT | The older `license-inventory-v1.md` §1.2 labels IFBench **Apache-2.0** ("confirmed by HuggingFace card"). **That is wrong for the dataset.** Every current machine artifact (lock files, `suite.json` `license_manifest`, bundle NOTICE/ATTRIBUTION, committed license text, scorer NOTICE quoting the card) says the **dataset is ODC-BY-1.0**; Apache-2.0 applies only to the IFBench/IFEval verifier *code*. The repo-root NOTICE and the wheel were already corrected to ODC-BY-1.0 (per anonymity-license-sweep-2026-06-23.md). **Action: retire / correct the Apache-2.0 line in `license-inventory-v1.md` so the two inventories don't disagree.** |

### 1.3 AMO-Bench (Olympiad math)  — repo only (surface B)

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 39 of 50 (dropped "description" answer type). |
| Upstream | `meituan-longcat/AMO-Bench` — https://huggingface.co/datasets/meituan-longcat/AMO-Bench (rev `2f422616c25d862984408fbbfaed63a961e8e025`) |
| License | **MIT — VERIFIED (build-gated).** `suite/build_v1_math.py` `AMO_LICENSE="mit"` enforced by `_require_license(AMO_REPO, …)`. **Note:** no full MIT text travels with this file in `suite/v1/` (it is not in the public wheel), and the top-level `suite/v1/itemsets.lock.json` does **not** record a `license` key for `amo.jsonl` (the assertion lives in the build script, not the lock). |
| Required attribution | MIT: retain copyright notice. Credit meituan-longcat/AMO-Bench. |
| Where in repo | `suite/v1/amo.jsonl`. Not in public wheel. |

### 1.4 OlymMATH-Hard  — repo only (surface B)

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 100 (en-hard config). |
| Upstream | `RUC-AIBOX/OlymMATH` — https://huggingface.co/datasets/RUC-AIBOX/OlymMATH (rev `2c6532ea2cf929ac1c421532af5951553eaee727`) |
| License | **MIT — VERIFIED (build-gated).** `suite/build_v1_math.py` `OLYMMATH_LICENSE="mit"` enforced by `_require_license(OLYMMATH_REPO, …)`. Same caveat as AMO: no `license` key in `suite/v1/itemsets.lock.json` for this file. |
| Required attribution | MIT: retain copyright notice. Credit RUC-AIBOX/OlymMATH. |
| Where in repo | `suite/v1/olymmath_hard.jsonl`. Not in public wheel. |

### 1.5 SuperGPQA  — repo only (surface B)

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** sampled subset (build validates against 26,529 source rows). Legacy bench; not in the v1.2 headline composite. |
| Upstream | `m-a-p/SuperGPQA` — https://huggingface.co/datasets/m-a-p/SuperGPQA (rev `4430d4458112c7d4497fdcf94d7cc223313d6acf`) |
| License | **ODC-BY-1.0 — VERIFIED (build-gated).** `suite/build_v1_supergpqa.py` `EXPECTED_LICENSE="odc-by"` enforced by `_require_license()` against the live card. |
| Required attribution | ODC-BY: attribution required for public use / database distribution. Credit m-a-p/SuperGPQA. **No full ODC-BY text travels with `suite/v1/` for this dataset** (only the IFBench copy of ODC-BY-1.0 is committed). |
| Where in repo | `suite/v1/supergpqa.jsonl`. Not in public wheel. |

### 1.6 Berkeley Function-Calling Leaderboard (BFCL)  — repo only (surface B)

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 300 single-turn (75 each of single/multiple/parallel/parallel_multiple) **plus 100 multi-turn rows vendored from the eval repo** (`BFCL_v4_multi_turn_base` + `…_long_context`, incl. `possible_answer/`). |
| Upstream | Dataset `gorilla-llm/Berkeley-Function-Calling-Leaderboard` — https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard (rev `61fc0608cfd831fcfbbaa676ebdfef0ed963eeda`); eval repo `ShishirPatil/gorilla` — https://github.com/ShishirPatil/gorilla (rev `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`) |
| License | **Apache-2.0 — AUTHOR-ASSERTED (UNVERIFIED).** Recorded as hardcoded constants (`DATASET_LICENSE`/`BFCL_EVAL_LICENSE`/`BFCL_v4 … "license":"Apache-2.0"`); **no build-time card check** (unlike MMLU-Pro/AMO/OlymMATH/SuperGPQA). Matches Gorilla's well-known Apache-2.0 licensing, but not re-verified against the live source here. |
| Required attribution | Apache-2.0: retain copyright + NOTICE. Credit Gorilla LLM / UC Berkeley. Vendored multi-turn data is *embedded* in the item set → needs NOTICE-level credit. |
| Where in repo | `suite/v1/bfcl.jsonl`, `suite/v1/bfcl_multi_turn.jsonl`. Verifier code: `cli/src/localbench/scorers/bfcl/` and `…/bfcl_multi_turn/` (+ their `NOTICE`s, which already cite the Apache-2.0 source + revision). Not in public wheel. |

### 1.7 LiveCodeBench (LCB)  — repo only (surface B) — most demanding dataset license

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 129 test-generation items, contest-date window 2023-12-01..2024-03-02. |
| Upstream | Dataset `livecodebench/test_generation` — https://huggingface.co/datasets/livecodebench/test_generation (rev `6f3ac40bbecf81eba15899139d279b077f2816fd`); harness https://github.com/LiveCodeBench/LiveCodeBench (rev `28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`) |
| License | **DATASET: CC-BY-4.0 — AUTHOR-ASSERTED (UNVERIFIED).** **HARNESS: MIT — AUTHOR-ASSERTED.** Hardcoded constants in `suite/build_v1_lcb.py` + lock; no build-time card check. CC-BY-4.0 matches the dataset's well-known licensing but is not re-verified here. |
| Required attribution | CC-BY-4.0 (the most demanding here): on any redistribution, give credit to LiveCodeBench, **link the license** (https://creativecommons.org/licenses/by/4.0/), and **indicate changes** (the suite sub-samples + reformats → changes were made). **ToS caveat:** problem statements originate from **LeetCode**; LeetCode Terms of Service apply to the problem text (lock records `source_tos_note`). |
| Where in repo | `suite/v1/lcb.jsonl`. Not in public wheel. |

### 1.8 RULER (needle-in-a-haystack)  — repo only (surface B) — derived, not vendored

| Field | Value |
|---|---|
| What's redistributed | **Derived / synthetic only — NOT upstream items.** 60 NIAH items generated locally from the RULER task *pattern*. Lock states: *"Stores compact seed parameters only; no upstream RULER code, prompts, or haystack data are vendored."* |
| Upstream | `NVIDIA/RULER` — https://github.com/NVIDIA/RULER (paper https://arxiv.org/abs/2404.06654). Reimplemented, not copied. |
| License | **Apache-2.0 — AUTHOR-ASSERTED (UNVERIFIED).** Hardcoded constant; relevant only to the *algorithm* (no upstream code/data shipped). Generated items are the project's own synthetic output. |
| Required attribution | Low obligation: items are original synthetic data. Credit NVIDIA/RULER for the algorithmic pattern (good-practice / Apache-2.0 if any code were reused). |
| Where in repo | `suite/v1/ruler_32k.jsonl`. Not in public wheel. |

### 1.9 BigCodeBench-Hard  — repo only (surface B), inert in v1

| Field | Value |
|---|---|
| What's redistributed | **Items (full text):** 148 (split v0.1.4). **Opt-in code-EXECUTION axis — 0% weight, inert in the v1 headline.** Not scored, not in `web/out/`. |
| Upstream | `bigcode/bigcodebench-hard` — https://huggingface.co/datasets/bigcode/bigcodebench-hard (rev `298d2cc7b96612e15e47313c3603ee124cee0c1f`); harness https://github.com/bigcode-project/bigcodebench |
| License | **Apache-2.0 (dataset + harness) — AUTHOR-ASSERTED (UNVERIFIED).** Hardcoded constants in `suite/build_v1_bigcodebench.py` + lock; no build-time card check. |
| Required attribution | Apache-2.0: retain copyright + NOTICE. Credit BigCode. |
| Where in repo | `suite/v1/bigcodebench_hard.jsonl`. Not in public wheel. |

---

## 2. Vendored / adapted scorer code (not dataset items)

| Source | License (evidence) | What's vendored | Where |
|---|---|---|---|
| Google Research `instruction_following_eval` (IFEval) | **Apache-2.0 — VERIFIED (license text in repo).** Full text at `cli/.../core-text-v1/LICENSES/IFEval-Apache-2.0`. | IFEval-style checker registry / scoring semantics, adapted. | `cli/src/localbench/scorers/ifeval/` |
| AllenAI `IFBench` code | **Apache-2.0 — AUTHOR-ASSERTED** (scorer NOTICE quotes upstream "licensed under Apache 2.0"; not independently re-checked). | Adapted programmatic verifier semantics (rev `1091c4c3…` inspected). | `cli/src/localbench/scorers/ifbench/` (+ `NOTICE`) |
| `ShishirPatil/gorilla` BFCL evaluator | **Apache-2.0 — AUTHOR-ASSERTED** (scorer NOTICE cites Apache-2.0 + rev). | AST-checkable scoring semantics + multi-turn evaluator semantics. | `cli/src/localbench/scorers/bfcl/`, `…/bfcl_multi_turn/` (+ `NOTICE`s) |

> The IFEval/IFBench/BFCL verifier code is **compiled into the CLI wheel** (it is product
> code, not test-only), so its Apache-2.0 notices ship to the public via surface A.
> `cli/pyproject.toml` already lists the three scorer `NOTICE`s as `package-data`.

---

## 3. Models (names + scores only — no weights redistributed)

The site/CLI **reference** model names and publish **scores**; **no model weights, GGUF
files, or embeddings are hosted or redistributed.** Per the earlier inventory (carried
forward, not re-verified here): Apache-2.0 / MIT families (Qwen*, DeepSeek*, Mistral,
Phi, GLM) — score publication is unrestricted. **Gemma** (Google Terms): benchmarking +
score publication is fine; do not imply Google endorsement; no "Built with Gemma" notice
needed for evaluation-only. **Llama 3.x** (Meta): benchmarking/results explicitly
permitted; 700M-MAU separate-license threshold not applicable at v1 scale. **Cohere
Command R** (CC-BY-NC): NC restricts *weight* redistribution, not score publication.
**Qwopus** community distill (`Jackrong/Qwopus3.6-27B-v2-MTP-GGUF`): inherits Qwen
Apache-2.0 base — confirm the distiller's card for added terms before featuring
prominently. **No model action is launch-blocking** for a scores-only site; this whole
section is **owner-to-confirm** if model names/scores ever carry endorsement-flavored copy.

---

## 4. Project's own license posture (context, not edited by this draft)

- `LICENSE` (repo root) is a **deliberate placeholder — "NOT YET CHOSEN."** All rights
  reserved in the project's own `cli/`/`web/` source until a license is picked. **Owner
  must choose a source license before any public *source* release.** (The v1 public
  surface is the exported site + the CLI wheel, not the source repo.)
- `cli/` package has **no top-level `LICENSE`/`NOTICE`/`ATTRIBUTION`** (only the per-suite
  and per-scorer notices). If the wheel goes to PyPI, consumers get the dataset/scorer
  notices but no project-level license statement — see risks R5.

---

## 5. Open questions / risks for owner (resolve before a real legal pass)

| # | Risk | Severity | Why it matters |
|---|---|---|---|
| **R1** | **IFBench license conflict between two in-repo inventories.** `license-inventory-v1.md` says Apache-2.0; everything else (and reality) says **dataset = ODC-BY-1.0**, code = Apache-2.0. | **High (clarity)** | A leftover wrong label in a foundations doc is exactly what a legal reviewer will catch and distrust. Correct/retire the old line. |
| **R2** | **The public CLI wheel already redistributes MMLU-Pro + IFBench item text.** Prior docs framed items as "private repo only." | **High (framing)** | Attribution + ODC-BY-1.0 + Ai2 Responsible-Use + third-party-output caveats for IFBench are **already-live obligations** via `pipx install`, not hypothetical. (The shipped bundle's NOTICE/ATTRIBUTION/LICENSES do cover this — but the obligation is present-tense.) |
| **R3** | **BFCL, LiveCodeBench, RULER, BigCodeBench licenses are author-asserted only** (hardcoded constants, no build-time card check), unlike MMLU-Pro/AMO/OlymMATH/SuperGPQA which are build-gated. | **Medium** | Owner/legal should confirm each against the *current* upstream card/repo before the source repo is published or these items are served. CC-BY-4.0 (LCB) is the highest-stakes to get right. |
| **R4** | **LiveCodeBench → LeetCode ToS.** Problem statements originate from LeetCode; CC-BY-4.0 governs the LCB *database* but LeetCode ToS may govern the underlying problem text. | **Medium–High** | If `lcb.jsonl` is ever published/served, this is the most likely third-party-rights snag. Get a human read on it. |
| **R5** | **Repo-root `LICENSES/` is incomplete** (only `Apache-2.0.txt` + `IFBench-ODC-BY-1.0.txt` + `MMLU-Pro-MIT.txt`). No standalone CC-BY-4.0 text, and no MIT/ODC-BY text covering AMO/OlymMATH/SuperGPQA/LCB/BigCodeBench that live only in `suite/v1/`. | **Medium** | If `suite/v1/` is ever published, those datasets ship **without** their full license texts. (The public *wheel* bundle is complete for its two datasets.) Decide: ship per-dataset license texts with `suite/v1/`, or keep `suite/v1/` private. |
| **R6** | **No project-level `LICENSE`/`NOTICE` inside `cli/`** for a PyPI wheel. | **Medium** | Standalone wheel consumers get no project license statement. Add one before PyPI (also depends on R-source-license choice). |
| **R7** | **Project's own source `LICENSE` is an unfilled placeholder.** | **Medium (blocks source release only)** | Must be chosen before any public *source* release; not blocking for site/wheel-only launch. |
| **R8** | **SuperGPQA / AMO / OlymMATH have no `license` key in `suite/v1/itemsets.lock.json`** — the license assertion lives only in the build script. | **Low** | The machine-readable lock is the natural place a downstream tool reads license from; consider writing the build-gated license into the lock for these three so the artifact is self-describing. |
| **R9** | All redistribution-implication and model-license readings here are **my interpretation, not legal advice.** | **Baseline** | A real legal pass is required before relying on any "permitted" conclusion. |

---

## 6. pyproject identity-scrub note

**`cli/pyproject.toml` is CLEAN for personal identity — no scrub needed there.** It has
**no `authors`, no `maintainers`, no `email`** field (checked: the `[project]` table
declares only name/version/description/deps). Package name is the generic `localbench`;
description is generic. Nothing in `pyproject.toml` leaks Michael / Clarity / an email.

For completeness (the project wants to be anonymous), identity exposure lives **elsewhere**
and is already tracked in the two sibling audits — **do NOT treat the following as part of
the pyproject; they are pointers for the owner, and several are already remediated**:

- `cli/pyproject.toml`: **nothing to scrub.** (Stated explicitly so a reviewer doesn't
  go hunting.)
- `cli/tests/test_ifbench.py:285`: previously hardcoded `C:/Users/Michael/AppData/...`;
  **already fixed** to `tempfile.gettempdir()` (verified in current source). The
  `anonymity-audit-v1.md` still lists this as launch-blocker "B1" — that entry is **stale**.
- **Git author identity** on every commit = `Michael Russell <michael.russell@clarityconsultive.com>`
  (per anonymity-audit). Not exposed by the site (direct-upload of `web/out/` only), but
  would surface if the **source repo** is ever pushed. Owner decision before any repo publish.
- Internal `docs/` + `.superpowers/sdd/` planning files reference "Michael" / Windows
  user paths. Internal-only; never served. Tracked in anonymity-audit §A2–A3.
- These are **out of scope for this license inventory** and out of scope for the two
  files this pass was allowed to write — listed only so the owner has one consolidated
  pointer. Authoritative anonymity detail: `anonymity-audit-v1.md` +
  `anonymity-license-sweep-2026-06-23.md`.

---

## 7. What this draft did / did not verify

- **Did verify (in-repo):** which items are redistributed and where (read the jsonl,
  confirmed full text + counts 400/294); the two distribution surfaces; build-time
  license gates for MMLU-Pro/AMO/OlymMATH/SuperGPQA; committed full license texts for
  MMLU-Pro (MIT), IFBench (ODC-BY-1.0), IFEval (Apache-2.0); the IFBench dataset-vs-code
  license split (quoted from the scorer NOTICE which quotes the source card); that
  `pyproject.toml` carries no identity.
- **Did NOT verify:** the live current state of any upstream HF card/repo (no network
  check performed by this pass); BFCL/LCB/RULER/BigCodeBench licenses beyond the
  author-asserted constants; any legal conclusion about redistribution permissibility,
  the LeetCode ToS interaction, or model endorsement copy. Those are the owner's +
  legal's to close.
