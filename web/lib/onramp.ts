import { QUANT_OPTIONS } from "./quant";

export type OnrampCatalogQuant = {
  readonly label: string;
  readonly vramGb8k: number | null;
  readonly fileGb: number | null;
  readonly bpw: number | null;
};

export type OnrampCatalogModel = {
  readonly id: string;
  readonly slug: string;
  readonly displayName: string;
  readonly family: string;
  readonly org: string;
  readonly paramsB: number | null;
  readonly reasoningCapable: boolean;
  readonly license: string;
  readonly ggufRepo: string | null;
  readonly downloads: number;
  readonly quants: readonly OnrampCatalogQuant[];
};

// The CLI reasoning registry (cli/src/localbench/reasoning_registry.py) currently RANKS only these two
// native reasoning modes; granite/nemotron/r1 exist as flag values but resolve to None (not ranked).
// So the on-ramp only ever emits these activations, and only Qwen3- and Gemma-family models are
// treated as board-rankable. Broaden this when the registry adds ranked entries.
export type ReasoningActivation = "qwen3" | "gemma4";
export type RuntimeId = "llamacpp" | "lmstudio" | "vllm";

export type RuntimeProfile = {
  readonly id: RuntimeId;
  readonly label: string;
  readonly endpoint: string;
  readonly recommended: boolean;
  readonly servedModelName: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string;
  readonly serveCommand: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string;
  readonly serveNote: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string | null;
};

const LLAMACPP_RUNTIME: RuntimeProfile = {
  id: "llamacpp",
  label: "llama.cpp",
  endpoint: "http://localhost:8080/v1",
  recommended: true,
  servedModelName: (model, quant) => `${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label}`,
  serveCommand: (model, quant) => `llama-server -hf ${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label} --port 8080`,
  serveNote: () => null,
};

export type RecommendedEntry = {
  readonly model: OnrampCatalogModel;
  readonly quant: OnrampCatalogQuant;
};

export type BenchmarkRecipe = {
  readonly setupCommand: string;
  readonly serveCommand: string;
  readonly serveNote: string | null;
  readonly benchCommand: string;
  readonly submitCommand: string | null;
  readonly lane: "bounded-final-v1" | "capped-thinking" | "answer-only";
  readonly boardComparable: boolean;
  readonly notRankableReason: string | null;
  readonly activation: ReasoningActivation | null;
  readonly servedModelName: string;
  readonly ggufRepo: string | null;
};

// Best-to-worst quality order is the order of QUANT_OPTIONS (FP16 first, Q2_K last).
const QUANT_RANK = new Map<string, number>(QUANT_OPTIONS.map((label, index) => [label, index]));

function quantRank(label: string): number {
  return QUANT_RANK.get(label) ?? Number.MAX_SAFE_INTEGER;
}

// Returns the ranked CLI activation for a model's family, or null when the model is not in the
// ranked registry (so the on-ramp can flag it as not-board-comparable rather than guess).
export function rankedActivationFor(model: { family: string; org: string }): ReasoningActivation | null {
  const haystack = `${model.family} ${model.org}`.toLowerCase();
  if (haystack.includes("qwen")) {
    return "qwen3";
  }
  if (haystack.includes("gemma")) {
    return "gemma4";
  }
  return null;
}

export function recommendedQuantForVram(model: OnrampCatalogModel, vramGb: number): OnrampCatalogQuant | null {
  const fitting = model.quants.filter(
    (quant): quant is OnrampCatalogQuant & { vramGb8k: number } => quant.vramGb8k !== null && quant.vramGb8k <= vramGb,
  );
  if (fitting.length === 0) {
    return null;
  }
  return fitting.reduce((best, quant) => (quantRank(quant.label) < quantRank(best.label) ? quant : best));
}

// "Popular" models for the picker: most-downloaded board-rankable models near the top of the size
// range that fits the selected VRAM. Popularity is a convenience ordering, not an endorsement.
export function popularModels(
  catalog: readonly OnrampCatalogModel[],
  vramGb: number,
  limit = 5,
): readonly RecommendedEntry[] {
  const fitting = catalog
    .filter((model) => model.reasoningCapable && model.ggufRepo !== null && rankedActivationFor(model) !== null)
    .map((model) => ({ model, quant: recommendedQuantForVram(model, vramGb) }))
    .filter((entry): entry is RecommendedEntry => entry.quant !== null);
  const maxParams = fitting.reduce((max, entry) => Math.max(max, entry.model.paramsB ?? 0), 0);
  const nearTopSizeRange = fitting.filter(
    (entry) => entry.model.paramsB !== null && entry.model.paramsB >= 0.3 * maxParams,
  );
  const candidates = nearTopSizeRange.length > 0 ? nearTopSizeRange : fitting;
  return candidates
    .sort((left, right) => right.model.downloads - left.model.downloads)
    .slice(0, limit);
}

export function listOrgs(catalog: readonly OnrampCatalogModel[]): readonly string[] {
  return [...new Set(catalog.map((model) => model.org).filter((org) => org !== ""))].sort((left, right) =>
    left.localeCompare(right),
  );
}

export function modelsForOrg(catalog: readonly OnrampCatalogModel[], org: string): readonly OnrampCatalogModel[] {
  return catalog.filter((model) => model.org === org).sort((left, right) => right.downloads - left.downloads);
}

// Ollama is intentionally excluded: its defaults (num_ctx 2048, its own chat template, its own
// sampler defaults) silently change the inputs a comparable benchmark must pin, so runs produced
// through it are not comparable. The on-ramp recommends llama.cpp (serves GGUF directly, full
// control over sampling/context/template).
export const RUNTIME_PROFILES: readonly RuntimeProfile[] = [
  LLAMACPP_RUNTIME,
  {
    id: "lmstudio",
    label: "LM Studio",
    endpoint: "http://localhost:1234/v1",
    recommended: false,
    servedModelName: (model) => model.id,
    serveCommand: () => "",
    serveNote: (model, quant) =>
      `In LM Studio: search ${model.ggufRepo ?? model.id}, download the ${quant.label} file, then open the Developer tab and Start Server (port 1234). Use the model name shown in the server log if it differs.`,
  },
  {
    id: "vllm",
    label: "vLLM",
    endpoint: "http://localhost:8000/v1",
    recommended: false,
    servedModelName: (model) => model.id,
    serveCommand: (model) => `vllm serve ${model.id} --port 8000`,
    serveNote: () =>
      "vLLM serves the full-precision weights — the GGUF quant you picked does not apply, so VRAM use is much higher. It may also apply the repo generation_config; pass --generation-config vllm to pin sampling.",
  },
];

export function buildRecipe(input: {
  model: OnrampCatalogModel;
  quant: OnrampCatalogQuant;
  runtime: RuntimeProfile;
}): BenchmarkRecipe {
  const { model, quant, runtime } = input;
  const servedModelName = runtime.servedModelName(model, quant);
  const activation = model.reasoningCapable ? rankedActivationFor(model) : null;

  // bounded-final-v1: every model runs the ONE ranked lane. --profile auto introspects the
  // model's own chat template (thinking models get the bounded think sub-budget, the rest run
  // answer-only) — no family gate. The [hf] extra ships the template introspection dependency;
  // plain `pip install local-bench-ai` cannot resolve --hf-model-id (user-path smoke, 2026-07-05).
  const setupCommand = [
    'pip install "local-bench-ai[hf]"',
    "localbench fetch-suite --site https://local-bench.ai --suite suite-v1-text-code-agentic-5axis-v1 --accept-suite-terms",
  ].join("\n");
  const benchCommand = [
    "localbench run",
    `--endpoint ${runtime.endpoint}`,
    `--model ${servedModelName}`,
    `--hf-model-id ${model.id}`,
    "--lane bounded-final-v1",
    "--profile auto",
    "--tier standard",
    "--publishable",
    "--sampler-seed 1234",
    "--out runs/my-run.json",
  ].join(" \\\n  ");

  return {
    setupCommand,
    serveCommand: runtime.serveCommand(model, quant),
    serveNote: runtime.serveNote(model, quant),
    benchCommand,
    submitCommand: "localbench submit run --run runs/my-run.json",
    lane: "bounded-final-v1",
    boardComparable: true,
    notRankableReason: null,
    activation,
    servedModelName,
    ggufRepo: model.ggufRepo,
  };
}
