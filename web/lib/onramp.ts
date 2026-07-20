import { QUANT_OPTIONS } from "./quant";
import { formatCanonicalBenchCommand, LOCALBENCH_INSTALL_COMMAND } from "./cli-onboarding";

export type OnrampCatalogQuant = {
  readonly label: string;
  readonly vramGb8k: number | null;
  readonly fileGb: number | null;
  readonly bpw: number | null;
  readonly filename?: string | null;
  readonly revision?: string | null;
  readonly fileSha256?: string | null;
  readonly artifactFiles?: readonly OnrampCatalogArtifactFile[];
};

export type OnrampCatalogArtifactFile = {
  readonly filename: string;
  readonly fileSha256: string;
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
  readonly likes: number;
  readonly trending: number;
  readonly modelKind: ModelKind;
  readonly baseModelIds: readonly string[];
  readonly baseModelId: string | null;
  readonly baseModelSlug: string | null;
  readonly baseModelDisplayName: string | null;
  readonly quants: readonly OnrampCatalogQuant[];
};

export type RuntimeId = "llamacpp" | "lmstudio" | "vllm";
export type PopularitySort = "downloads" | "trending" | "likes";
export type ModelKind = "base" | "finetune" | "distill" | "merge";

export type RuntimeProfile = {
  readonly id: RuntimeId;
  readonly label: string;
  readonly endpoint: string;
  readonly recommended: boolean;
  readonly servedModelName: (input: RuntimeRecipeInput) => string;
  readonly serveCommand: (input: RuntimeRecipeInput) => string;
  readonly serveNote: (input: RuntimeRecipeInput) => string | null;
};

type RuntimeRecipeInput = {
  readonly model: OnrampCatalogModel;
  readonly quant: OnrampCatalogQuant;
  readonly hfModelId: string | null;
};

function llamaCppServedModelName(input: RuntimeRecipeInput): string {
  return `${input.model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${input.quant.label}`;
}

const LLAMACPP_RUNTIME: RuntimeProfile = {
  id: "llamacpp",
  label: "llama.cpp",
  endpoint: "http://localhost:8080/v1",
  recommended: true,
  servedModelName: llamaCppServedModelName,
  serveCommand: (input) => {
    const servedModelName = llamaCppServedModelName(input);
    return `llama-server -hf ${input.model.ggufRepo ?? "<owner>/<repo>-GGUF"}:${input.quant.label} --ctx-size 32768 --parallel 1 --alias ${servedModelName} --port 8080`;
  },
  serveNote: () => null,
};

export type RecommendedEntry = {
  readonly model: OnrampCatalogModel;
  readonly quant: OnrampCatalogQuant;
};

export type BrowseVariant = {
  readonly model: OnrampCatalogModel;
  readonly kind: ModelKind;
  readonly official: boolean;
  readonly alsoBasedOn: readonly OnrampCatalogModel[];
};

export type BrowseFamily = {
  readonly base: OnrampCatalogModel;
  readonly variants: readonly BrowseVariant[];
};

export type BrowseFamiliesOptions = {
  readonly lab?: string;
  readonly search?: string;
  readonly vramGb?: number;
};

export type BestFitLabel = {
  readonly quant: OnrampCatalogQuant | null;
  readonly label: string;
};

export type BenchmarkTimeEstimate =
  | {
      readonly kind: "range";
      readonly label: string;
      readonly lowerHours: number;
      readonly pointHours: number;
      readonly upperHours: number;
    }
  | {
      readonly kind: "generic";
      readonly label: string;
    };

export type BenchmarkRecipe = {
  readonly installCommand: string;
  readonly lead: BenchmarkRecipeLead;
  readonly setupCommand: string;
  readonly serveCommand: string;
  readonly serveNote: string | null;
  readonly benchCommand: string;
  readonly submitCommand: string;
  readonly lane: "bounded-final-v2";
  readonly servedModelName: string;
  readonly ggufRepo: string | null;
  readonly identityMode: "full" | "basic";
  readonly model: OnrampCatalogModel;
  readonly runtimeId: RuntimeId;
};

export type BenchmarkRecipeLead =
  | {
      readonly kind: "publishable";
      readonly command: string;
    }
  | {
      readonly kind: "local-only";
      readonly command: string;
    }
  | {
      readonly kind: "unavailable";
      readonly reason: string;
    }
  | {
      readonly kind: "maintainer";
      readonly command: string;
    };

export type BenchmarkRecipeSource = "catalog" | "paste";

// Best-to-worst quality order is the order of QUANT_OPTIONS (FP16 first, Q2_K last).
const QUANT_RANK = new Map<string, number>(QUANT_OPTIONS.map((label, index) => [label, index]));
const BENCH_TIME_SMALL_ANCHOR_PARAMS_B = 12;
const BENCH_TIME_SMALL_ANCHOR_HOURS = 17;
const BENCH_TIME_LARGE_ANCHOR_PARAMS_B = 27;
const BENCH_TIME_LARGE_ANCHOR_HOURS = 24;
const BENCH_TIME_MIN_HOURS = 2;
const BENCH_TIME_MAX_HOURS = 96;
const Q4_FILE_GB_TO_PARAMS_B = 1.8;
const UNPINNED_ONE_COMMAND_REASON =
  "This catalog quant is missing artifact pins, so the one-command flow fails closed.";

function quantRank(label: string): number {
  return QUANT_RANK.get(label) ?? Number.MAX_SAFE_INTEGER;
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

export function bestFitForVram(model: OnrampCatalogModel, vramGb: number): BestFitLabel {
  const quant = recommendedQuantForVram(model, vramGb);
  return quant === null
    ? { quant: null, label: `no listed quant fits ${vramGb} GB` }
    : { quant, label: `best fit: ${quant.label}` };
}

export function estimateBenchmarkTime(model: OnrampCatalogModel, quant: OnrampCatalogQuant): BenchmarkTimeEstimate {
  const effectiveParamsB = model.paramsB ?? (quant.fileGb === null ? null : quant.fileGb * Q4_FILE_GB_TO_PARAMS_B);
  if (effectiveParamsB === null) {
    return { kind: "generic", label: "expect a full day on a 24GB-class GPU" };
  }
  const slope =
    (BENCH_TIME_LARGE_ANCHOR_HOURS - BENCH_TIME_SMALL_ANCHOR_HOURS) /
    (BENCH_TIME_LARGE_ANCHOR_PARAMS_B - BENCH_TIME_SMALL_ANCHOR_PARAMS_B);
  const rawHours = BENCH_TIME_SMALL_ANCHOR_HOURS + (effectiveParamsB - BENCH_TIME_SMALL_ANCHOR_PARAMS_B) * slope;
  const pointHours = Math.round(clamp(rawHours, BENCH_TIME_MIN_HOURS, BENCH_TIME_MAX_HOURS));
  const lowerHours = Math.max(BENCH_TIME_MIN_HOURS, Math.round(pointHours * 0.75));
  const upperHours = Math.max(lowerHours, Math.round(pointHours * 1.25));
  return {
    kind: "range",
    label: `~${lowerHours}–${upperHours}h`,
    lowerHours,
    pointHours,
    upperHours,
  };
}

export function smallestFileQuant(model: OnrampCatalogModel): OnrampCatalogQuant | null {
  const first = model.quants[0];
  if (first === undefined) {
    return null;
  }
  return model.quants.reduce((smallest, quant) => {
    const smallestFile = smallest.fileGb ?? Number.POSITIVE_INFINITY;
    const quantFile = quant.fileGb ?? Number.POSITIVE_INFINITY;
    if (quantFile < smallestFile) {
      return quant;
    }
    if (quantFile === smallestFile && quantRank(quant.label) > quantRank(smallest.label)) {
      return quant;
    }
    return smallest;
  }, first);
}

export function popularModels(
  catalog: readonly OnrampCatalogModel[],
  vramGb: number,
  sort: PopularitySort = "downloads",
  limit = 5,
): readonly RecommendedEntry[] {
  const fitting = catalog
    .filter((model) => model.ggufRepo !== null)
    .map((model) => ({ model, quant: recommendedQuantForVram(model, vramGb) }))
    .filter((entry): entry is RecommendedEntry => entry.quant !== null);
  const maxParams = fitting.reduce((max, entry) => Math.max(max, entry.model.paramsB ?? 0), 0);
  const nearTopSizeRange = fitting.filter(
    (entry) => entry.model.paramsB !== null && entry.model.paramsB >= 0.3 * maxParams,
  );
  const candidates = nearTopSizeRange.length > 0 ? nearTopSizeRange : fitting;
  return candidates
    .sort(
      (left, right) =>
        right.model[sort] - left.model[sort] ||
        right.model.downloads - left.model.downloads ||
        left.model.displayName.localeCompare(right.model.displayName),
    )
    .slice(0, limit);
}

export function listOrgs(catalog: readonly OnrampCatalogModel[]): readonly string[] {
  return [...new Set(catalog.map((model) => model.org).filter((org) => org !== ""))].sort((left, right) =>
    left.localeCompare(right),
  );
}

function catalogModelMap(catalog: readonly OnrampCatalogModel[]): ReadonlyMap<string, OnrampCatalogModel> {
  return new Map(catalog.map((model) => [model.id, model]));
}

function cataloguedBases(
  model: OnrampCatalogModel,
  byId: ReadonlyMap<string, OnrampCatalogModel>,
): readonly OnrampCatalogModel[] {
  return model.baseModelIds.flatMap((baseId) => {
    const base = byId.get(baseId);
    return base === undefined || base.id === model.id ? [] : [base];
  });
}

function isCataloguedDerivative(model: OnrampCatalogModel, byId: ReadonlyMap<string, OnrampCatalogModel>): boolean {
  return cataloguedBases(model, byId).length > 0;
}

export function isDerivativeModel(model: OnrampCatalogModel): boolean {
  return model.baseModelSlug !== null;
}

export function listBaseLabs(catalog: readonly OnrampCatalogModel[]): readonly string[] {
  const byId = catalogModelMap(catalog);
  return [
    ...new Set(
      catalog
        .filter((model) => !isCataloguedDerivative(model, byId))
        .map((model) => model.org)
        .filter((org) => org !== ""),
    ),
  ].sort((left, right) => left.localeCompare(right));
}

function searchText(model: OnrampCatalogModel): string {
  return [model.id, model.displayName, model.org, model.ggufRepo ?? ""].join("\n").toLowerCase();
}

function matchesSearch(model: OnrampCatalogModel, search: string): boolean {
  return search === "" || searchText(model).includes(search);
}

function sortBases(left: OnrampCatalogModel, right: OnrampCatalogModel): number {
  return right.downloads - left.downloads || left.displayName.localeCompare(right.displayName);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function sortVariants(vramGb: number | undefined) {
  return (left: BrowseVariant, right: BrowseVariant): number => {
    const leftFits = vramGb === undefined ? 0 : recommendedQuantForVram(left.model, vramGb) === null ? 0 : 1;
    const rightFits = vramGb === undefined ? 0 : recommendedQuantForVram(right.model, vramGb) === null ? 0 : 1;
    return (
      rightFits - leftFits ||
      right.model.downloads - left.model.downloads ||
      left.model.displayName.localeCompare(right.model.displayName)
    );
  };
}

function variantForBase(
  model: OnrampCatalogModel,
  base: OnrampCatalogModel,
  allBases: readonly OnrampCatalogModel[],
): BrowseVariant {
  return {
    model,
    kind: model.modelKind,
    official: model.org !== "" && model.org === base.org,
    alsoBasedOn: allBases.filter((candidate) => candidate.id !== base.id),
  };
}

export function browseFamilies(
  catalog: readonly OnrampCatalogModel[],
  opts: BrowseFamiliesOptions = {},
): readonly BrowseFamily[] {
  const byId = catalogModelMap(catalog);
  const search = (opts.search ?? "").trim().toLowerCase();
  const bases = catalog
    .filter((model) => !isCataloguedDerivative(model, byId))
    .filter((model) => opts.lab === undefined || opts.lab === "" || model.org === opts.lab)
    .sort(sortBases);

  return bases.flatMap((base) => {
    const variants = catalog
      .flatMap((model) => {
        const basesForVariant = cataloguedBases(model, byId);
        return basesForVariant.some((candidate) => candidate.id === base.id)
          ? [variantForBase(model, base, basesForVariant)]
          : [];
      })
      .sort(sortVariants(opts.vramGb));
    const baseMatches = matchesSearch(base, search);
    const matchingVariants = variants.filter((variant) => matchesSearch(variant.model, search));
    if (search !== "" && !baseMatches && matchingVariants.length === 0) {
      return [];
    }
    return [{ base, variants: search !== "" && !baseMatches ? matchingVariants : variants }];
  });
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
    servedModelName: (input) => input.hfModelId ?? input.model.id,
    serveCommand: () => "",
    serveNote: (input) =>
      `In LM Studio: search ${input.model.ggufRepo ?? input.hfModelId ?? input.model.id}, download the ${input.quant.label} file, then open the Developer tab and Start Server (port 1234). Check the model id with curl http://localhost:1234/v1/models and use the returned id in --model if it differs.`,
  },
  {
    id: "vllm",
    label: "vLLM",
    endpoint: "http://localhost:8000/v1",
    recommended: false,
    servedModelName: (input) => input.hfModelId ?? input.model.id,
    serveCommand: (input) => `vllm serve ${input.hfModelId ?? input.model.id} --port 8000 --generation-config vllm`,
    serveNote: () =>
      "vLLM serves the full-precision weights — the GGUF quant you picked does not apply, so VRAM use is much higher.",
  },
];

function normalizeIdentityRepo(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? "";
  return trimmed === "" ? null : trimmed;
}

function sanitizeRunPart(value: string): string {
  const sanitized = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized === "" ? "model" : sanitized;
}

function runOutputPath(model: OnrampCatalogModel, quant: OnrampCatalogQuant): string {
  return `runs/${sanitizeRunPart(model.slug)}-${sanitizeRunPart(quant.label)}.json`;
}

function hasText(value: string | null | undefined): boolean {
  return value !== undefined && value !== null && value.trim() !== "";
}

export function quantHasArtifactPins(quant: OnrampCatalogQuant): boolean {
  if (!hasText(quant.revision)) {
    return false;
  }
  if (hasText(quant.filename) && hasText(quant.fileSha256)) {
    return true;
  }
  const artifactFiles = quant.artifactFiles ?? [];
  return (
    artifactFiles.length > 0 &&
    artifactFiles.every((file) => hasText(file.filename) && hasText(file.fileSha256))
  );
}

function oneCommandTarget(model: OnrampCatalogModel, source: BenchmarkRecipeSource): string {
  return source === "paste" ? model.id : model.slug;
}

function buildOneCommandLead(
  model: OnrampCatalogModel,
  quant: OnrampCatalogQuant,
  source: BenchmarkRecipeSource,
): BenchmarkRecipeLead {
  const command = formatCanonicalBenchCommand(shellArg(oneCommandTarget(model, source)), shellArg(quant.label));
  if (source === "paste") {
    return { kind: "local-only", command };
  }
  if (quantHasArtifactPins(quant)) {
    return { kind: "publishable", command };
  }
  return { kind: "unavailable", reason: UNPINNED_ONE_COMMAND_REASON };
}

const RUNTIME_IDENTITY_NAMES: Record<RuntimeId, string> = {
  llamacpp: "llama.cpp",
  lmstudio: "lmstudio",
  vllm: "vllm",
};

const RUNTIME_VERSION_PLACEHOLDERS: Record<RuntimeId, string> = {
  llamacpp: "<llama.cpp-build>",
  lmstudio: "<lmstudio-version>",
  vllm: "<vllm-version>",
};

function shellArg(value: string): string {
  return /^[A-Za-z0-9_./:@~<>-]+$/.test(value) ? value : `'${value.replaceAll("'", "'\\''")}'`;
}

function modelFamilyFlag(model: OnrampCatalogModel): string {
  const family = model.family.trim();
  return family === "" ? "<model-family>" : shellArg(family);
}

function modelFilePlaceholder(model: OnrampCatalogModel, quant: OnrampCatalogQuant): string {
  return `<path-to-${sanitizeRunPart(model.slug)}-${sanitizeRunPart(quant.label)}.gguf>`;
}

function hfCacheSnapshotPath(repoId: string, fileName: "tokenizer.json" | "tokenizer_config.json"): string {
  const repoCacheDir = repoId.trim().split("/").filter(Boolean).join("--");
  return `~/.cache/huggingface/hub/models--${repoCacheDir}/snapshots/<revision>/${fileName}`;
}

export function buildRecipe(input: {
  model: OnrampCatalogModel;
  quant: OnrampCatalogQuant;
  runtime: RuntimeProfile;
  hfModelId?: string | null;
  source?: BenchmarkRecipeSource;
}): BenchmarkRecipe {
  const { model, quant, runtime } = input;
  const hfModelId = "hfModelId" in input ? normalizeIdentityRepo(input.hfModelId) : normalizeIdentityRepo(model.id);
  const source = input.source ?? "catalog";
  const runtimeInput = { model, quant, hfModelId };
  const servedModelName = runtime.servedModelName(runtimeInput);
  const outputPath = runOutputPath(model, quant);
  const vllmRepo = hfModelId ?? model.id;
  const vllmCommand = [
    "localbench bench",
    "--runtime vllm",
    `--model-ref hf://${vllmRepo}@<full-40-character-revision>`,
    `--model-id ${model.slug}`,
    "--wsl-distro <wsl-distro>",
    "--vllm-venv <absolute-wsl-vllm-venv>",
    "--suite suite-v1-full-exec-6axis-v1",
    "--bench all",
    "--wsl-venv-python <absolute-wsl-appworld-python>",
    "--appworld-root <absolute-wsl-appworld-root>",
    "--lane bounded-final-v2",
    "--profile auto",
    "--tier standard",
    "--determinism-canary",
    "--seed 1234",
    `--out runs/${sanitizeRunPart(model.slug)}-nvfp4`,
  ].join(" \\\n  ");

  // bounded-final-v2: every model runs the ONE ranked lane. --profile auto introspects the
  // model's own chat template and applies the allowlisted execution profile; no family gate.
  // The [hf] extra ships the template introspection dependency.
  // `cache-tokenizer` pre-caches the tokenizer AND verifies it loads offline: --hf-model-id
  // template introspection is OFFLINE-only (HF_HUB_OFFLINE=1), so a fresh machine fails the
  // run's first seconds without it (clean-room user-journey pass, 2026-07-07).
  // The publishable run recipe must also declare model, runtime, and deterministic sampler identity:
  // the verifier rejects under-declared Option B submissions as model.identity_missing/runtime.identity_missing.
  const setupCommand = [
    LOCALBENCH_INSTALL_COMMAND,
    "localbench fetch-suite --site https://local-bench.ai --suite suite-v1-full-exec-6axis-v1 --accept-suite-terms",
    ...(hfModelId === null ? [] : [`localbench cache-tokenizer ${hfModelId}`]),
  ].join("\n");
  const benchCommand = [
    "localbench run",
    `--endpoint ${runtime.endpoint}`,
    `--model ${servedModelName}`,
    hfModelId === null ? "--gguf-repo-only" : `--hf-model-id ${hfModelId}`,
    "--lane bounded-final-v2",
    "--profile auto",
    "--tier standard",
    "--publishable",
    "--sampler-temperature 0",
    "--sampler-top-k 1",
    "--sampler-seed 1234",
    "--determinism-policy gpu-greedy-single-slot-v1",
    `--model-file ${modelFilePlaceholder(model, quant)}`,
    `--model-family ${modelFamilyFlag(model)}`,
    `--quant-label ${quant.label}`,
    "--model-format gguf",
    ...(hfModelId === null
      ? []
      : [
          `--tokenizer-file ${hfCacheSnapshotPath(hfModelId, "tokenizer.json")}`,
          `--chat-template-file ${hfCacheSnapshotPath(hfModelId, "tokenizer_config.json")}`,
        ]),
    `--runtime-name ${RUNTIME_IDENTITY_NAMES[runtime.id]}`,
    `--runtime-version ${RUNTIME_VERSION_PLACEHOLDERS[runtime.id]}`,
    "--kv-cache-quant f16",
    "--ctx-len-configured 32768",
    "--parallel-slots 1",
    `--out ${outputPath}`,
  ].join(" \\\n  ");

  return {
    installCommand: LOCALBENCH_INSTALL_COMMAND,
    lead: runtime.id === "vllm" ? { kind: "maintainer", command: vllmCommand } : buildOneCommandLead(model, quant, source),
    setupCommand,
    serveCommand: runtime.serveCommand(runtimeInput),
    serveNote: runtime.serveNote(runtimeInput),
    benchCommand,
    submitCommand: `localbench submit run --run ${outputPath}`,
    lane: "bounded-final-v2",
    servedModelName,
    ggufRepo: model.ggufRepo,
    identityMode: hfModelId === null ? "basic" : "full",
    model,
    runtimeId: runtime.id,
  };
}
