import { RUNTIME_OVERHEAD_GB } from "./rig-match";
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

export type ReasoningActivation = "qwen3" | "granite" | "nemotron" | "r1" | "gemma4";
export type RuntimeId = "ollama" | "lmstudio" | "llamacpp" | "vllm";

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
  readonly activation: ReasoningActivation;
  readonly activationConfident: boolean;
  readonly servedModelName: string;
};

// Best-to-worst quality order is the order of QUANT_OPTIONS (FP16 first, Q2_K last).
const QUANT_RANK = new Map<string, number>(QUANT_OPTIONS.map((label, index) => [label, index]));

function quantRank(label: string): number {
  return QUANT_RANK.get(label) ?? Number.MAX_SAFE_INTEGER;
}

export function reasoningActivationFor(model: { family: string; org: string }): {
  activation: ReasoningActivation;
  confident: boolean;
} {
  const haystack = `${model.family} ${model.org}`.toLowerCase();
  if (haystack.includes("qwen")) {
    return { activation: "qwen3", confident: true };
  }
  if (haystack.includes("granite")) {
    return { activation: "granite", confident: true };
  }
  if (haystack.includes("nemotron")) {
    return { activation: "nemotron", confident: true };
  }
  if (haystack.includes("deepseek") || /\br1\b/.test(haystack)) {
    return { activation: "r1", confident: true };
  }
  if (haystack.includes("gemma")) {
    return { activation: "gemma4", confident: true };
  }
  return { activation: "qwen3", confident: false };
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

export function recommendModels(
  catalog: readonly OnrampCatalogModel[],
  vramGb: number,
  limit = 5,
): readonly RecommendedEntry[] {
  return catalog
    .filter((model) => model.reasoningCapable && model.ggufRepo !== null)
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

function ggufTag(model: OnrampCatalogModel, quant: OnrampCatalogQuant): string {
  return `hf.co/${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label}`;
}

export const RUNTIME_PROFILES: readonly RuntimeProfile[] = [
  {
    id: "ollama",
    label: "Ollama",
    endpoint: "http://localhost:11434/v1",
    recommended: true,
    servedModelName: (model, quant) => ggufTag(model, quant),
    serveCommand: (model, quant) => `ollama run ${ggufTag(model, quant)}`,
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
    id: "llamacpp",
    label: "llama.cpp",
    endpoint: "http://localhost:8080/v1",
    recommended: false,
    servedModelName: (model, quant) => `${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label}`,
    serveCommand: (model, quant) =>
      `llama-server -hf ${model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${quant.label} --port 8080`,
    serveNote: () => null,
  },
  {
    id: "vllm",
    label: "vLLM",
    endpoint: "http://localhost:8000/v1",
    recommended: false,
    servedModelName: (model) => model.id,
    serveCommand: (model) => `vllm serve ${model.id} --port 8000`,
    serveNote: () => "vLLM may apply the repo generation_config; pass --generation-config vllm to disable it.",
  },
];

export function buildRecipe(input: {
  model: OnrampCatalogModel;
  quant: OnrampCatalogQuant;
  runtime: RuntimeProfile;
}): BenchmarkRecipe {
  const { model, quant, runtime } = input;
  const servedModelName = runtime.servedModelName(model, quant);
  const lane: BenchmarkRecipe["lane"] = model.reasoningCapable ? "capped-thinking" : "answer-only";
  const { activation, confident } = reasoningActivationFor(model);

  const parts = ["localbench run", `--endpoint ${runtime.endpoint}`, `--model ${servedModelName}`];
  if (lane === "capped-thinking") {
    parts.push(`--hf-model-id ${model.id}`, "--lane capped-thinking", `--reasoning-activation ${activation}`);
  } else {
    parts.push("--lane answer-only");
  }
  parts.push("--tier standard", "--out my-run.json");

  return {
    serveCommand: runtime.serveCommand(model, quant),
    serveNote: runtime.serveNote(model, quant),
    benchCommand: parts.join(" "),
    lane,
    activation,
    activationConfident: confident,
    servedModelName,
  };
}

// Imported to keep the VRAM-fit convention aligned with rig-match.ts. The catalog's vram_gb_8k is
// already an at-8k requirement, so recommendedQuantForVram compares against it directly (matching
// how estimateVramRequirement uses vramRequiredGb8k). Referenced here so the shared constant stays
// a single source of truth even though the on-ramp does not add overhead on top of the catalog figure.
export const ONRAMP_RUNTIME_OVERHEAD_GB = RUNTIME_OVERHEAD_GB;
