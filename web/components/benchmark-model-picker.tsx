"use client";

import { formatCompactNumber } from "@/lib/format";
import type { OnrampCatalogModel, OnrampCatalogQuant } from "@/lib/onramp";
import { QUANT_OPTIONS } from "@/lib/quant";

export type PickMode = "popular" | "browse" | "paste";

function formatParams(paramsB: number | null): string {
  return paramsB === null ? "size n/a" : `${formatCompactNumber(paramsB)}B`;
}

export function ModelPicker(props: {
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
    const firstPopular = props.popular[0];
    if (firstPopular === undefined) {
      return <p className="font-mono text-xs text-bench-muted">No board-rankable model (Qwen3 / Gemma) fits this VRAM yet · try Browse or a larger tier.</p>;
    }
    const activeSlug = props.popularSlug ?? firstPopular.model.slug;
    return (
      <div className="flex flex-col gap-2">
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
                <span className="font-mono text-[11px] text-bench-muted">
                  {formatParams(entry.model.paramsB)} · {formatCompactNumber(entry.model.downloads)} downloads
                </span>
              </span>
              <span className="shrink-0 font-mono text-[11px] text-bench-muted">{entry.quant.label}</span>
            </button>
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
        <p className="font-mono text-[10px] text-bench-muted">
          Most-downloaded rankable models near the top of your VRAM class · Hugging Face snapshot (June 2026) · not an
          endorsement.
        </p>
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
