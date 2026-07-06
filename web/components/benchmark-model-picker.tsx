"use client";

import Link from "next/link";
import { PasteModelPicker } from "@/components/benchmark-paste-picker";
import { formatCompactNumber } from "@/lib/format";
import {
  isDerivativeModel,
  modelMatchesBrowseType,
  type BrowseModelType,
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
  readonly orgModels: readonly OnrampCatalogModel[];
  readonly browseType: BrowseModelType;
  readonly onBrowseType: (value: BrowseModelType) => void;
  readonly browseSlug: string;
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
    const displayedModels = props.orgModels.filter((model) => modelMatchesBrowseType(model, props.browseType));
    const activeModel = displayedModels.find((model) => model.slug === props.browseSlug);
    const quantOptions = activeModel?.quants.map((quant) => quant.label) ?? [];
    return (
      <div className="flex flex-col gap-2">
        <div className="inline-flex w-fit rounded border border-bench-line bg-bench-panel-2 p-1" role="group" aria-label="Catalog model type">
          {([
            ["all", "All"],
            ["base", "Base"],
            ["finetune", "Fine-tunes"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => props.onBrowseType(value)}
              className={[
                "rounded px-2.5 py-1 text-[11px] font-semibold uppercase transition-colors",
                props.browseType === value ? "bg-bench-accent text-bench-bg" : "text-bench-muted hover:text-bench-text",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px]">
          <select className={selectClass} aria-label="Lab" value={props.browseOrg} onChange={(event) => props.onOrg(event.currentTarget.value)}>
            <option value="">Lab…</option>
            {props.orgs.map((org) => (
              <option key={org} value={org}>
                {org}
              </option>
            ))}
          </select>
          <select className={selectClass} aria-label="Quant" value={props.browseQuant} onChange={(event) => props.onQuant(event.currentTarget.value)} disabled={activeModel === undefined}>
            <option value="">Quant (auto)</option>
            {quantOptions.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {displayedModels.length === 0 ? (
          <p className="font-mono text-xs text-bench-muted">Choose a lab to browse its catalog models.</p>
        ) : (
          <div className="grid max-h-[280px] gap-2 overflow-y-auto pr-1" role="listbox" aria-label="Model">
            {displayedModels.map((model) => {
              const selected = model.slug === props.browseSlug;
              return (
                <div
                  key={model.slug}
                  role="option"
                  aria-selected={selected}
                  className={[
                    "min-w-0 rounded border px-3 py-2 text-left text-sm transition-colors",
                    selected
                      ? "border-bench-accent bg-bench-accent/10 text-bench-text"
                      : "border-bench-line text-bench-muted hover:border-bench-accent/60",
                  ].join(" ")}
                >
                  <button type="button" onClick={() => props.onModel(model.slug)} className="block w-full min-w-0 text-left">
                    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="truncate font-semibold text-bench-text">{model.displayName}</span>
                    </span>
                    <span className="mt-1 block font-mono text-[11px] text-bench-muted" title={POPULARITY_DISCLAIMER}>
                      {formatParams(model.paramsB)} · {popularityStats(model)}
                    </span>
                  </button>
                  {fineTuneLine(model) ? (
                    <div className="mt-2">
                      <LineageChip model={model} />
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
