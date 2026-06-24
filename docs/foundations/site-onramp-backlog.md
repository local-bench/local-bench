# On-ramp "recipe" backlog (for the SITE agent)

The landing-page **"Get the recipe to benchmark a model"** on-ramp (Browse catalogue
-> pick model -> pick quant) needs work. These items are owned by the SITE agent (this
CLI/scoring agent does not edit `web/`); relay as needed.

---

## 1. Quant selector offers no PUBLISHER choice (likely affects every model)

**Observed by Michael (2026-06-23):** in "Browse catalogue", selecting a quant for a model
returns a single hard-coded build. e.g. **DeepSeek Flash -> Q4** yields a *Jacrong* quant.
But multiple publishers ship Q4 GGUFs of the same model -- **Unsloth**, **bartowski**, etc.
The on-ramp currently pins one publisher per (model, quant-level) and gives the user no
choice. Almost certainly the same pattern for every model in the catalogue.

**Why this is more than cosmetic -- it is a provenance / reproducibility issue:**
- "Q4_K_M" is *underspecified* without the publisher **and** the exact file. Different GGUF
  publishers produce **different bytes** for the nominally-same quant level: different imatrix
  calibration corpora, different per-tensor type overrides, sometimes different llama.cpp
  conversion commits. They can and do score differently on the same suite.
- local-bench's entire spine is "freeze the exact model artifact (URL + SHA256) so a number is
  reproducible." A recipe that says "run Q4" without pinning publisher + file quietly undercuts
  that promise. The recipe a user copies should emit the **exact artifact we benchmarked**
  (HF repo, filename, SHA256) -- not just a quant tier.

**Suggested direction (site agent to scope/own):**
- Catalogue carries **multiple publisher options per quant level**, each with its exact HF repo
  + filename + SHA256.
- **Default** to whichever publisher the board actually benchmarked, so "the recipe" == "what we
  scored" and stays board-comparable.
- Expose the alternatives, but make explicit that a different publisher = a different artifact =
  **potentially a different score** (not board-comparable unless we benchmarked that exact file).
- Ties directly into the oracle's "freeze model artifact URLs + SHA256s" launch item and the
  board provenance story.

---

*(Add further on-ramp UX/recipe items below as they come up.)*
