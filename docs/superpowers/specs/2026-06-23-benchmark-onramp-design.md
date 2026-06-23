# "Benchmark a model" on-ramp — design (v2-gated)

Date: 2026-06-23. Brainstormed with Michael + GPT-5.5 Pro (oracle) red-team
(session `lb-benchmark-onramp`). Replaces the landing-page Rig-Match Finder with a
contributor on-ramp that emits a copy-paste benchmark recipe.

## Status & coupling
**BUILD NOW (v1), with an honest soft ending.** Michael's updated call (2026-06-23): build
the front-of-house on-ramp now — it fixes the confusing finder immediately and previews the
contribution flow (the oracle endorsed shipping ahead of v2 if the promise is honest). The
ONLY part gated on v2 is the submit step: the anonymity gate (no public repo → no
GitHub-issue intake) means the v1 ending is **"run it, save `my-run.json`; automated upload
+ server re-score land in v2."** No fake upload UI, no dead "Submit" button — the copy says
plainly that v1 produces a local artifact and v2 publishes it.

The v2 backend (`docs/foundations/submission-verification-design.md`: R2 presigned upload +
Workers + D1 + server re-score + trust labels) is the CLI/main agent's domain; when it lands,
the on-ramp's final step gets wired to it. This card **replaces** the Rig-Match Finder (whose
answer-only lane was already stripped, commit `d4b857b`).

## Why (the job to be done)
A leaderboard lives on **coverage** — getting people to contribute comparable runs. The
current finder answers a *consumer* question ("what existing result fits my GPU?"), which
is the wrong first action for a newcomer. The on-ramp answers the *contributor* question
("how do I produce one benchmark run?") and turns a static board into a participation funnel.

## Locked decisions
1. **Replace the finder as the hero — no equal Consumer/Contributor tabs** (tabs recreate
   today's ambiguity). Keep rig-fit as a *secondary* affordance (the VRAM step inside the
   builder + a small "filter the board by my VRAM" link).
2. **Picker opens VRAM-first**, not lab-first (the oracle's edit to the original lab→model
   instinct — newcomers don't know Qwen vs Gemma vs DeepSeek). Three paths:
   - **Recommended for my VRAM** → 3–5 known-good candidates (default)
   - **Browse catalog** → lab → model → quant/distill (the original instinct, demoted)
   - **Paste HF repo** → advanced / experimental
3. **Layout: vertical stack** — scatter (top) → summary board → on-ramp card (full width,
   where the finder box is now) → CTA.
4. **Honest framing** — it generates a *local benchmark artifact*, never "submit to the
   leaderboard." (Moot at ship time since it's v2-gated, but the copy discipline stays:
   the run lands via the v2 upload + server re-score + trust label, not by magic.)

## The on-ramp card — four inputs
1. **I have:** 8 / 12 / 16 / 24 / 48+ GB VRAM
2. **Choose model:** Recommended (default) / Browse catalog / Paste HF repo
3. **Runtime:** Ollama (recommended) / LM Studio / llama.cpp / vLLM
4. **Output:** copyable **Step 1 (serve)** + **Step 2 (`localbench run`)**

Below output: the v2 trust note (run lands after server re-score + trust label).
Secondary link: "Just exploring? Filter the leaderboard for my VRAM."

### Serve-then-run is stated bluntly, never hidden
> localbench does not download or run the model. First start a local server; then
> localbench sends the benchmark to that endpoint.

Two visual panels. Ollama is the beginner default, tied to a **canonical HF artifact**:
```
# Step 1 — start the model (leave running)
ollama run hf.co/{owner}/{repo}:{quant}
# Step 2 — in a second terminal, benchmark it
localbench run --endpoint http://localhost:11434/v1 --model hf.co/{owner}/{repo}:{quant} --tier standard --out my-run.json
```
Runtime profiles carry the right endpoint each (don't make users guess):
Ollama OpenAI-compat `:11434/v1` (native API is `/api`), LM Studio `:1234/v1`,
vLLM `:8000/v1`, llama.cpp server. Add a localhost-binding safety note.

## Artifact identity vs display name (design the row NOW)
Store the human label separately from the verification identity so v2 doesn't force a
painful migration:
- **Display model:** e.g. "Qwen3 8B Instruct"
- **Artifact:** HF repo + GGUF file/SHA256 (or runtime-native tag) + tokenizer/chat-template hash
- **Runtime:** Ollama / llama.cpp / LM Studio / vLLM + version + CLI version
- **Trust:** project anchor / community re-scored / spot-reproduced (per the v2 taxonomy)

Quant labels (`Q4_K_M` in a GGUF filename vs an Ollama tag vs a catalog variant) are
**display labels only** — key off the canonical artifact id.

## Comparability guardrails (the real hidden risk — not the UI)
Serving-stack defaults move scores: vLLM silently applies a repo's `generation_config.json`
(disable with `--generation-config vllm`); llama.cpp/Ollama/LM Studio each have sampler
defaults. So:
- The **CLI owns benchmark params** (decoding/sampler/context/template) as much as possible.
- UI copy: "Do not change sampling, context, or prompt-template settings unless the recipe
  says so." Do **not** teach "temperature 0 is enough" (v2 pins `top_k=1` greedy).
- VRAM tiers are **"recommended," never "guaranteed fits"** ("may be slower or fail on some
  runtimes; close other GPU workloads").
- Hero copy: "**Start** a benchmark in about a minute" — not "finish."

## Picker sourcing
- **v1.5 (build-time):** drive the picker from `model_catalog.json`, enriched with the
  recipe metadata: display name, lab, family, size, base/instruct/reasoning/distill marker,
  canonical HF repo, GGUF repo, preferred quant per VRAM tier, exact quant tag/filename
  where known, license/gated note, known-good vs experimental.
- **Paste-any-HF-id:** explicitly experimental — "we have not validated this repo has a
  compatible GGUF, template, quant, or license; results may not be comparable."
- **v2+ (cached registry):** a periodic job fetches candidate HF repos, classifies GGUFs,
  normalizes quant names into a static/D1 cache. The browser queries OUR cache.
- **Avoid:** live client-side HF search from the static hero (rate limits, GGUF-as-files,
  gated models, no HF tokens in the browser).

## Manual-submission support debt (constrain it)
Even with v2 auto-upload, gate eligibility by category: known catalog model = eligible;
paste-HF = local-run / best-effort; modified/LoRA/private = local-only unless the
contributor supplies artifact details. Keeps the queue from becoming "debug my LLM setup."

## Interim (before v2 ships)
The Rig-Match Finder stays on the landing page until the on-ramp replaces it. OPEN: whether
to do a light interim tidy now — drop the finder's **context** + **lane** selectors (context
is suite-fixed; lane collapsed) to cut the confusion Michael flagged — or leave it untouched
until the v2 swap. (Cheap, isolated change if wanted.)

## Open items / coordination
- Flag to the CLI/main agent: the on-ramp is now a **v2 co-deliverable** with their upload +
  re-score backend; sequence them together.
- The exact `localbench run` flags + whether the CLI accepts `hf.co/...:{quant}` model names
  through an Ollama endpoint (it should — that's the served model name) need a quick confirm.
- When v2 is scheduled, this design → `writing-plans` → implementation. Not before.
