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
  popularModels,
  recommendedQuantForVram,
  type OnrampCatalogModel,
  type OnrampCatalogQuant,
  type RuntimeId,
} from "@/lib/onramp";
import { VRAM_TIERS } from "@/lib/rig-match";
import { QUANT_OPTIONS } from "@/lib/quant";

type PickMode = "popular" | "browse" | "paste";

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
  const runtime = RUNTIME_PROFILES.find((profile) => profile.id === runtimeId) ?? RUNTIME_PROFILES[0]!;

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
    return { model: synthetic, quant: synthetic.quants[0]! };
  }, [mode, popular, popularSlug, catalog, browseSlug, browseQuant, vramGb, pasteRepo, pasteQuant]);

  const recipe = selection ? buildRecipe({ model: selection.model, quant: selection.quant, runtime }) : null;

  return (
    <section data-testid="benchmark-onramp" className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20">
      <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Benchmark a model · preview</p>
      <h2 className="mt-2 text-3xl font-semibold text-bench-text">Get the recipe to benchmark a model</h2>
      <p className="mt-1 font-mono text-xs text-bench-muted">
        {LOCAL_INTELLIGENCE_INDEX_NAME} · {LOCAL_INTELLIGENCE_INDEX_QUALIFIER}
      </p>
      <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
        Pick your VRAM and a model to get the exact benchmark command. The board ranks Qwen3 and Gemma families today; the
        v1 suite the recipe needs, and one-step submission, ship with v2.
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
          Preview of the contribution flow · the recipe is the real command, pinned to the v1 board. Obtaining the suite
          and one-step submission land with v2 · for now it produces a local <span className="font-mono text-bench-text">my-run.json</span>.
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
  readonly popular: readonly { model: OnrampCatalogModel; quant: OnrampCatalogQuant }[];
  readonly popularSlug: string | null;
  readonly onPopular: (slug: string) => void;
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

  if (props.mode === "popular") {
    if (props.popular.length === 0) {
      return <p className="font-mono text-xs text-bench-muted">No board-rankable model (Qwen3 / Gemma) fits this VRAM yet · try Browse or a larger tier.</p>;
    }
    const activeSlug = props.popularSlug ?? props.popular[0]!.model.slug;
    return (
      <div className="flex flex-col gap-2">
        {props.popular.map((entry) => (
          <button
            key={entry.model.slug}
            type="button"
            onClick={() => props.onPopular(entry.model.slug)}
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
        <p className="font-mono text-[10px] text-bench-muted">Most-downloaded board-rankable models that fit · catalog snapshot, not an endorsement.</p>
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
        Experimental · we have not validated this repo has a compatible GGUF, template, or license · only Qwen3/Gemma
        families are board-rankable today.
      </p>
    </div>
  );
}
