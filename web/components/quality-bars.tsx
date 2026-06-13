import { DemoBadge } from "@/components/badges";
import { formatGb, formatScore } from "@/lib/format";
import { getRankedQualityRows, type AnchorQualityRow, type LocalQualityRow } from "@/lib/quality-bars";
import type { AnchorReference } from "@/lib/data";
import type { RigMatchCandidate } from "@/lib/rig-match";

export function QualityBars({
  anchorRuns,
  runs,
}: {
  readonly anchorRuns: readonly AnchorReference[];
  readonly runs: readonly RigMatchCandidate[];
}) {
  const rows = getRankedQualityRows({ anchorRuns, runs });
  const ariaLabel = `Ranked Quality Bars showing ${rows.anchors.length} frontier anchors followed by ${rows.locals.length} local model representatives, with bar length on a fixed 0 to 100 composite quality scale.`;

  return (
    <section data-testid="quality-bars" className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Ranked Quality Bars</p>
          <h2 className="mt-2 text-2xl font-semibold text-bench-text">Quality index</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-bench-muted">
            Frontier anchors are reference ceilings. Local rows show each model once at its best measured headline quant.
          </p>
        </div>
        <div className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-xs text-bench-muted">
          fixed 0-100 scale
        </div>
      </div>

      <div role="img" aria-label={ariaLabel} className="space-y-2">
        <div className="space-y-2">
          {rows.anchors.map((row) => (
            <QualityBarRow key={row.id} row={row} />
          ))}
        </div>

        <div className="flex items-center gap-3 py-2" aria-hidden="true">
          <div className="h-px flex-1 bg-bench-anchor/55" />
          <span className="font-mono text-[11px] uppercase text-bench-anchor-soft">frontier line</span>
          <div className="h-px flex-1 bg-bench-anchor/55" />
        </div>

        <div className="space-y-2">
          {rows.locals.map((row) => (
            <QualityBarRow key={row.id} row={row} />
          ))}
        </div>

        <dl className="sr-only">
          {rows.anchors.map((row) => (
            <div key={row.id}>
              <dt>{row.modelLabel}</dt>
              <dd>frontier score {formatScore(row.score)}</dd>
            </div>
          ))}
          {rows.locals.map((row) => (
            <div key={row.id}>
              <dt>{row.modelLabel}</dt>
              <dd>
                local {row.quantLabel ?? "n/a"} score {formatScore(row.score)} VRAM {formatGb(row.vramFootprintGb)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function QualityBarRow({ row }: { readonly row: AnchorQualityRow | LocalQualityRow }) {
  const isAnchor = row.kind === "anchor";
  const fillClass = isAnchor ? "bg-bench-anchor" : "bg-bench-accent";
  const labelClass = isAnchor ? "text-bench-anchor-soft" : "text-bench-accent";

  return (
    <div className="grid min-w-0 gap-2 rounded border border-bench-line bg-bench-panel-2/55 p-2 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)_92px] sm:items-center">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-semibold text-bench-text">{row.modelLabel}</span>
          {isAnchor ? (
            <span className="shrink-0 rounded border border-bench-anchor/45 bg-bench-anchor/10 px-2 py-0.5 font-mono text-[10px] uppercase text-bench-anchor-soft">
              frontier
            </span>
          ) : row.demo ? (
            <DemoBadge />
          ) : null}
        </div>
        <div className={["mt-1 truncate font-mono text-xs", labelClass].join(" ")}>
          {isAnchor ? "API anchor" : `headline ${row.quantLabel ?? "n/a"}`}
        </div>
      </div>

      <div className="relative h-8 overflow-hidden rounded border border-bench-line bg-bench-bg">
        <div className="absolute inset-0 grid grid-cols-4">
          <span className="border-r border-bench-line/70" />
          <span className="border-r border-bench-line/70" />
          <span className="border-r border-bench-line/70" />
          <span />
        </div>
        <div className={["relative flex h-full items-center justify-end pr-2", fillClass].join(" ")} style={{ width: `${row.barWidthPercent}%` }}>
          <span className="font-mono text-xs font-semibold text-bench-bg">{formatScore(row.score)}</span>
        </div>
      </div>

      {isAnchor ? (
        <div aria-hidden="true" />
      ) : (
        <div className="w-fit rounded border border-bench-accent/35 bg-bench-accent/10 px-2 py-1 font-mono text-xs text-bench-accent sm:ml-auto">
          {formatGb(row.vramFootprintGb)}
        </div>
      )}
    </div>
  );
}
