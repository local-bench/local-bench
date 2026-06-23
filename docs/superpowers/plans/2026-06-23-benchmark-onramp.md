# "Benchmark a model" On-Ramp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the landing-page Rig-Match Finder with a "Benchmark a model" on-ramp that lets a newcomer pick VRAM + model + runtime and copy a board-comparable 2-step benchmark recipe.

**Architecture:** A new pure-logic module (`web/lib/onramp.ts`) owns recipe generation, VRAM→quant selection, family→reasoning-activation mapping, and catalog querying — all unit-tested. A server function (`getOnrampCatalog` in `web/lib/data.ts`) reads the existing `web/model_catalog.json` at build time, trims it, and passes it as a prop to a thin client component (`web/components/benchmark-onramp.tsx`). No `build_data.py` change, no GPU, no new public asset. The old finder and its two helper components are deleted.

**Tech Stack:** Next.js 16 App Router (static export, `output: "export"`), TypeScript strict (`noUncheckedIndexedAccess`), Zod, Vitest, Tailwind (`bench-*` design tokens).

## Global Constraints

- **Commits are LOCAL only** on branch `suite/v1-quant-wedge`. Never `git push`.
- **Commit ONLY `web/` files** (plus this plan/spec doc under `docs/`). The tree is shared with a CLI agent. Every commit: `git add web/ docs/superpowers/plans/2026-06-23-benchmark-onramp.md`, then run `git diff --cached --name-only` and abort the commit if any staged path is outside `web/` or that doc.
- **Anonymity gate #20:** no operator PII (the name "Michael"/"Russell", any email, "Clarity", "QIC", or personal accounts) in any new file, UI copy, comment, or metadata.
- **No GPU work.** This plan touches only TypeScript/JSON/Python-free files.
- **Board-comparable recipe:** the emitted recipe targets the headline lane — `--lane capped-thinking --tier standard` — and for reasoning models includes `--hf-model-id <hf repo>` and `--reasoning-activation <family map>`. Non-reasoning models emit `--lane answer-only --tier standard` with neither flag.
- **Shell-portable commands:** emit every shell command as a SINGLE line (no backslash line-continuations) so it pastes safely into bash, zsh, PowerShell, and cmd.
- **Naming:** raw JSON stays snake_case (`vram_gb_8k`, `gguf_repo`); derived TS is camelCase (`vramGb8k`, `ggufRepo`).
- **Typography:** middle-dot `·` for inline separators; no em dashes in UI copy.
- **Honest v1 ending:** NO fake "Submit" button. Copy states the run produces a local `my-run.json`; automated upload + server re-score land in v2.
- **Gate before every commit:** from `web/`, run `npm run test` (vitest), `npm run typecheck` (tsc --noEmit), and `npm run build` (next export) — all must pass clean.

## File Structure

| File | Responsibility |
|---|---|
| `web/lib/onramp.ts` (NEW) | Pure logic: types, `RUNTIME_PROFILES`, `reasoningActivationFor`, `recommendedQuantForVram`, `recommendModels`, `listOrgs`, `modelsForOrg`, `buildRecipe`. |
| `web/tests/onramp.test.ts` (NEW) | Unit tests for all of `onramp.ts` + `getOnrampCatalog`. |
| `web/lib/schemas.ts` (MODIFY) | Add tolerant Zod schemas for `model_catalog.json`. |
| `web/lib/data.ts` (MODIFY) | Add `getOnrampCatalog()` (reads + trims `model_catalog.json`). |
| `web/components/copy-button.tsx` (NEW) | Tiny clipboard button. |
| `web/components/benchmark-recipe.tsx` (NEW) | Renders a `BenchmarkRecipe` (two code blocks + notes). |
| `web/components/benchmark-onramp.tsx` (NEW) | Client container: VRAM/model/runtime inputs + recipe. |
| `web/app/page.tsx` (MODIFY) | Swap `<RigMatchFinder>` → `<BenchmarkOnramp>`. |
| `web/components/rig-match-finder.tsx` (DELETE) | Replaced. |
| `web/components/rig-match-finder-row.tsx` (DELETE) | Dead after finder removal. |
| `web/components/rig-match-bounty.tsx` (DELETE) | Dead after finder removal. |
| `web/e2e/home.spec.ts` (MODIFY) | Best-effort: point finder assertions at the on-ramp (e2e is NOT in the gate). |

`web/lib/rig-match.ts` STAYS (its VRAM constants/types are reused here and by the scatter/board). `web/components/local-intelligence-index.tsx` STAYS (constants reused). `web/components/best-variant-*` STAY.

---

### Task 1: On-ramp pure logic (`web/lib/onramp.ts`)

**Files:**
- Create: `web/lib/onramp.ts`
- Test: `web/tests/onramp.test.ts`

**Interfaces:**
- Consumes: `RUNTIME_OVERHEAD_GB` from `web/lib/rig-match.ts`; `QUANT_OPTIONS` from `web/lib/quant.ts`.
- Produces: types `OnrampCatalogModel`, `OnrampCatalogQuant`, `RuntimeProfile`, `RuntimeId`, `ReasoningActivation`, `BenchmarkRecipe`, `RecommendedEntry`; values `RUNTIME_PROFILES`, and functions `reasoningActivationFor`, `recommendedQuantForVram`, `recommendModels`, `listOrgs`, `modelsForOrg`, `buildRecipe`.

- [ ] **Step 1: Write the failing test**

Create `web/tests/onramp.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  RUNTIME_PROFILES,
  buildRecipe,
  listOrgs,
  modelsForOrg,
  recommendModels,
  recommendedQuantForVram,
  reasoningActivationFor,
  type OnrampCatalogModel,
} from "../lib/onramp";

function model(overrides: Partial<OnrampCatalogModel> = {}): OnrampCatalogModel {
  return {
    id: "Qwen/Qwen3-8B",
    slug: "qwen3-8b",
    displayName: "Qwen3 8B",
    family: "Qwen3",
    org: "Qwen",
    paramsB: 8.2,
    reasoningCapable: true,
    license: "apache-2.0",
    ggufRepo: "MaziyarPanahi/Qwen3-8B-GGUF",
    downloads: 11_000_000,
    quants: [
      { label: "Q8_0", vramGb8k: 10.1, fileGb: 8.7, bpw: 8.5 },
      { label: "Q6_K", vramGb8k: 8.2, fileGb: 6.8, bpw: 6.6 },
      { label: "Q4_K_M", vramGb8k: 6.0, fileGb: 5.0, bpw: 4.8 },
    ],
    ...overrides,
  };
}

describe("reasoningActivationFor", () => {
  it("maps known families with confidence", () => {
    expect(reasoningActivationFor({ family: "Qwen3", org: "Qwen" })).toEqual({ activation: "qwen3", confident: true });
    expect(reasoningActivationFor({ family: "Granite 3", org: "IBM" })).toEqual({ activation: "granite", confident: true });
    expect(reasoningActivationFor({ family: "Nemotron", org: "NVIDIA" })).toEqual({ activation: "nemotron", confident: true });
    expect(reasoningActivationFor({ family: "DeepSeek-R1-Distill", org: "DeepSeek" })).toEqual({ activation: "r1", confident: true });
    expect(reasoningActivationFor({ family: "Gemma 4", org: "Google" })).toEqual({ activation: "gemma4", confident: true });
  });

  it("falls back to qwen3 without confidence for unknown families", () => {
    expect(reasoningActivationFor({ family: "Mystery", org: "Acme" })).toEqual({ activation: "qwen3", confident: false });
  });
});

describe("recommendedQuantForVram", () => {
  it("picks the highest-quality quant that fits the budget", () => {
    expect(recommendedQuantForVram(model(), 12)?.label).toBe("Q8_0");
    expect(recommendedQuantForVram(model(), 9)?.label).toBe("Q6_K");
    expect(recommendedQuantForVram(model(), 7)?.label).toBe("Q4_K_M");
  });

  it("returns null when nothing fits", () => {
    expect(recommendedQuantForVram(model(), 4)).toBeNull();
  });

  it("ignores quants with unknown VRAM", () => {
    const m = model({ quants: [{ label: "Q4_K_M", vramGb8k: null, fileGb: 5, bpw: 4.8 }] });
    expect(recommendedQuantForVram(m, 24)).toBeNull();
  });
});

describe("recommendModels", () => {
  it("returns only reasoning models with a GGUF repo and a fitting quant, ranked by downloads, capped", () => {
    const catalog = [
      model({ slug: "a", downloads: 100 }),
      model({ slug: "b", downloads: 900 }),
      model({ slug: "no-gguf", ggufRepo: null, downloads: 5000 }),
      model({ slug: "not-reasoning", reasoningCapable: false, downloads: 5000 }),
      model({ slug: "too-big", downloads: 5000, quants: [{ label: "Q8_0", vramGb8k: 99, fileGb: 80, bpw: 8.5 }] }),
    ];
    const result = recommendModels(catalog, 24, 5);
    expect(result.map((entry) => entry.model.slug)).toEqual(["b", "a"]);
    expect(result.every((entry) => entry.quant.vramGb8k !== null)).toBe(true);
  });

  it("respects the limit", () => {
    const catalog = [model({ slug: "a", downloads: 3 }), model({ slug: "b", downloads: 2 }), model({ slug: "c", downloads: 1 })];
    expect(recommendModels(catalog, 24, 2)).toHaveLength(2);
  });
});

describe("listOrgs / modelsForOrg", () => {
  it("lists unique orgs sorted, and models per org by downloads", () => {
    const catalog = [
      model({ slug: "q1", org: "Qwen", downloads: 1 }),
      model({ slug: "q2", org: "Qwen", downloads: 9 }),
      model({ slug: "g1", org: "Google" }),
    ];
    expect(listOrgs(catalog)).toEqual(["Google", "Qwen"]);
    expect(modelsForOrg(catalog, "Qwen").map((m) => m.slug)).toEqual(["q2", "q1"]);
  });
});

describe("RUNTIME_PROFILES", () => {
  it("exposes four profiles with Ollama recommended", () => {
    expect(RUNTIME_PROFILES.map((p) => p.id)).toEqual(["ollama", "lmstudio", "llamacpp", "vllm"]);
    expect(RUNTIME_PROFILES.find((p) => p.id === "ollama")?.recommended).toBe(true);
    expect(RUNTIME_PROFILES.find((p) => p.id === "ollama")?.endpoint).toBe("http://localhost:11434/v1");
    expect(RUNTIME_PROFILES.find((p) => p.id === "vllm")?.endpoint).toBe("http://localhost:8000/v1");
  });
});

describe("buildRecipe", () => {
  const ollama = RUNTIME_PROFILES.find((p) => p.id === "ollama")!;
  const vllm = RUNTIME_PROFILES.find((p) => p.id === "vllm")!;
  const lmstudio = RUNTIME_PROFILES.find((p) => p.id === "lmstudio")!;

  it("emits a board-comparable capped-thinking recipe for a reasoning model on Ollama", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: ollama });
    expect(recipe.lane).toBe("capped-thinking");
    expect(recipe.servedModelName).toBe("hf.co/MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveCommand).toBe("ollama run hf.co/MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.serveNote).toBeNull();
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:11434/v1");
    expect(recipe.benchCommand).toContain("--model hf.co/MaziyarPanahi/Qwen3-8B-GGUF:Q4_K_M");
    expect(recipe.benchCommand).toContain("--hf-model-id Qwen/Qwen3-8B");
    expect(recipe.benchCommand).toContain("--lane capped-thinking");
    expect(recipe.benchCommand).toContain("--reasoning-activation qwen3");
    expect(recipe.benchCommand).toContain("--tier standard");
    expect(recipe.benchCommand).toContain("--out my-run.json");
    expect(recipe.benchCommand.includes("\n")).toBe(false);
  });

  it("uses the HF model id as the served name for vLLM", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: vllm });
    expect(recipe.servedModelName).toBe("Qwen/Qwen3-8B");
    expect(recipe.serveCommand).toBe("vllm serve Qwen/Qwen3-8B --port 8000");
    expect(recipe.benchCommand).toContain("--endpoint http://localhost:8000/v1");
  });

  it("renders a GUI note instead of a serve command for LM Studio", () => {
    const recipe = buildRecipe({ model: model(), quant: model().quants[2]!, runtime: lmstudio });
    expect(recipe.serveCommand).toBe("");
    expect(recipe.serveNote).toContain("LM Studio");
  });

  it("emits answer-only with no reasoning flags for a non-reasoning model", () => {
    const recipe = buildRecipe({ model: model({ reasoningCapable: false }), quant: model().quants[2]!, runtime: ollama });
    expect(recipe.lane).toBe("answer-only");
    expect(recipe.benchCommand).not.toContain("--hf-model-id");
    expect(recipe.benchCommand).not.toContain("--reasoning-activation");
    expect(recipe.benchCommand).toContain("--lane answer-only");
  });

  it("flags low confidence when the family is unknown", () => {
    const recipe = buildRecipe({ model: model({ family: "Mystery", org: "Acme" }), quant: model().quants[2]!, runtime: ollama });
    expect(recipe.activationConfident).toBe(false);
    expect(recipe.activation).toBe("qwen3");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm run test -- onramp`
Expected: FAIL — `Cannot find module '../lib/onramp'`.

- [ ] **Step 3: Write `web/lib/onramp.ts`**

```ts
import { RUNTIME_OVERHEAD_GB } from "@/lib/rig-match";
import { QUANT_OPTIONS } from "@/lib/quant";

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
```

Note for the implementer: `RUNTIME_OVERHEAD_GB` is imported to keep the VRAM-fit convention aligned with `rig-match.ts`, but the catalog's `vram_gb_8k` is already an at-8k requirement, so `recommendedQuantForVram` compares against it directly (matching how `estimateVramRequirement` uses `vramRequiredGb8k` directly). If your linter flags the import as unused, drop it — do not add overhead double-counting.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npm run test -- onramp`
Expected: PASS (all describe blocks green).

- [ ] **Step 5: Typecheck**

Run: `cd web && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/lib/onramp.ts web/tests/onramp.test.ts
git diff --cached --name-only   # confirm only web/ paths
git commit -m "feat(web): on-ramp recipe + catalog-query logic with tests"
```

---

### Task 2: Catalog loader (`getOnrampCatalog` + schema)

**Files:**
- Modify: `web/lib/schemas.ts` (append catalog schemas)
- Modify: `web/lib/data.ts` (add `getOnrampCatalog`)
- Test: `web/tests/onramp.test.ts` (append a real-catalog test)

**Interfaces:**
- Consumes: `model_catalog.json` at `process.cwd()/model_catalog.json`; types from `web/lib/onramp.ts`.
- Produces: `getOnrampCatalog(): Promise<readonly OnrampCatalogModel[]>`.

- [ ] **Step 1: Write the failing test (append to `web/tests/onramp.test.ts`)**

```ts
import { getOnrampCatalog } from "../lib/data";

describe("getOnrampCatalog", () => {
  it("loads the real catalog and trims it to on-ramp models", async () => {
    const catalog = await getOnrampCatalog();
    expect(catalog.length).toBeGreaterThan(50);
    for (const model of catalog) {
      expect(model.id).toBeTruthy();
      expect(model.slug).toBeTruthy();
      expect(model.quants.length).toBeGreaterThan(0);
    }
    const qwen = catalog.find((model) => model.slug === "qwen3-8b");
    expect(qwen).toBeDefined();
    expect(qwen?.ggufRepo).toBeTruthy();
    expect(qwen?.quants.some((quant) => quant.label === "Q4_K_M")).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npm run test -- onramp`
Expected: FAIL — `getOnrampCatalog` is not exported from `../lib/data`.

- [ ] **Step 3: Append catalog schemas to `web/lib/schemas.ts`**

Add at the end of the file (keep the existing `import { z } from "zod";` — do not duplicate it):

```ts
const CatalogQuantSchema = z
  .object({
    label: z.string(),
    bpw: z.number().nullable().optional(),
    file_gb: z.number().nullable().optional(),
    vram_gb_8k: z.number().nullable().optional(),
  })
  .passthrough();

const CatalogModelSchema = z
  .object({
    id: z.string(),
    slug: z.string(),
    display_name: z.string(),
    family: z.string().nullable().optional(),
    org: z.string().nullable().optional(),
    params_b: z
      .union([
        z.number(),
        z.object({ total_b: z.number().nullable().optional(), active_b: z.number().nullable().optional() }).passthrough(),
      ])
      .nullable()
      .optional(),
    reasoning_capable: z.boolean().nullable().optional(),
    license: z.string().nullable().optional(),
    popularity: z.object({ downloads: z.number().nullable().optional() }).passthrough().nullable().optional(),
    gguf_repo: z.string().nullable().optional(),
    quants: z.array(CatalogQuantSchema),
  })
  .passthrough();

export const CatalogSchema = z.array(CatalogModelSchema);
export type CatalogModel = z.infer<typeof CatalogModelSchema>;
```

- [ ] **Step 4: Add `getOnrampCatalog` to `web/lib/data.ts`**

At the top of the imports, extend the existing `node:path` import to also bring in nothing new (it already imports `join`), and add `CatalogSchema` + `type CatalogModel` to the existing `./schemas` import block, and the on-ramp types to a new import:

```ts
// add to the existing import from "./schemas":
//   CatalogSchema,
//   type CatalogModel,
import type { OnrampCatalogModel } from "./onramp";
```

Then add near the other exported `get*` functions:

```ts
function toOnrampModel(raw: CatalogModel): OnrampCatalogModel {
  const paramsB =
    typeof raw.params_b === "number" ? raw.params_b : raw.params_b ? raw.params_b.total_b ?? null : null;
  return {
    id: raw.id,
    slug: raw.slug,
    displayName: raw.display_name,
    family: raw.family ?? "",
    org: raw.org ?? "",
    paramsB,
    reasoningCapable: raw.reasoning_capable ?? false,
    license: raw.license ?? "",
    ggufRepo: raw.gguf_repo ?? null,
    downloads: raw.popularity?.downloads ?? 0,
    quants: raw.quants.map((quant) => ({
      label: quant.label,
      vramGb8k: quant.vram_gb_8k ?? null,
      fileGb: quant.file_gb ?? null,
      bpw: quant.bpw ?? null,
    })),
  };
}

export async function getOnrampCatalog(): Promise<readonly OnrampCatalogModel[]> {
  const file = await readFile(join(process.cwd(), "model_catalog.json"), "utf8");
  const parsed: unknown = JSON.parse(file);
  const catalog = CatalogSchema.parse(parsed);
  return catalog.filter((raw) => raw.quants.length > 0).map(toOnrampModel);
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd web && npm run test -- onramp`
Expected: PASS, including the real-catalog test.

- [ ] **Step 6: Typecheck**

Run: `cd web && npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add web/lib/schemas.ts web/lib/data.ts web/tests/onramp.test.ts
git diff --cached --name-only
git commit -m "feat(web): getOnrampCatalog loader + tolerant catalog schema"
```

---

### Task 3: On-ramp view components

**Files:**
- Create: `web/components/copy-button.tsx`
- Create: `web/components/benchmark-recipe.tsx`
- Create: `web/components/benchmark-onramp.tsx`

**Interfaces:**
- Consumes: everything exported from `web/lib/onramp.ts`; `VRAM_TIERS` from `web/lib/rig-match.ts`; `QUANT_OPTIONS` from `web/lib/quant.ts`; `LOCAL_INTELLIGENCE_INDEX_NAME`, `LOCAL_INTELLIGENCE_INDEX_QUALIFIER` from `web/components/local-intelligence-index.tsx`.
- Produces: default-less named exports `CopyButton`, `BenchmarkRecipe`, `BenchmarkOnramp`. `BenchmarkOnramp` prop: `{ catalog: readonly OnrampCatalogModel[] }`.

This task has no unit test — the repo unit-tests pure lib functions, not React components (see `web/tests/`), and all logic here is already covered by Task 1. Verification is `tsc` + `next build` + the data-testids the e2e/Task 4 rely on. Do not introduce Testing Library.

- [ ] **Step 1: Create `web/components/copy-button.tsx`**

```tsx
"use client";

import { useState } from "react";

export function CopyButton({ value, label = "Copy" }: { readonly value: string; readonly label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="rounded border border-bench-line px-2 py-1 font-mono text-[11px] uppercase text-bench-muted transition-colors hover:border-bench-accent hover:text-bench-accent"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}
```

- [ ] **Step 2: Create `web/components/benchmark-recipe.tsx`**

```tsx
import { CopyButton } from "@/components/copy-button";
import type { BenchmarkRecipe as Recipe } from "@/lib/onramp";

function CommandBlock({ title, command }: { readonly title: string; readonly command: string }) {
  return (
    <div className="rounded border border-bench-line bg-bench-panel-2/70">
      <div className="flex items-center justify-between gap-3 border-b border-bench-line px-3 py-2">
        <span className="font-mono text-[11px] uppercase text-bench-muted">{title}</span>
        <CopyButton value={command} />
      </div>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-xs leading-6 text-bench-text">{command}</pre>
    </div>
  );
}

export function BenchmarkRecipe({ recipe }: { readonly recipe: Recipe }) {
  return (
    <div className="mt-5 flex flex-col gap-3" data-testid="benchmark-recipe">
      <p className="font-mono text-xs text-bench-muted">
        localbench does not download or run the model. First start a local server, then localbench sends the benchmark to
        that endpoint.
      </p>
      {recipe.serveCommand ? (
        <CommandBlock title="Step 1 · start the model (leave running)" command={recipe.serveCommand} />
      ) : (
        <div className="rounded border border-bench-line bg-bench-panel-2/70 px-3 py-3 text-sm leading-6 text-bench-muted">
          <span className="font-mono text-[11px] uppercase text-bench-muted">Step 1 · start the model</span>
          <p className="mt-1">{recipe.serveNote}</p>
        </div>
      )}
      {recipe.serveCommand && recipe.serveNote ? (
        <p className="font-mono text-[11px] text-bench-muted">{recipe.serveNote}</p>
      ) : null}
      <CommandBlock title="Step 2 · benchmark it (second terminal)" command={recipe.benchCommand} />
      {recipe.lane === "capped-thinking" && !recipe.activationConfident ? (
        <p className="rounded border border-bench-warn/35 bg-bench-warn/10 p-2 font-mono text-[11px] text-bench-warn">
          Reasoning activation defaulted to qwen3 · confirm the right --reasoning-activation for this model family before
          you rely on the result.
        </p>
      ) : null}
      <p className="font-mono text-[11px] leading-5 text-bench-muted">
        Do not change sampling, context, or prompt-template settings unless the recipe says so. VRAM tiers are
        recommendations, not guaranteed fits · close other GPU workloads.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Create `web/components/benchmark-onramp.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { BenchmarkRecipe } from "@/components/benchmark-recipe";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import {
  RUNTIME_PROFILES,
  buildRecipe,
  listOrgs,
  modelsForOrg,
  recommendModels,
  recommendedQuantForVram,
  type OnrampCatalogModel,
  type OnrampCatalogQuant,
  type RuntimeId,
} from "@/lib/onramp";
import { VRAM_TIERS } from "@/lib/rig-match";
import { QUANT_OPTIONS } from "@/lib/quant";

type PickMode = "recommended" | "browse" | "paste";

const DEFAULT_VRAM = 24;
const PASTE_QUANT_DEFAULT = "Q4_K_M";

function syntheticPasteModel(repo: string, quantLabel: string): OnrampCatalogModel {
  const trimmed = repo.trim();
  return {
    id: trimmed,
    slug: trimmed,
    displayName: trimmed,
    family: "",
    org: "",
    paramsB: null,
    reasoningCapable: true,
    license: "",
    ggufRepo: trimmed,
    downloads: 0,
    quants: [{ label: quantLabel, vramGb8k: null, fileGb: null, bpw: null }],
  };
}

export function BenchmarkOnramp({ catalog }: { readonly catalog: readonly OnrampCatalogModel[] }) {
  const [vramGb, setVramGb] = useState<number>(DEFAULT_VRAM);
  const [mode, setMode] = useState<PickMode>("recommended");
  const [runtimeId, setRuntimeId] = useState<RuntimeId>("ollama");
  const [recommendedSlug, setRecommendedSlug] = useState<string | null>(null);
  const [browseOrg, setBrowseOrg] = useState<string>("");
  const [browseSlug, setBrowseSlug] = useState<string>("");
  const [browseQuant, setBrowseQuant] = useState<string>("");
  const [pasteRepo, setPasteRepo] = useState<string>("");
  const [pasteQuant, setPasteQuant] = useState<string>(PASTE_QUANT_DEFAULT);

  const orgs = useMemo(() => listOrgs(catalog), [catalog]);
  const recommended = useMemo(() => recommendModels(catalog, vramGb, 5), [catalog, vramGb]);
  const orgModels = useMemo(() => (browseOrg ? modelsForOrg(catalog, browseOrg) : []), [catalog, browseOrg]);
  const runtime = RUNTIME_PROFILES.find((profile) => profile.id === runtimeId) ?? RUNTIME_PROFILES[0]!;

  const selection = useMemo<{ model: OnrampCatalogModel; quant: OnrampCatalogQuant } | null>(() => {
    if (mode === "recommended") {
      const entry = recommended.find((candidate) => candidate.model.slug === recommendedSlug) ?? recommended[0];
      return entry ? { model: entry.model, quant: entry.quant } : null;
    }
    if (mode === "browse") {
      const model = catalog.find((candidate) => candidate.slug === browseSlug);
      if (!model) {
        return null;
      }
      const quant =
        model.quants.find((candidate) => candidate.label === browseQuant) ??
        recommendedQuantForVram(model, vramGb) ??
        model.quants[0];
      return quant ? { model, quant } : null;
    }
    if (pasteRepo.trim() === "") {
      return null;
    }
    const model = syntheticPasteModel(pasteRepo, pasteQuant);
    return { model, quant: model.quants[0]! };
  }, [mode, recommended, recommendedSlug, catalog, browseSlug, browseQuant, vramGb, pasteRepo, pasteQuant]);

  const recipe = selection ? buildRecipe({ model: selection.model, quant: selection.quant, runtime }) : null;

  return (
    <section data-testid="benchmark-onramp" className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20">
      <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Benchmark a model</p>
      <h2 className="mt-2 text-3xl font-semibold text-bench-text">Start a benchmark in about a minute</h2>
      <p className="mt-1 font-mono text-xs text-bench-muted">
        {LOCAL_INTELLIGENCE_INDEX_NAME} · {LOCAL_INTELLIGENCE_INDEX_QUALIFIER}
      </p>
      <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
        Pick your VRAM, choose a model, and copy the recipe. It produces a board-comparable run on your own hardware.
      </p>

      <div className="mt-5 grid gap-4 lg:grid-cols-[170px_1fr_170px]">
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted" htmlFor="onramp-vram">
          I have
          <select
            id="onramp-vram"
            className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent"
            value={vramGb}
            onChange={(event) => setVramGb(Number(event.currentTarget.value))}
          >
            {VRAM_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier} GB VRAM
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-col gap-2">
          <div className="inline-flex w-fit rounded border border-bench-line bg-bench-panel-2 p-1" role="group" aria-label="How to choose a model">
            {(["recommended", "browse", "paste"] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={[
                  "rounded px-3 py-1.5 text-sm font-semibold transition-colors",
                  mode === value ? "bg-bench-accent text-bench-bg" : "text-bench-muted hover:text-bench-text",
                ].join(" ")}
                onClick={() => setMode(value)}
              >
                {value === "recommended" ? "Recommended" : value === "browse" ? "Browse catalog" : "Paste HF repo"}
              </button>
            ))}
          </div>
          <ModelPicker
            mode={mode}
            recommended={recommended}
            recommendedSlug={recommendedSlug}
            onRecommended={setRecommendedSlug}
            orgs={orgs}
            browseOrg={browseOrg}
            onOrg={(org) => {
              setBrowseOrg(org);
              setBrowseSlug("");
            }}
            orgModels={orgModels}
            browseSlug={browseSlug}
            onModel={setBrowseSlug}
            browseQuant={browseQuant}
            onQuant={setBrowseQuant}
            pasteRepo={pasteRepo}
            onPasteRepo={setPasteRepo}
            pasteQuant={pasteQuant}
            onPasteQuant={setPasteQuant}
          />
        </div>

        <label className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted" htmlFor="onramp-runtime">
          Runtime
          <select
            id="onramp-runtime"
            className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent"
            value={runtimeId}
            onChange={(event) => setRuntimeId(event.currentTarget.value as RuntimeId)}
          >
            {RUNTIME_PROFILES.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.label}
                {profile.recommended ? " (recommended)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      {recipe ? <BenchmarkRecipe recipe={recipe} /> : <EmptyRecipe mode={mode} />}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded border border-bench-line bg-bench-panel-2/60 p-3 text-sm text-bench-muted">
        <span>
          v1 produces a local <span className="font-mono text-bench-text">my-run.json</span>. Automated upload and server
          re-score land in v2.
        </span>
        <Link href="/leaderboard" className="font-semibold text-bench-accent hover:underline">
          Just exploring? See the board →
        </Link>
      </div>
    </section>
  );
}

function EmptyRecipe({ mode }: { readonly mode: PickMode }) {
  return (
    <div className="mt-5 rounded border border-bench-line bg-bench-panel-2/70 p-5 text-sm leading-6 text-bench-muted">
      {mode === "paste" ? "Paste a Hugging Face GGUF repo (owner/repo) to generate a recipe." : "Pick a model to generate a recipe."}
    </div>
  );
}

function ModelPicker(props: {
  readonly mode: PickMode;
  readonly recommended: readonly { model: OnrampCatalogModel; quant: OnrampCatalogQuant }[];
  readonly recommendedSlug: string | null;
  readonly onRecommended: (slug: string) => void;
  readonly orgs: readonly string[];
  readonly browseOrg: string;
  readonly onOrg: (org: string) => void;
  readonly orgModels: readonly OnrampCatalogModel[];
  readonly browseSlug: string;
  readonly onModel: (slug: string) => void;
  readonly browseQuant: string;
  readonly onQuant: (label: string) => void;
  readonly pasteRepo: string;
  readonly onPasteRepo: (value: string) => void;
  readonly pasteQuant: string;
  readonly onPasteQuant: (value: string) => void;
}) {
  const selectClass =
    "rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent";

  if (props.mode === "recommended") {
    if (props.recommended.length === 0) {
      return <p className="font-mono text-xs text-bench-muted">No known-good reasoning model fits this VRAM yet · try Browse or a larger tier.</p>;
    }
    const activeSlug = props.recommendedSlug ?? props.recommended[0]!.model.slug;
    return (
      <div className="flex flex-col gap-2">
        {props.recommended.map((entry) => (
          <button
            key={entry.model.slug}
            type="button"
            onClick={() => props.onRecommended(entry.model.slug)}
            className={[
              "flex items-center justify-between gap-3 rounded border px-3 py-2 text-left text-sm transition-colors",
              entry.model.slug === activeSlug
                ? "border-bench-accent bg-bench-accent/10 text-bench-text"
                : "border-bench-line text-bench-muted hover:border-bench-accent/60",
            ].join(" ")}
          >
            <span className="font-semibold text-bench-text">{entry.model.displayName}</span>
            <span className="font-mono text-[11px] text-bench-muted">{entry.quant.label}</span>
          </button>
        ))}
      </div>
    );
  }

  if (props.mode === "browse") {
    return (
      <div className="grid gap-2 sm:grid-cols-3">
        <select className={selectClass} aria-label="Lab" value={props.browseOrg} onChange={(event) => props.onOrg(event.currentTarget.value)}>
          <option value="">Lab…</option>
          {props.orgs.map((org) => (
            <option key={org} value={org}>
              {org}
            </option>
          ))}
        </select>
        <select className={selectClass} aria-label="Model" value={props.browseSlug} onChange={(event) => props.onModel(event.currentTarget.value)} disabled={props.orgModels.length === 0}>
          <option value="">Model…</option>
          {props.orgModels.map((model) => (
            <option key={model.slug} value={model.slug}>
              {model.displayName}
            </option>
          ))}
        </select>
        <select className={selectClass} aria-label="Quant" value={props.browseQuant} onChange={(event) => props.onQuant(event.currentTarget.value)}>
          <option value="">Quant (auto)</option>
          {QUANT_OPTIONS.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_140px]">
      <input
        type="text"
        className={selectClass}
        placeholder="owner/repo-GGUF"
        aria-label="Hugging Face GGUF repo"
        value={props.pasteRepo}
        onChange={(event) => props.onPasteRepo(event.currentTarget.value)}
      />
      <select className={selectClass} aria-label="Quant" value={props.pasteQuant} onChange={(event) => props.onPasteQuant(event.currentTarget.value)}>
        {QUANT_OPTIONS.map((label) => (
          <option key={label} value={label}>
            {label}
          </option>
        ))}
      </select>
      <p className="font-mono text-[11px] text-bench-muted sm:col-span-2">
        Experimental · we have not validated this repo has a compatible GGUF, template, or license · results may not be
        comparable.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd web && npm run typecheck`
Expected: no errors. (If `noUncheckedIndexedAccess` flags any `recommended[0]`/`RUNTIME_PROFILES[0]` access, the `!` assertions above already guard them — keep them.)

- [ ] **Step 5: Build (smoke — old finder still on the page, on-ramp not yet wired)**

Run: `cd web && npm run build`
Expected: success. The component compiles even though it is not yet rendered.

- [ ] **Step 6: Commit**

```bash
git add web/components/copy-button.tsx web/components/benchmark-recipe.tsx web/components/benchmark-onramp.tsx
git diff --cached --name-only
git commit -m "feat(web): benchmark on-ramp view components"
```

---

### Task 4: Wire the on-ramp + delete the finder

**Files:**
- Modify: `web/app/page.tsx`
- Delete: `web/components/rig-match-finder.tsx`, `web/components/rig-match-finder-row.tsx`, `web/components/rig-match-bounty.tsx`
- Modify: `web/e2e/home.spec.ts` (best-effort, not gated)

**Interfaces:**
- Consumes: `getOnrampCatalog` from `web/lib/data.ts`; `BenchmarkOnramp` from `web/components/benchmark-onramp.tsx`.

- [ ] **Step 1: Replace the finder in `web/app/page.tsx`**

Rewrite the file to:

```tsx
import Link from "next/link";
import { BenchmarkOnramp } from "@/components/benchmark-onramp";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { getHomePageData, getOnrampCatalog } from "@/lib/data";
import { selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, rigCandidates } = await getHomePageData();
  const catalog = await getOnrampCatalog();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates);

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
      <BestVariantTable points={bestVariantPoints} />
      <BenchmarkOnramp catalog={catalog} />
      <Link
        href="/leaderboard"
        className="rounded-lg border border-bench-line bg-bench-panel/82 px-5 py-4 text-center font-semibold text-bench-text transition-colors hover:border-bench-accent hover:text-bench-accent"
      >
        View full leaderboard →
      </Link>
    </main>
  );
}
```

- [ ] **Step 2: Delete the three finder files**

```bash
git rm web/components/rig-match-finder.tsx web/components/rig-match-finder-row.tsx web/components/rig-match-bounty.tsx
```

- [ ] **Step 3: Confirm no dangling imports**

Run: `cd web && grep -rn "rig-match-finder\|rig-match-bounty\|RigMatchFinder\|RigMatchBounty\|FinderRow" app components lib`
Expected: no matches in `app/`, `components/`, or `lib/`. (Matches in `e2e/` are handled in Step 5; matches in `lib/rig-match.ts` for the SHARED types `RigMatchCandidate`/`RigMatchAnchor`/`rankRigMatches` are expected and fine — only the FINDER identifiers must be gone.)

- [ ] **Step 4: Typecheck + test + build**

Run: `cd web && npm run typecheck && npm run test && npm run build`
Expected: all pass. Build still emits the full set of static pages (home renders the on-ramp; the page count should be unchanged from before this plan, since no routes were added or removed).

- [ ] **Step 5: Best-effort e2e selector update (`web/e2e/home.spec.ts`)**

Open the file. Replace any assertion that locates `[data-testid="rig-match-finder"]` / `[data-testid="rig-match-results"]` with `[data-testid="benchmark-onramp"]` and a basic visibility check; delete assertions about finder rows/quant filtering that no longer have an equivalent. Do NOT add new behavioral coverage. e2e is not part of the gate (`npm run test` runs vitest only), so this step is best-effort; if the spec is too stale to adapt cleanly, replace its body with a single `await expect(page.getByTestId("benchmark-onramp")).toBeVisible();` and leave a `// TODO: refresh e2e coverage for the on-ramp` comment.

- [ ] **Step 6: Commit**

```bash
git add web/app/page.tsx web/e2e/home.spec.ts
git add -u web/components   # stages the three deletions
git diff --cached --name-only
git commit -m "feat(web): swap landing finder for the benchmark on-ramp"
```

---

## Post-plan verification (controller, after Task 4)

- [ ] From `web/`: `npm run test && npm run typecheck && npm run build` all clean.
- [ ] Anonymity re-check: `cd web && grep -rni "michael\|russell\|clarity\|qic\|mj_russell" app components lib public/data 2>/dev/null` → no operator PII (matches inside model names/licenses unrelated to the operator are fine; there should be none).
- [ ] Manual render check (optional, no GPU): `npm run dev`, open `/`, confirm the on-ramp shows VRAM/model/runtime, a recommended model is preselected at 24 GB, and the Ollama recipe contains `--lane capped-thinking --reasoning-activation qwen3 --hf-model-id`.
- [ ] Confirm `/leaderboard`, `/methodology`, model and run pages still build and render (the shared `rig-match.ts` types are untouched).
