"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ModelPicker, type PickMode } from "@/components/benchmark-model-picker";
import { BenchmarkRecipe } from "@/components/benchmark-recipe";
import { estimateBenchTime, formatBenchTimeRange, type BenchTimeEstimate } from "@/lib/bench-time-estimate";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import {
  RUNTIME_PROFILES,
  buildRecipe,
  listOrgs,
  modelsForOrg,
  popularModels,
  recommendedQuantForVram,
  type OnrampCatalogModel,
  type OnrampCatalogQuant,
  type RuntimeId,
} from "@/lib/onramp";
import { VRAM_TIERS } from "@/lib/rig-match";

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

function isRuntimeId(value: string): value is RuntimeId {
  return RUNTIME_PROFILES.some((profile) => profile.id === value);
}

export function BenchmarkOnramp({ catalog }: { readonly catalog: readonly OnrampCatalogModel[] }) {
  const [vramGb, setVramGb] = useState<number>(DEFAULT_VRAM);
  const [mode, setMode] = useState<PickMode>("popular");
  const [runtimeId, setRuntimeId] = useState<RuntimeId>("llamacpp");
  const [popularSlug, setPopularSlug] = useState<string | null>(null);
  const [browseOrg, setBrowseOrg] = useState<string>("");
  const [browseSlug, setBrowseSlug] = useState<string>("");
  const [browseQuant, setBrowseQuant] = useState<string>("");
  const [pasteRepo, setPasteRepo] = useState<string>("");
  const [pasteQuant, setPasteQuant] = useState<string>(PASTE_QUANT_DEFAULT);

  const orgs = useMemo(() => listOrgs(catalog), [catalog]);
  const popular = useMemo(() => popularModels(catalog, vramGb, 5), [catalog, vramGb]);
  const orgModels = useMemo(() => (browseOrg ? modelsForOrg(catalog, browseOrg) : []), [catalog, browseOrg]);
  const runtime = RUNTIME_PROFILES.find((profile) => profile.id === runtimeId) ?? RUNTIME_PROFILES[0];

  const selection = useMemo<{ model: OnrampCatalogModel; quant: OnrampCatalogQuant } | null>(() => {
    if (mode === "popular") {
      const entry = popular.find((candidate) => candidate.model.slug === popularSlug) ?? popular[0];
      return entry ? { model: entry.model, quant: entry.quant } : null;
    }
    if (mode === "browse") {
      const found = catalog.find((candidate) => candidate.slug === browseSlug);
      if (!found) {
        return null;
      }
      const quant =
        found.quants.find((candidate) => candidate.label === browseQuant) ??
        recommendedQuantForVram(found, vramGb) ??
        found.quants[0];
      return quant ? { model: found, quant } : null;
    }
    if (pasteRepo.trim() === "") {
      return null;
    }
    const synthetic = syntheticPasteModel(pasteRepo, pasteQuant);
    const quant = synthetic.quants[0];
    return quant === undefined ? null : { model: synthetic, quant };
  }, [mode, popular, popularSlug, catalog, browseSlug, browseQuant, vramGb, pasteRepo, pasteQuant]);

  const recipe = selection && runtime ? buildRecipe({ model: selection.model, quant: selection.quant, runtime }) : null;
  const benchTime = selection
    ? estimateBenchTime({
        fileGb: selection.quant.fileGb,
        paramsB: selection.model.paramsB,
        bpw: selection.quant.bpw,
        vramGb8k: selection.quant.vramGb8k,
        vramGb,
      })
    : null;

  return (
    <section data-testid="benchmark-onramp" className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Benchmark a model</p>
          <h2 className="mt-1 text-2xl font-semibold text-bench-text">Pick a model, get the exact commands</h2>
          <p className="mt-1 font-mono text-xs text-bench-muted">
            {LOCAL_INTELLIGENCE_INDEX_NAME} · {LOCAL_INTELLIGENCE_INDEX_QUALIFIER}
          </p>
        </div>
        <BenchTimePanel estimate={benchTime} hasSelection={selection !== null} vramGb={vramGb} />
      </div>
      <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
        Choose your VRAM, model, and runtime — the recipe is the exact pinned command sequence for a run you can submit to
        this board. Every model runs the same ranked lane: the CLI reads the model&apos;s own chat template, gives
        reasoning models a fixed thinking budget inside the shared token cap, and runs everything else answer-only.
      </p>

      <div className="mt-5 grid gap-4 lg:grid-cols-[170px_minmax(0,1fr)_220px]">
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

      {recipe ? <BenchmarkRecipe recipe={recipe} /> : <EmptyRecipe mode={mode} />}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded border border-bench-line bg-bench-panel-2/60 p-3 text-sm text-bench-muted">
        <span>
          Every command is pinned to the frozen v1 suite. Submissions are signed with a key generated on your machine and
          reviewed before anything publishes —{" "}
          <Link href="/submit" className="text-bench-accent hover:underline">
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

function BenchTimePanel({
  estimate,
  hasSelection,
  vramGb,
}: {
  readonly estimate: BenchTimeEstimate | null;
  readonly hasSelection: boolean;
  readonly vramGb: number;
}) {
  return (
    <div
      data-testid="bench-time-estimate"
      title="Scaled from measured board runs by model size and typical memory bandwidth for your VRAM tier — actual time varies with hardware and verbosity. Mixture-of-experts models typically finish several times faster than shown."
      className="rounded border border-bench-line bg-bench-panel-2 px-4 py-3"
    >
      <p className="font-mono text-[11px] uppercase tracking-wide text-bench-muted">Estimated benchmark time</p>
      {estimate === null ? (
        <>
          <p className="mt-1 font-mono text-xl text-bench-muted">{hasSelection ? "—" : "pick a model"}</p>
          <p className="mt-0.5 text-xs text-bench-muted">
            {/* Mirrors the picker's soft fits language — the recipe still renders. */}
            {hasSelection ? `won't fit in ${vramGb} GB at 8K context` : "full five-axis suite"}
          </p>
        </>
      ) : (
        <>
          <p className="mt-1 font-mono text-xl text-bench-text">
            {formatBenchTimeRange(estimate.lowSeconds, estimate.highSeconds)}
            {estimate.rough ? <span className="ml-1.5 text-sm text-bench-muted">(rough)</span> : null}
          </p>
          <p className="mt-0.5 text-xs text-bench-muted">full five-axis suite on your {vramGb} GB tier</p>
        </>
      )}
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
