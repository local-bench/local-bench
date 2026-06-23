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

// The headline board runs the v1 suite. `localbench run` with no --suite-dir falls back to suite/v0
// (discover_suite_dir), so every recipe pins this explicitly.
export const BOARD_SUITE_DIR = "suite/v1";

export type RuntimeProfile = {
  readonly id: RuntimeId;
  readonly label: string;
  readonly endpoint: string;
  readonly recommended: boolean;
  readonly servedModelName: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string;
  readonly serveCommand: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string;
  readonly serveNote: (model: OnrampCatalogModel, quant: OnrampCatalogQuant) => string | null;
};

export type RecommendedEntry = {
  readonly model: OnrampCatalogModel;
  readonly quant: OnrampCatalogQuant;
};

export type BenchmarkRecipe = {
  readonly serveCommand: string;
  readonly serveNote: string | null;
  readonly benchCommand: string;
  readonly lane: "capped-thinking" | "answer-only";
  readonly boardComparable: boolean;
  readonly notRankableReason: string | null;
  readonly activation: ReasoningActivation | null;
  readonly servedModelName: string;
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

// "Popular" models for the picker: only board-rankable families (Qwen3/Gemma) with a GGUF repo and a
// quant that fits, ranked by the catalog's HF download snapshot. Popularity is a convenience ordering,
// not an endorsement, and the catalog is a static snapshot until the live HF refresh lands.
export function popularModels(
  catalog: readonly OnrampCatalogModel[],
  vramGb: number,
  limit = 5,
): readonly RecommendedEntry[] {
  return catalog
    .filter((model) => model.reasoningCapable && model.ggufRepo !== null && rankedActivationFor(model) !== null)
    .map((model) => ({ model, quant: recommendedQuantForVram(model, vramGb) }))
    .filter((entry): entry is RecommendedEntry => entry.quant !== null)
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
  {
    id: "llamacpp",
    label: "llama.cpp",
    endpoint: "http://localhost:8080/v1",
    recommended: true,
    servedModelName: (model, quant) => `${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label}`,
    serveCommand: (model, quant) =>
      `llama-server -hf ${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label} --port 8080`,
    serveNote: () => null,
  },
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
  const boardComparable = activation !== null;
  const lane: BenchmarkRecipe["lane"] = boardComparable ? "capped-thinking" : "answer-only";

  const notRankableReason = boardComparable
    ? null
    : model.reasoningCapable
      ? "Only Qwen3 and Gemma reasoning modes are board-ranked today."
      : "Not a reasoning model, so it runs answer-only.";

  const parts = ["localbench run", `--endpoint ${runtime.endpoint}`, `--model ${servedModelName}`];
  if (boardComparable && activation !== null) {
    parts.push(
      `--hf-model-id ${model.id}`,
      `--suite-dir ${BOARD_SUITE_DIR}`,
      "--lane capped-thinking",
      `--reasoning-activation ${activation}`,
    );
  } else {
    parts.push(`--suite-dir ${BOARD_SUITE_DIR}`, "--lane answer-only");
  }
  parts.push("--tier standard", "--out my-run.json");

  return {
    serveCommand: runtime.serveCommand(model, quant),
    serveNote: runtime.serveNote(model, quant),
    benchCommand: parts.join(" "),
    lane,
    boardComparable,
    notRankableReason,
    activation,
    servedModelName,
  };
}
