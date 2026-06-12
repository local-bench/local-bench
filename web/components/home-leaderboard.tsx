"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { KindBadge, LaneBadge, TierBadge } from "@/components/badges";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { axisLabel, formatCost, formatInteger } from "@/lib/format";
import type { Axis, IndexModel } from "@/lib/schemas";

const TABLE_AXES = ["mmlu_pro", "ifeval", "genmath"] as const;

type SortKey =
  | "model"
  | "kind"
  | "composite"
  | "mmlu_pro"
  | "ifeval"
  | "genmath"
  | "tier"
  | "lane"
  | "tokens"
  | "cost";

type SortDirection = "asc" | "desc";

type SortState = {
  readonly key: SortKey;
  readonly direction: SortDirection;
};

export function HomeLeaderboard({ models }: { readonly models: readonly IndexModel[] }) {
  const [sort, setSort] = useState<SortState>({ key: "composite", direction: "desc" });
  const sortedModels = useMemo(() => sortRows(models, sort), [models, sort]);

  return (
    <div className="overflow-x-auto rounded-lg border border-bench-line bg-bench-panel/82 shadow-2xl shadow-black/20">
      <table className="min-w-[1120px] border-collapse text-sm">
        <thead className="bg-white/[0.03] text-left text-[11px] uppercase text-bench-muted">
          <tr>
            <th className="px-3 py-3 font-semibold">Rank</th>
            <SortableHeader label="Model" sortKey="model" sort={sort} onSort={setSort} />
            <SortableHeader label="Kind" sortKey="kind" sort={sort} onSort={setSort} />
            <SortableHeader label="Composite" sortKey="composite" sort={sort} onSort={setSort} />
            {TABLE_AXES.map((axis) => (
              <SortableHeader key={axis} label={axisLabel(axis)} sortKey={axis} sort={sort} onSort={setSort} />
            ))}
            <SortableHeader label="Tier" sortKey="tier" sort={sort} onSort={setSort} />
            <SortableHeader label="Lane" sortKey="lane" sort={sort} onSort={setSort} />
            <SortableHeader label="Tokens" sortKey="tokens" sort={sort} onSort={setSort} />
            <SortableHeader label="Cost" sortKey="cost" sort={sort} onSort={setSort} />
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model, index) => (
            <tr
              key={model.slug}
              className={[
                "border-t border-bench-line/75 align-middle transition-colors hover:bg-white/[0.035]",
                model.kind === "anchor" ? "bg-amber-300/[0.025]" : "",
              ].join(" ")}
            >
              <td className="px-3 py-3 font-mono text-bench-muted">{index + 1}</td>
              <td className="px-3 py-3">
                <Link href={`/model/${model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
                  {model.model_label}
                </Link>
                <div className="text-xs text-bench-muted">{model.family}</div>
              </td>
              <td className="px-3 py-3">
                <KindBadge kind={model.kind} runCount={model.n_runs} />
              </td>
              <td className="px-3 py-3">
                <ScoreBar score={model.composite} tone={model.kind === "anchor" ? "anchor" : "accent"} />
              </td>
              {TABLE_AXES.map((axis) => (
                <td key={axis} className="px-3 py-3">
                  <AxisMiniBar score={model.axes[axis]} />
                </td>
              ))}
              <td className="px-3 py-3">
                <TierBadge tier={model.tier} />
              </td>
              <td className="px-3 py-3">
                <LaneBadge lane={model.lane} />
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">
                {formatInteger(model.tokens_to_answer_median)}
              </td>
              <td className="px-3 py-3 font-mono text-bench-text">{formatCost(model.est_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  readonly label: string;
  readonly sortKey: SortKey;
  readonly sort: SortState;
  readonly onSort: (sort: SortState) => void;
}) {
  const active = sort.key === sortKey;
  const marker = active ? (sort.direction === "asc" ? "↑" : "↓") : "↕";

  return (
    <th className="px-3 py-3 font-semibold">
      <button
        type="button"
        className="inline-flex items-center gap-1 text-left hover:text-bench-text"
        onClick={() => onSort(nextSort(sort, sortKey))}
      >
        <span>{label}</span>
        <span className={active ? "text-bench-accent" : "text-bench-muted/60"}>{marker}</span>
      </button>
    </th>
  );
}

function nextSort(current: SortState, key: SortKey): SortState {
  if (current.key === key) {
    return { key, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  return { key, direction: key === "model" ? "asc" : "desc" };
}

function sortRows(models: readonly IndexModel[], sort: SortState): readonly IndexModel[] {
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...models].sort((left, right) => compareRows(left, right, sort.key) * direction);
}

function compareRows(left: IndexModel, right: IndexModel, key: SortKey): number {
  switch (key) {
    case "model":
      return left.model_label.localeCompare(right.model_label);
    case "kind":
      return left.kind.localeCompare(right.kind);
    case "composite":
      return left.composite.point - right.composite.point;
    case "mmlu_pro":
    case "ifeval":
    case "genmath":
      return compareAxis(left, right, key);
    case "tier":
      return left.tier.localeCompare(right.tier);
    case "lane":
      return (left.lane ?? "").localeCompare(right.lane ?? "");
    case "tokens":
      return nullableNumber(left.tokens_to_answer_median) - nullableNumber(right.tokens_to_answer_median);
    case "cost":
      return nullableNumber(left.est_cost_usd) - nullableNumber(right.est_cost_usd);
    default:
      return assertNever(key);
  }
}

function compareAxis(left: IndexModel, right: IndexModel, axis: Axis): number {
  return left.axes[axis].point - right.axes[axis].point;
}

function nullableNumber(value: number | null): number {
  return value ?? Number.NEGATIVE_INFINITY;
}

function assertNever(value: never): never {
  throw new Error(`Unhandled sort key: ${String(value)}`);
}
