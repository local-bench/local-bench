"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { DemoBadge } from "@/components/badges";
import { RigMatchBounty } from "@/components/rig-match-bounty";
import {
  LANE_FILTERS,
  QUANT_OPTIONS,
  VRAM_TIERS,
  rankRigMatches,
  type LaneFilter,
  type QuantFilter,
  type RigMatch,
  type RigMatchAnchor,
  type RigMatchCandidate,
  type RigMatchVerdict,
} from "@/lib/rig-match";
import { formatCi, formatCompactNumber, formatGb, formatScore } from "@/lib/format";

const DEFAULT_VRAM = 24;
const DEFAULT_QUANT: QuantFilter = "any";
const DEFAULT_LANE: LaneFilter = "answer-only";
const MAX_VISIBLE_ROWS = 8;

export function RigMatchFinder({
  anchors,
  candidates,
}: {
  readonly anchors: readonly RigMatchAnchor[];
  readonly candidates: readonly RigMatchCandidate[];
}) {
  const [vramGb, setVramGb] = useState<number>(DEFAULT_VRAM);
  const [quant, setQuant] = useState<QuantFilter>(DEFAULT_QUANT);
  const [lane, setLane] = useState<LaneFilter>(DEFAULT_LANE);
  const matches = useMemo(
    () => rankRigMatches({ anchors, candidates, lane, quant, vramGb }),
    [anchors, candidates, lane, quant, vramGb],
  );
  const visibleMatches = matches.slice(0, MAX_VISIBLE_ROWS);
  const coverageMessage = coverageFor(matches.length, vramGb, quant);

  return (
    <section data-testid="rig-match-finder" className="rounded-lg border border-bench-line bg-bench-panel p-5 shadow-2xl shadow-black/20">
      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-mono text-xs uppercase tracking-normal text-bench-accent">Rig-Match Finder</p>
              <h1 className="mt-2 text-4xl font-semibold text-bench-text">What can I run?</h1>
              <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
                Pick a VRAM budget and quant target. Results show local model x quant runs that fit, ranked by the lower
                bound of their quality interval.
              </p>
            </div>
            <FrontierCeiling anchors={anchors} />
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-[170px_170px_1fr]">
            <label className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted" htmlFor="vram-tier">
              VRAM tier
              <select
                id="vram-tier"
                aria-label="VRAM tier"
                className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent"
                value={vramGb}
                onChange={(event) => setVramGb(Number(event.currentTarget.value))}
              >
                {VRAM_TIERS.map((tier) => (
                  <option key={tier} value={tier}>
                    {tier} GB
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted" htmlFor="quant-filter">
              Quant
              <select
                id="quant-filter"
                className="rounded border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none focus:border-bench-accent"
                value={quant}
                onChange={(event) => setQuant(toQuantFilter(event.currentTarget.value))}
              >
                <option value="any">Any</option>
                {QUANT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-1 text-xs font-semibold uppercase text-bench-muted">
              <span>Lane</span>
              <div className="inline-flex w-fit rounded border border-bench-line bg-bench-panel-2 p-1" role="group" aria-label="Lane">
                {LANE_FILTERS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={[
                      "rounded px-3 py-1.5 text-sm font-semibold transition-colors",
                      lane === option ? "bg-bench-accent text-bench-bg" : "text-bench-muted hover:text-bench-text",
                    ].join(" ")}
                    onClick={() => setLane(option)}
                  >
                    {option === "any" ? "Any local" : "Answer-only"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-5 max-w-full overflow-x-auto rounded border border-bench-line bg-bench-panel-2/70">
            <table data-testid="rig-match-results" className="min-w-[920px] border-collapse text-sm">
              <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
                <tr>
                  <th className="px-3 py-3">#</th>
                  <th className="px-3 py-3">Model</th>
                  <th className="px-3 py-3">Quant</th>
                  <th className="px-3 py-3">Quality</th>
                  <th className="px-3 py-3">Frontier gap</th>
                  <th className="px-3 py-3">VRAM</th>
                  <th className="px-3 py-3">tok/s</th>
                  <th className="px-3 py-3">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {visibleMatches.map((match, index) => (
                  <FinderRow key={match.runId} match={match} rank={index + 1} />
                ))}
              </tbody>
            </table>
            {visibleMatches.length === 0 ? <EmptyState vramGb={vramGb} quant={quant} /> : null}
          </div>
          {coverageMessage ? (
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded border border-bench-warn/35 bg-bench-warn/10 p-3 text-sm text-bench-warn">
              <span>{coverageMessage}</span>
              <Link href="/submit" className="rounded border border-bench-warn/55 px-3 py-1.5 font-semibold text-bench-warn hover:bg-bench-warn/10">
                submit your run
              </Link>
            </div>
          ) : null}
        </div>
        <RigMatchBounty />
      </div>
    </section>
  );
}

function FinderRow({ match, rank }: { readonly match: RigMatch; readonly rank: number }) {
  return (
    <tr className="border-t border-bench-line/75 align-middle hover:bg-white/[0.035]">
      <td className="px-3 py-3 font-mono text-bench-muted">{rank}</td>
      <td className="px-3 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/model/${match.modelSlug}`} className="font-semibold text-bench-text hover:text-bench-accent">
            {match.modelLabel}
          </Link>
          {match.demo ? <DemoBadge /> : null}
        </div>
        <div className="text-xs text-bench-muted">{match.family}</div>
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{match.quantLabel ?? "n/a"}</td>
      <td className="px-3 py-3 font-mono text-bench-text">
        {formatScore(match.score.point)} <span className="text-bench-muted">{formatCi(match.score)}</span>
      </td>
      <td className="px-3 py-3 font-mono text-bench-text">{Math.round(match.frontierGapPercent)}% of top anchor</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatGb(match.vramFootprintGb)}</td>
      <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(match.tokS)}</td>
      <td className="px-3 py-3">
        <VerdictChip verdict={match.verdict} />
      </td>
    </tr>
  );
}

function FrontierCeiling({ anchors }: { readonly anchors: readonly RigMatchAnchor[] }) {
  const labels = [...anchors]
    .sort((left, right) => right.score.point - left.score.point)
    .map((anchor) => `${shortAnchorLabel(anchor.modelLabel)} ${Math.round(anchor.score.point)}`);
  return (
    <div className="rounded border border-bench-anchor/40 bg-bench-anchor/10 px-3 py-2 font-mono text-xs uppercase text-bench-anchor-soft">
      frontier ceiling: {labels.join(" · ")}
    </div>
  );
}

function EmptyState({ quant, vramGb }: { readonly quant: QuantFilter; readonly vramGb: number }) {
  return (
    <div className="border-t border-bench-line p-5 text-sm leading-6 text-bench-muted">
      No local {quant === "any" ? "runs" : quant} rows fit {vramGb} GB yet. Empty cells are coverage gaps, not failures.
    </div>
  );
}

function VerdictChip({ verdict }: { readonly verdict: RigMatchVerdict }) {
  const styles: Record<RigMatchVerdict, string> = {
    "best-under-budget": "border-bench-better/45 bg-bench-better/10 text-bench-better",
    "needs-replication": "border-bench-warn/45 bg-bench-warn/10 text-bench-warn",
    "not-enough-data": "border-bench-muted/45 bg-white/[0.03] text-bench-muted",
    "statistical-tie": "border-bench-tied/45 bg-white/[0.03] text-bench-tied",
  };
  return (
    <span className={["inline-flex rounded border px-2 py-1 text-[11px] font-semibold uppercase", styles[verdict]].join(" ")}>
      {verdict.replace(/-/g, " ")}
    </span>
  );
}

function coverageFor(count: number, vramGb: number, quant: QuantFilter): string | null {
  if (count === 0) {
    return `No ${quant === "any" ? "local" : quant} rows currently fit ${vramGb} GB.`;
  }
  if (count < 3) {
    return `Only ${count} local row${count === 1 ? "" : "s"} fit this selection; more runs will tighten the recommendation.`;
  }
  return null;
}

function toQuantFilter(value: string): QuantFilter {
  return value === "FP16" || value === "Q8_0" || value === "Q5_K_M" || value === "Q4_K_M" || value === "Q3_K_M"
    ? value
    : "any";
}

function shortAnchorLabel(label: string): string {
  if (label.includes("Opus")) {
    return "Opus";
  }
  if (label.includes("Sonnet")) {
    return "Sonnet";
  }
  if (label.includes("Gemini")) {
    return "Gemini";
  }
  return label;
}
