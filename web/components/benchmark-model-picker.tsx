"use client";

import Link from "next/link";
import { useState } from "react";
import { PasteModelPicker } from "@/components/benchmark-paste-picker";
import { formatCompactNumber } from "@/lib/format";
import {
  bestFitForVram,
  isDerivativeModel,
  type BrowseFamily,
  type BrowseVariant,
  type ModelKind,
  type OnrampCatalogModel,
  type OnrampCatalogQuant,
  type PopularitySort,
} from "@/lib/onramp";

export type PickMode = "popular" | "browse" | "paste";
const COUNT_FORMAT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const SORT_LABELS: Record<PopularitySort, string> = {
  downloads: "Downloads",
  trending: "Trending",
  likes: "Likes",
};
const SORT_DESCRIPTIONS: Record<PopularitySort, string> = {
  downloads: "HF downloads last month",
  trending: "HF trending score",
  likes: "HF likes",
};
const POPULARITY_DISCLAIMER =
  "Hugging Face popularity is repo-level: monthly downloads and likes count the whole GGUF repo, not this individual quant file.";
const VARIANT_PREVIEW_LIMIT = 5;
const VARIANT_KIND_LABELS: Record<ModelKind, string> = {
  base: "Variant",
  finetune: "Fine-tune",
  distill: "Distill",
  merge: "Merge",
};

function formatParams(paramsB: number | null): string {
  return paramsB === null ? "size n/a" : `${formatCompactNumber(paramsB)}B`;
}

function formatCount(value: number): string {
  return COUNT_FORMAT.format(value);
}

function popularityStats(model: OnrampCatalogModel): string {
  return `↓ ${formatCount(model.downloads)} downloads/mo · ♥ ${formatCount(model.likes)}`;
}

function fineTuneLine(model: OnrampCatalogModel): string | null {
  return isDerivativeModel(model) && model.baseModelDisplayName !== null ? `fine-tune of ${model.baseModelDisplayName}` : null;
}

function LineageChip({ model }: { readonly model: OnrampCatalogModel }) {
  const label = fineTuneLine(model);
  if (label === null) {
    return null;
  }
  const className =
    "inline-flex w-fit rounded border border-bench-accent/35 px-1.5 py-0.5 font-mono text-[10px] uppercase text-bench-accent hover:border-bench-accent";
  return model.baseModelSlug === null ? (
    <span className={className}>{label}</span>
  ) : (
    <Link href={`/model/${model.baseModelSlug}`} className={className}>
      {label}
    </Link>
  );
}

function variantKindLabel(variant: BrowseVariant): string {
  return variant.official ? "Official variant" : VARIANT_KIND_LABELS[variant.kind];
}

function variantMeta(variant: BrowseVariant): string {
  const base = `${variantKindLabel(variant)} · by ${variant.model.org || "unknown org"}`;
  const alsoBasedOn = variant.alsoBasedOn.map((model) => model.displayName).join(", ");
  return alsoBasedOn === "" ? base : `${base} · also based on ${alsoBasedOn}`;
}

function familySummary(family: BrowseFamily): string {
  const variantCount = family.variants.length;
  const variants = variantCount === 1 ? "1 variant" : `${variantCount} variants`;
  return `Original + ${variants} · ${formatParams(family.base.paramsB)} · ${popularityStats(family.base)}`;
}

export function ModelPicker(props: {
  readonly mode: PickMode;
  readonly popular: readonly { model: OnrampCatalogModel; quant: OnrampCatalogQuant }[];
  readonly popularSlug: string | null;
  readonly onPopular: (slug: string) => void;
  readonly popularitySort: PopularitySort;
  readonly onPopularitySort: (sort: PopularitySort) => void;
  readonly vramGb: number;
  readonly popularityAsOf: string | null;
  readonly orgs: readonly string[];
  readonly browseOrg: string;
  readonly onOrg: (org: string) => void;
  readonly browseSearch: string;
  readonly onBrowseSearch: (value: string) => void;
  readonly families: readonly BrowseFamily[];
  readonly browseSlug: string;
  readonly browseModel: OnrampCatalogModel | null;
  readonly onModel: (slug: string) => void;
  readonly browseQuant: string;
  readonly onQuant: (label: string) => void;
  readonly pasteRepo: string;
  readonly onPasteRepo: (value: string) => void;
  readonly pasteHfModelId: string;
  readonly onPasteHfModelId: (value: string) => void;
  readonly pasteQuant: string;
  readonly onPasteQuant: (value: string) => void;
}) {
  const [expandedFamilySlug, setExpandedFamilySlug] = useState<string | null>(null);
  const [showAllFamilySlug, setShowAllFamilySlug] = useState<string | null>(null);
  const selectClass =
    "rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent";

  if (props.mode === "popular") {
    const firstPopular = props.popular[0];
    if (firstPopular === undefined) {
      return <p className="font-mono text-xs text-bench-muted">No catalog GGUF model fits this VRAM yet · try Browse or a larger tier.</p>;
    }
    const activeSlug = props.popularSlug ?? firstPopular.model.slug;
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-mono text-[11px] text-bench-muted">
            Popular models with 8k-context VRAM estimates for {props.vramGb} GB — sorted by{" "}
            {SORT_DESCRIPTIONS[props.popularitySort]} · popularity as of {props.popularityAsOf ?? "unknown date"}
          </p>
          <div className="inline-flex rounded border border-bench-line bg-bench-panel-2 p-1" role="group" aria-label="Popular model sort">
            {(["downloads", "trending", "likes"] as const).map((sort) => (
              <button
                key={sort}
                type="button"
                onClick={() => props.onPopularitySort(sort)}
                className={[
                  "rounded px-2.5 py-1 text-[11px] font-semibold uppercase transition-colors",
                  props.popularitySort === sort ? "bg-bench-accent text-bench-bg" : "text-bench-muted hover:text-bench-text",
                ].join(" ")}
              >
                {SORT_LABELS[sort]}
              </button>
            ))}
          </div>
        </div>
        {props.popular.map((entry) => (
          <div key={entry.model.slug} className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => props.onPopular(entry.model.slug)}
              className={[
                "flex min-w-0 grow items-center justify-between gap-3 rounded border px-3 py-2 text-left text-sm transition-colors",
                entry.model.slug === activeSlug
                  ? "border-bench-accent bg-bench-accent/10 text-bench-text"
                  : "border-bench-line text-bench-muted hover:border-bench-accent/60",
              ].join(" ")}
            >
              <span className="min-w-0">
                <span className="block truncate font-semibold text-bench-text">{entry.model.displayName}</span>
                <span className="block font-mono text-[11px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
                  {formatParams(entry.model.paramsB)} · {popularityStats(entry.model)}
                </span>
              </span>
              <span className="shrink-0 font-mono text-[11px] text-bench-muted">{entry.quant.label}</span>
            </button>
            {fineTuneLine(entry.model) ? (
              <div className="flex shrink-0 items-center">
                <LineageChip model={entry.model} />
              </div>
            ) : null}
            {entry.model.ggufRepo !== null ? (
              <a
                href={`https://huggingface.co/${entry.model.ggufRepo}`}
                target="_blank"
                rel="noreferrer"
                aria-label={`${entry.model.displayName} GGUF repo on Hugging Face`}
                className="flex shrink-0 items-center rounded border border-bench-line px-2 font-mono text-[11px] text-bench-muted hover:border-bench-accent/60 hover:text-bench-accent"
              >
                HF ↗
              </a>
            ) : null}
          </div>
        ))}
        <p className="font-mono text-[10px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
          Hugging Face popularity is repo-level and monthly for downloads · 8k-context estimate; the ranked recipe pins
          32k context — you may need one quant tier smaller.
        </p>
      </div>
    );
  }

  if (props.mode === "browse") {
    const activeModel = props.browseModel;
    const quantOptions = activeModel?.quants.map((quant) => quant.label) ?? [];
    const activeFit = activeModel === null ? null : bestFitForVram(activeModel, props.vramGb).quant;
    const quantPlaceholder =
      activeModel === null ? "Quant" : activeFit === null ? "Pick quant explicitly" : "Quant (best fit)";
    const searchActive = props.browseSearch.trim() !== "";
    const selectedFamilySlug =
      props.families.find(
        (family) => family.base.slug === props.browseSlug || family.variants.some((variant) => variant.model.slug === props.browseSlug),
      )?.base.slug ?? null;
    const isExpanded = (family: BrowseFamily): boolean =>
      searchActive ||
      selectedFamilySlug === family.base.slug ||
      expandedFamilySlug === family.base.slug ||
      family.variants.length === 0 ||
      (family.variants.length > 0 && family.variants.length <= 3) ||
      family.variants.length > 10;
    const emptyState =
      props.browseOrg === "" && !searchActive
        ? "Choose a base lab to browse family trees."
        : searchActive
          ? "No base families match this search."
          : "No catalog base families for this lab yet.";
    return (
      <div className="flex flex-col gap-2">
        <div className="grid gap-2 md:grid-cols-[180px_minmax(0,1fr)_180px]">
          <select className={selectClass} aria-label="Base lab" value={props.browseOrg} onChange={(event) => props.onOrg(event.currentTarget.value)}>
            <option value="">Base lab…</option>
            {props.orgs.map((org) => (
              <option key={org} value={org}>
                {org}
              </option>
            ))}
          </select>
          <input
            className={selectClass}
            aria-label="Search model, creator, or repo"
            placeholder="Search model / creator / repo..."
            value={props.browseSearch}
            onChange={(event) => props.onBrowseSearch(event.currentTarget.value)}
          />
          <select className={selectClass} aria-label="Quant" value={props.browseQuant} onChange={(event) => props.onQuant(event.currentTarget.value)} disabled={activeModel === null}>
            <option value="">{quantPlaceholder}</option>
            {quantOptions.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {props.families.length === 0 ? (
          <p className="font-mono text-xs text-bench-muted">{emptyState}</p>
        ) : (
          <div className="grid max-h-[280px] gap-2 overflow-y-auto pr-1" role="radiogroup" aria-label="Model">
            {props.families.map((family) => {
              const expanded = isExpanded(family);
              const showAll = showAllFamilySlug === family.base.slug || family.variants.length <= VARIANT_PREVIEW_LIMIT;
              const variants = showAll ? family.variants : family.variants.slice(0, VARIANT_PREVIEW_LIMIT);
              const baseSelected = family.base.slug === props.browseSlug;
              return (
                <div key={family.base.slug} className="min-w-0 rounded border border-bench-line bg-bench-panel-2/40">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => {
                      setExpandedFamilySlug(expandedFamilySlug === family.base.slug ? null : family.base.slug);
                      setShowAllFamilySlug(null);
                    }}
                    className="flex w-full min-w-0 items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-white/5"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-semibold text-bench-text">{family.base.displayName}</span>
                      <span className="block font-mono text-[11px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
                        {familySummary(family)}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-bench-muted">
                      {family.variants.length === 0 ? "base only" : expanded ? "expanded" : `${family.variants.length} variants`}
                    </span>
                  </button>
                  {expanded ? (
                    <div className="grid gap-1 border-t border-bench-line p-2">
                      <button
                        type="button"
                        role="radio"
                        aria-checked={baseSelected}
                        onClick={() => props.onModel(family.base.slug)}
                        className={[
                          "min-w-0 rounded border px-3 py-2 text-left text-sm transition-colors",
                          baseSelected
                            ? "border-bench-accent bg-bench-accent/10 text-bench-text"
                            : "border-bench-line text-bench-muted hover:border-bench-accent/60",
                        ].join(" ")}
                      >
                        <span className="block font-semibold text-bench-text">Original release</span>
                        <span className="mt-1 block font-mono text-[11px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
                          {family.base.displayName} · {popularityStats(family.base)} · {bestFitForVram(family.base, props.vramGb).label}
                        </span>
                      </button>
                      {family.variants.length === 0 && baseSelected ? (
                        <p className="px-3 py-1 font-mono text-[11px] text-bench-muted">
                          base only — no curated variants for this base yet. Paste HF repo if you need another release.
                        </p>
                      ) : null}
                      {variants.map((variant) => {
                        const selected = variant.model.slug === props.browseSlug;
                        return (
                          <button
                            key={variant.model.slug}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            onClick={() => props.onModel(variant.model.slug)}
                            className={[
                              "min-w-0 rounded border px-3 py-2 text-left text-sm transition-colors",
                              selected
                                ? "border-bench-accent bg-bench-accent/10 text-bench-text"
                                : "border-bench-line text-bench-muted hover:border-bench-accent/60",
                            ].join(" ")}
                          >
                            <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                              <span className="truncate font-semibold text-bench-text">{variant.model.displayName}</span>
                              <span className="rounded border border-bench-accent/35 px-1.5 py-0.5 font-mono text-[10px] uppercase text-bench-accent">
                                {variantKindLabel(variant)}
                              </span>
                            </span>
                            <span className="mt-1 block font-mono text-[11px] text-bench-muted">{variantMeta(variant)}</span>
                            <span className="mt-1 block font-mono text-[11px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
                              {popularityStats(variant.model)} · {bestFitForVram(variant.model, props.vramGb).label}
                            </span>
                          </button>
                        );
                      })}
                      {family.variants.length > VARIANT_PREVIEW_LIMIT && !showAll ? (
                        <button
                          type="button"
                          onClick={() => setShowAllFamilySlug(family.base.slug)}
                          className="rounded border border-bench-line px-3 py-2 text-left font-mono text-[11px] text-bench-muted transition-colors hover:border-bench-accent/60 hover:text-bench-accent"
                        >
                          Show all {family.variants.length} variants
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return <PasteModelPicker {...props} />;
}
