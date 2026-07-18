"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ModelPicker, type PickMode } from "@/components/benchmark-model-picker";
import { BenchmarkRecipe } from "@/components/benchmark-recipe";
import {
  RUNTIME_PROFILES,
  browseFamilies,
  buildRecipe,
  estimateBenchmarkTime,
  listBaseLabs,
  popularModels,
  recommendedQuantForVram,
  smallestFileQuant,
  type BenchmarkTimeEstimate,
  type OnrampCatalogModel,
  type OnrampCatalogQuant,
  type PopularitySort,
  type RuntimeId,
} from "@/lib/onramp";
import { VRAM_TIERS } from "@/lib/rig-match";

const DEFAULT_VRAM = 24;
const PASTE_QUANT_DEFAULT = "Q4_K_M";

function repoNameSegment(repo: string): string {
  const segments = repo.trim().split("/").filter((segment) => segment !== "");
  return segments[segments.length - 1] ?? repo.trim();
}

function slugFromRepoName(repo: string): string {
  const sanitized = repoNameSegment(repo).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return sanitized === "" ? "pasted-model" : sanitized;
}

function normalizeOptionalRepo(repo: string): string | null {
  const trimmed = repo.trim();
  return trimmed === "" ? null : trimmed;
}

function syntheticPasteModel(repo: string, quantLabel: string): OnrampCatalogModel {
  const trimmed = repo.trim();
  return {
    id: trimmed,
    slug: slugFromRepoName(trimmed),
    displayName: trimmed,
    family: "",
    org: "",
    paramsB: null,
    reasoningCapable: true,
    license: "",
    ggufRepo: trimmed,
    downloads: 0,
    likes: 0,
    trending: 0,
    modelKind: "base",
    baseModelIds: [],
    baseModelId: null,
    baseModelSlug: null,
    baseModelDisplayName: null,
    quants: [{ label: quantLabel, vramGb8k: null, fileGb: null, bpw: null }],
  };
}

function isRuntimeId(value: string): value is RuntimeId {
  return RUNTIME_PROFILES.some((profile) => profile.id === value);
}

export function BenchmarkOnramp({
  catalog,
  popularityAsOf,
}: {
  readonly catalog: readonly OnrampCatalogModel[];
  readonly popularityAsOf: string | null;
}) {
  const [vramGb, setVramGb] = useState<number>(DEFAULT_VRAM);
  const [mode, setMode] = useState<PickMode>("popular");
  const [popularitySort, setPopularitySort] = useState<PopularitySort>("downloads");
  const [runtimeId, setRuntimeId] = useState<RuntimeId>("llamacpp");
  const [popularSlug, setPopularSlug] = useState<string | null>(null);
  const [browseOrg, setBrowseOrg] = useState<string>("");
  const [browseSearch, setBrowseSearch] = useState<string>("");
  const [browseSlug, setBrowseSlug] = useState<string>("");
  const [browseQuant, setBrowseQuant] = useState<string>("");
  const [pasteRepo, setPasteRepo] = useState<string>("");
  const [pasteHfModelId, setPasteHfModelId] = useState<string>("");
  const [pasteQuant, setPasteQuant] = useState<string>(PASTE_QUANT_DEFAULT);

  const orgs = useMemo(() => listBaseLabs(catalog), [catalog]);
  const popular = useMemo(() => popularModels(catalog, vramGb, popularitySort, 5), [catalog, vramGb, popularitySort]);
  const families = useMemo(
    () =>
      browseOrg === "" && browseSearch.trim() === ""
        ? []
        : browseFamilies(catalog, { lab: browseOrg, search: browseSearch, vramGb }),
    [catalog, browseOrg, browseSearch, vramGb],
  );
  const browseModel = useMemo(
    () => catalog.find((candidate) => candidate.slug === browseSlug) ?? null,
    [catalog, browseSlug],
  );
  const runtime = RUNTIME_PROFILES.find((profile) => profile.id === runtimeId) ?? RUNTIME_PROFILES[0];

  const selection = useMemo<
    | { readonly model: OnrampCatalogModel; readonly quant: OnrampCatalogQuant }
    | { readonly model: OnrampCatalogModel; readonly quant: OnrampCatalogQuant; readonly hfModelId: string | null }
    | null
  >(() => {
    if (mode === "popular") {
      const entry = popular.find((candidate) => candidate.model.slug === popularSlug) ?? popular[0];
      return entry ? { model: entry.model, quant: entry.quant } : null;
    }
    if (mode === "browse") {
      const found = catalog.find((candidate) => candidate.slug === browseSlug);
      if (!found) {
        return null;
      }
      const explicitQuant = browseQuant === "" ? undefined : found.quants.find((candidate) => candidate.label === browseQuant);
      const quant = explicitQuant ?? recommendedQuantForVram(found, vramGb) ?? smallestFileQuant(found);
      return quant ? { model: found, quant } : null;
    }
    if (pasteRepo.trim() === "") {
      return null;
    }
    const synthetic = syntheticPasteModel(pasteRepo, pasteQuant);
    const quant = synthetic.quants[0];
    return quant === undefined ? null : { model: synthetic, quant, hfModelId: normalizeOptionalRepo(pasteHfModelId) };
  }, [mode, popular, popularSlug, catalog, browseSlug, browseQuant, vramGb, pasteRepo, pasteQuant, pasteHfModelId]);

  const recipe =
    selection && runtime
      ? "hfModelId" in selection
        ? buildRecipe({ model: selection.model, quant: selection.quant, runtime, hfModelId: selection.hfModelId, source: "paste" })
        : buildRecipe({ model: selection.model, quant: selection.quant, runtime })
      : null;
  const timeEstimate = selection === null ? null : estimateBenchmarkTime(selection.model, selection.quant);

  return (
    <section data-testid="benchmark-onramp" className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Benchmark a model</p>
          <h2 className="mt-1 text-2xl font-semibold text-bench-text">Pick a model, get the exact commands</h2>
        </div>
      </div>
      <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
        Choose your VRAM, model, and runtime. The public command runs the five non-agentic axes with
        <code className="font-mono text-bench-text"> --static-only</code>; full six-axis execution currently requires a
        managed AppWorld harness.
      </p>

      <div className="mt-5 grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[170px_minmax(0,1fr)_220px]">
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
            {(["popular", "browse", "paste"] as const).map((value) => (
              <button
                key={value}
                type="button"
                className={[
                  "rounded px-3 py-1.5 text-sm font-semibold transition-colors",
                  mode === value ? "bg-bench-accent text-bench-bg" : "text-bench-muted hover:text-bench-text",
                ].join(" ")}
                onClick={() => setMode(value)}
              >
                {value === "popular" ? "Popular" : value === "browse" ? "Browse catalog" : "Paste HF repo"}
              </button>
            ))}
          </div>
          <ModelPicker
            mode={mode}
            popular={popular}
            popularSlug={popularSlug}
            onPopular={setPopularSlug}
            popularitySort={popularitySort}
            onPopularitySort={setPopularitySort}
            vramGb={vramGb}
            popularityAsOf={popularityAsOf}
            orgs={orgs}
            browseOrg={browseOrg}
            onOrg={(org) => {
              setBrowseOrg(org);
              setBrowseSlug("");
              setBrowseQuant("");
            }}
            browseSearch={browseSearch}
            onBrowseSearch={setBrowseSearch}
            families={families}
            browseSlug={browseSlug}
            browseModel={browseModel}
            onModel={(slug) => {
              setBrowseSlug(slug);
              setBrowseQuant("");
            }}
            browseQuant={browseQuant}
            onQuant={setBrowseQuant}
            pasteRepo={pasteRepo}
            onPasteRepo={setPasteRepo}
            pasteHfModelId={pasteHfModelId}
            onPasteHfModelId={setPasteHfModelId}
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
            onChange={(event) => {
              const value = event.currentTarget.value;
              if (isRuntimeId(value)) {
                setRuntimeId(value);
              }
            }}
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

      {timeEstimate === null ? null : <BenchmarkTimeCallout estimate={timeEstimate} />}
      {recipe ? <BenchmarkRecipe recipe={recipe} /> : <EmptyRecipe mode={mode} />}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded border border-bench-line bg-bench-panel-2/60 p-3 text-sm text-bench-muted">
        <span>
          Public recipes use the measured/static suite. Full six-axis runs fail fast unless the managed AppWorld flags are
          configured. Submissions are signed and reviewed before anything publishes —{" "}
          <Link href="/submit" className="text-bench-accent underline">
            how to submit
          </Link>{" "}
          has the full loop and what the trust labels mean.
        </span>
        <Link href="/leaderboard" className="font-semibold text-bench-accent hover:underline">
          Just exploring? See the board →
        </Link>
      </div>
    </section>
  );
}

function BenchmarkTimeCallout({ estimate }: { readonly estimate: BenchmarkTimeEstimate }) {
  return (
    <div
      data-testid="benchmark-time-estimate"
      className="mt-5 rounded border border-bench-warn/45 bg-bench-warn/10 px-4 py-3 text-sm leading-6 text-bench-muted"
    >
      <p className="font-mono text-[11px] font-semibold uppercase text-bench-warn">Estimated full-run wall time</p>
      <p className="mt-1 text-bench-text">
        {estimate.kind === "range" ? (
          <>
            <span className="font-mono text-base font-semibold text-bench-warn">{estimate.label}</span>{" "}
            <span className="text-bench-muted">about {estimate.pointHours}h midpoint</span>
          </>
        ) : (
          <span className="font-mono text-base font-semibold text-bench-warn">{estimate.label}</span>
        )}
      </p>
      <p className="mt-1">
        Estimate is calibrated from full 6-axis bounded-final-v2 ranked runs on an RTX 5090-class GPU. Slower GPUs or
        partial CPU offload can take several times longer.
      </p>
    </div>
  );
}

function EmptyRecipe({ mode }: { readonly mode: PickMode }) {
  return (
    <div className="mt-5 rounded border border-bench-line bg-bench-panel-2/70 p-5 text-sm leading-6 text-bench-muted">
      {mode === "paste" ? "Paste a Hugging Face GGUF repo (owner/repo) to generate a recipe." : "Pick a model to generate a recipe."}
    </div>
  );
}
