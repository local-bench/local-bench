import Link from "next/link";
import type { ReactNode } from "react";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  indexQualifierForAxes,
} from "@/components/local-intelligence-index";
import { AxisMiniBar, ScoreBar } from "@/components/score-bar";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { axisLabel, formatCompactNumber, formatGb } from "@/lib/format";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { getQuantDecisionRows, type QuantDecisionRow } from "@/lib/quant-decision";
import { DEFAULT_CONTEXT_TOKENS, formatContextLength } from "@/lib/rig-match";
import { runtimeDisplay } from "@/lib/runtime-display";
import { RuntimeBadge } from "@/components/runtime-badge";
import type { ModelData, ModelFamilyScatterModel, ModelFamilyScatterRelation } from "@/lib/data";
import { displayIndexVersion, hasCompleteSeason2Coverage, headlineScoreForDisplay, INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

type VariantRun = ModelData["runs"][number];
type OwnVariantRow = {
  readonly kind: "this-model";
  readonly ownRankIndex: number | null;
  readonly run: VariantRun;
};
type FamilyVariantRow = {
  readonly kind: ModelFamilyScatterRelation;
  readonly model: ModelFamilyScatterModel["model"];
  readonly run: VariantRun;
};
type VariantRow = OwnVariantRow | FamilyVariantRow;

export function ModelVariantBoard({
  familyModels = [],
  model,
}: {
  readonly familyModels?: readonly ModelFamilyScatterModel[];
  readonly model: ModelData;
}) {
  // Only headline-lane (current-index) measurements render here. Runs measured under retired
  // lanes are on an earlier index version's scale: they are omitted from the model page
  // entirely (owner call, 2026-07-07 — the diagnostics table read as confusing). Their run
  // receipts remain reachable by direct URL and carry the retired-lane framing.
  const isCurrentIndexRun = (run: VariantRun): boolean =>
    run.score_status !== "measured" || run.lane === HEADLINE_LANE;
  const currentRuns = model.runs.filter(
    (run) => isCurrentIndexRun(run),
  );
  const decisionByQuant = new Map<string, QuantDecisionRow>(
    getQuantDecisionRows({ ...model, runs: currentRuns }, DEFAULT_CONTEXT_TOKENS).rows.map((row) => [
      row.quantLabel,
      row,
    ]),
  );
  const ownRankedRuns = sortRunsBySeason(
    currentRuns.filter((run) => isCompleteRun(run) && headlineScoreForDisplay(run) !== null),
  );
  const ownRankByRun = new Map<VariantRun, number>(ownRankedRuns.map((run, index) => [run, rankWithinRunSeason(ownRankedRuns, index) - 1]));
  const ownRows: readonly OwnVariantRow[] = currentRuns.map((run) => ({
    kind: "this-model",
    ownRankIndex: ownRankByRun.get(run) ?? null,
    run,
  }));
  const familyRows: readonly FamilyVariantRow[] = familyModels.flatMap(({ model: familyModel, relation }) =>
    familyModel.runs
      .filter((run) => run.score_status === "measured" && run.lane === HEADLINE_LANE && isCompleteRun(run))
      .map((run) => ({ kind: relation, model: familyModel, run })),
  );
  const rows = [...ownRows, ...familyRows];
  const axisKeys = variantAxisColumns(rows.map((row) => row.run));
  const ranked = sortVariantRowsBySeason(rows.filter((row) => isCompleteRun(row.run) && headlineScoreForDisplay(row.run) !== null));
  const partial = rows.filter((row) => !isCompleteRun(row.run) && row.run.score_status === "measured");
  const pending = ownRows.filter((row) => row.run.composite === null && row.run.score_status !== "measured");
  const hasPerf = rows.some((row) => row.run.perf !== undefined);
  const indexQualifier = indexQualifierForAxes(rows.find((row) => row.run.axes["tool_use"] !== undefined)?.run.axes ?? {});

  return (
    <section data-testid="model-variant-board" className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel">
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Variant profiles</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
            Complete rows are ordered by {LOCAL_INTELLIGENCE_INDEX_NAME}; partial rows show their measured axes but
            are not ranked. The VRAM/Fits columns ({formatContextLength(DEFAULT_CONTEXT_TOKENS)} context) tell you
            what your card needs.
          </p>
      </div>
      <p className="border-b border-bench-line px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-bench-accent 2xl:hidden">
        Swipe horizontally for all variant metrics &rarr;
      </p>
      <div className="overflow-x-auto">
        <table data-testid="model-variant-table" className="min-w-[1360px] border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
            <tr>
              <th className="px-3 py-3 font-semibold">Rank</th>
              <th className="px-3 py-3 font-semibold">Variant</th>
              <th className="px-3 py-3 font-semibold">
                <span className="flex flex-col gap-0.5 leading-tight">
                  <span>{LOCAL_INTELLIGENCE_INDEX_NAME}</span>
                  <span className="font-mono text-[10px] normal-case text-bench-muted">{indexQualifier}</span>
                </span>
              </th>
              {axisKeys.map((axis) => (
                <th key={axis} className="px-3 py-3 font-semibold">
                  {axisLabel(axis)}
                </th>
              ))}
              <th className="px-3 py-3 font-semibold" title="Model weights + KV cache at 8k context — what your card actually needs">
                VRAM @8k
              </th>
              <th className="px-3 py-3 font-semibold">Fits</th>
              {hasPerf ? (
                <th className="px-3 py-3 font-semibold" title="Prompt processing speed, from llama.cpp timings">
                  Prefill tok/s
                </th>
              ) : null}
              {hasPerf ? (
                <th className="px-3 py-3 font-semibold" title="Generation speed once the prompt is processed, from llama.cpp timings">
                  Decode tok/s
                </th>
              ) : null}
              <th
                className="px-3 py-3 font-semibold"
                title="Completion tokens per second across the whole benchmark run, including prompt processing"
              >
                Overall tok/s
              </th>
              <th className="px-3 py-3 font-semibold" title="Benchmarked model artifact size on disk">
                File size
              </th>
              <th className="px-3 py-3 font-semibold">Runtime</th>
              <th className="px-3 py-3 font-semibold">Run</th>
            </tr>
          </thead>
          <tbody>
            {ranked.length + partial.length + pending.length === 0 ? (
              <tr className="border-t border-bench-line/75">
                <td colSpan={9 + axisKeys.length + (hasPerf ? 2 : 0)} className="px-3 py-5 text-sm text-bench-muted">
                  No current-index measurements yet.{" "}
                  <Link
                    href={`/submit?model=${encodeURIComponent(model.slug)}`}
                    className="font-mono text-xs text-bench-warn hover:underline"
                  >
                    benchmark it
                  </Link>
                </td>
              </tr>
            ) : null}
            {ranked.map((row, index) => {
              const run = row.run;
              const decision =
                row.kind === "this-model" && run.quant_label !== null ? decisionByQuant.get(run.quant_label) : undefined;
              return (
                <tr key={variantRowKey(row, index)} className={variantRowClass(row)}>
                  <td className="px-3 py-3 font-mono text-bench-muted">{rankWithinRowSeason(ranked, index)}</td>
                  <td className="px-3 py-3">
                    <VariantCell row={row}>
                      {row.kind === "this-model" && row.ownRankIndex === 0 ? (
                        <Badge tone="accent" title="Best measured variant — the row shown on the full leaderboard">best</Badge>
                      ) : null}
                      {row.kind === "this-model" && decision?.isSweetSpot ? (
                        <Badge tone="better" title="Smallest variant that still holds the best variant's quality">sweet spot</Badge>
                      ) : null}
                    </VariantCell>
                  </td>
                  <td className="px-3 py-3">
                    {headlineScoreForDisplay(run) === null ? (
                      <span className="text-bench-muted">no data</span>
                    ) : (
                      <ScoreBar axes={run.axes} score={headlineScoreForDisplay(run) as NonNullable<ReturnType<typeof headlineScoreForDisplay>>} />
                    )}
                  </td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      <AxisMiniBar score={run.axes[axis]} axis={axis} />
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatFitTier(decision)}</td>
                  {hasPerf ? (
                    <td className="px-3 py-3 font-mono text-bench-text">{formatPerfTps(run.perf?.prefill_tps)}</td>
                  ) : null}
                  {hasPerf ? (
                    <td className="px-3 py-3 font-mono text-bench-text">{formatPerfTps(run.perf?.decode_tps)}</td>
                  ) : null}
                  <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                  <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3">
                    <RuntimeCell run={run} />
                  </td>
                  <td className="px-3 py-3">
                    {run.run_id === null ? (
                      <span className="font-mono text-xs text-bench-muted">—</span>
                    ) : (
                      <Link href={`/run/${run.run_id}`} className="font-mono text-xs text-bench-accent hover:underline">
                        receipt
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
            {partial.map((row, index) => {
              const run = row.run;
              return (
              <tr key={`partial-${variantRowKey(row, index)}`} className={variantRowClass(row)}>
                <td className="px-3 py-3 font-mono text-bench-muted">—</td>
                <td className="px-3 py-3">
                  <VariantCell row={row}>
                    <Badge tone="muted" title="Partial measurement; missing one or more headline modules">partial headline</Badge>
                  </VariantCell>
                </td>
                <td className="px-3 py-3">
                  {run.composite === null ? (
                    <span className="font-mono text-xs text-bench-muted">not measured</span>
                  ) : (
                    <div>
                      <ScoreBar axes={run.axes} score={run.composite} />
                      <div className="mt-1 font-mono text-[10px] uppercase text-bench-warn-soft">unranked diagnostic</div>
                    </div>
                  )}
                </td>
                {axisKeys.map((axis) => (
                  <td key={axis} className="px-3 py-3">
                    <AxisMiniBar score={run.axes[axis]} axis={axis} />
                  </td>
                ))}
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">n/a</td>
                {hasPerf ? (
                  <td className="px-3 py-3 font-mono text-bench-text">{formatPerfTps(run.perf?.prefill_tps)}</td>
                ) : null}
                {hasPerf ? (
                  <td className="px-3 py-3 font-mono text-bench-text">{formatPerfTps(run.perf?.decode_tps)}</td>
                ) : null}
                <td className="px-3 py-3 font-mono text-bench-text">{formatCompactNumber(run.tok_s)}</td>
                <td className="px-3 py-3 font-mono text-bench-text">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                <td className="px-3 py-3">
                  <RuntimeCell run={run} />
                </td>
                <td className="px-3 py-3">
                  {run.run_id === null ? (
                    <span className="font-mono text-xs text-bench-muted">—</span>
                  ) : (
                    <Link href={`/run/${run.run_id}`} className="font-mono text-xs text-bench-accent hover:underline">
                      receipt
                    </Link>
                  )}
                </td>
              </tr>
              );
            })}
            {pending.map((row, index) => {
              const run = row.run;
              const decision = run.quant_label === null ? undefined : decisionByQuant.get(run.quant_label);
              return (
                <tr key={`pending-${variantRowKey(row, index)}`} className="border-t border-bench-line/75 align-middle text-bench-muted">
                  <td className="px-3 py-3 font-mono">—</td>
                  <td className="px-3 py-3">
                    <VariantCell row={row} />
                  </td>
                  <td className="px-3 py-3">no run yet</td>
                  {axisKeys.map((axis) => (
                    <td key={axis} className="px-3 py-3">
                      —
                    </td>
                  ))}
                  <td className="px-3 py-3 font-mono">{formatGb(run.vram_required_gb_8k ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3 font-mono">{formatFitTier(decision)}</td>
                  {hasPerf ? <td className="px-3 py-3" /> : null}
                  {hasPerf ? <td className="px-3 py-3" /> : null}
                  <td className="px-3 py-3">—</td>
                  <td className="px-3 py-3 font-mono">{formatGb(run.file_gb ?? run.vram_footprint_gb)}</td>
                  <td className="px-3 py-3">
                    <RuntimeCell run={run} />
                  </td>
                  <td className="px-3 py-3">
                    <Link href={`/submit?model=${encodeURIComponent(model.slug)}`} className="font-mono text-xs text-bench-warn hover:underline">
                      benchmark it
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VariantCell({ row, children }: { readonly row: VariantRow; readonly children?: ReactNode }) {
  const quantLabel = <span className="font-mono font-semibold text-bench-text">{row.run.quant_label ?? "n/a"}</span>;
  if (row.kind === "this-model") {
    return (
      <>
        {quantLabel}
        <span className="ml-2 align-middle"><RuntimeBadge runtime={row.run.runtime} /></span>
        {children === undefined ? null : <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">{children}</span>}
        <VllmReproduction run={row.run} />
      </>
    );
  }
  const lineage = familyLineage(row.kind);
  return (
    <div className="flex min-w-[240px] flex-col gap-1">
      <span className="flex flex-wrap items-center gap-2">
        <Badge tone={lineage.tone} title={lineage.title}>
          {lineage.label}
        </Badge>
        <Link href={`/model/${row.model.slug}`} className="font-semibold text-bench-accent hover:underline">
          {row.model.model_label}
        </Link>
      </span>
      <span>
        {quantLabel}
        <span className="ml-2 align-middle"><RuntimeBadge runtime={row.run.runtime} /></span>
        {children === undefined ? null : <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">{children}</span>}
      </span>
      <VllmReproduction run={row.run} />
    </div>
  );
}

function VllmReproduction({ run }: { readonly run: VariantRun }) {
  const snapshot = run.serving_provenance?.snapshot;
  if (run.runtime.name !== "vllm" || snapshot === null || snapshot === undefined) return null;
  const command = [
    "localbench bench",
    "--runtime vllm",
    `--model-ref hf://${snapshot.repo}@${snapshot.revision}`,
    "--model-id <model-id>",
    "--seed 1234",
    "--wsl-distro <wsl-distro>",
    "--vllm-venv <absolute-wsl-vllm-venv>",
    "--wsl-venv-python <absolute-wsl-appworld-python>",
    "--appworld-root <absolute-wsl-appworld-root>",
  ].join(" ");
  return (
    <details className="mt-1 font-mono text-[10px] text-bench-muted">
      <summary className="cursor-pointer text-bench-accent">reproduce</summary>
      <code className="mt-1 block max-w-[360px] whitespace-normal break-all">{command}</code>
      <span className="mt-1 block">Replace each &lt;placeholder&gt; with the pinned maintainer environment value.</span>
      <span className="mt-1 block text-bench-warn-soft">Maintainer lane; community path remains llama.cpp/GGUF until the appliance ships.</span>
    </details>
  );
}

function familyLineage(relation: ModelFamilyScatterRelation): {
  readonly label: "base model" | "fine-tune";
  readonly title: string;
  readonly tone: "anchor" | "mixed";
} {
  switch (relation) {
    case "base-model":
      return { label: "base model", title: "Measured row from this fine-tune's root base model", tone: "anchor" };
    case "family-finetune":
      return { label: "fine-tune", title: "Measured row from this base model's catalog family", tone: "mixed" };
    default:
      return assertNever(relation);
  }
}

function variantRowKey(row: VariantRow, index: number): string {
  const modelPrefix = row.kind === "this-model" ? "this-model" : `${row.kind}-${row.model.slug}`;
  return `${modelPrefix}-${row.run.run_id ?? row.run.quant_label ?? index}`;
}

function variantRowClass(row: VariantRow): string {
  return [
    "border-t border-bench-line/75 align-middle hover:bg-white/[0.035]",
    row.kind === "this-model" ? "" : "bg-bench-panel-2/35",
  ].join(" ");
}

function assertNever(value: never): never {
  throw new Error(`Unexpected variant relation: ${value}`);
}

function Badge({
  tone,
  title,
  children,
}: {
  readonly tone: "accent" | "anchor" | "better" | "mixed" | "muted";
  readonly title: string;
  readonly children: string;
}) {
  const cls =
    tone === "better"
      ? "border-bench-better/45 bg-bench-better/10 text-bench-better"
      : tone === "mixed"
        ? "border-bench-mixed/45 bg-bench-mixed/10 text-bench-mixed"
        : tone === "anchor"
          ? "border-bench-anchor/45 bg-bench-anchor/10 text-bench-anchor"
      : tone === "muted"
        ? "border-bench-muted/40 bg-bench-muted/10 text-bench-muted"
        : "border-bench-accent/45 bg-bench-accent/10 text-bench-accent";
  return (
    <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${cls}`} title={title}>
      {children}
    </span>
  );
}

function RuntimeCell({ run }: { readonly run: VariantRun }) {
  const display = runtimeDisplay(run.runtime);
  if (display === null) {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return (
    <span className="flex min-w-[96px] flex-col gap-0.5 leading-tight">
      <RuntimeBadge runtime={run.runtime} />
      {display.version === null ? null : (
        <span className="font-mono text-[10px] text-bench-muted">{display.version}</span>
      )}
    </span>
  );
}

function formatPerfTps(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : formatCompactNumber(value);
}

function isCompleteRun(run: VariantRun): boolean {
  if (run.index_version === INDEX_VERSION_V4) return hasCompleteSeason2Coverage(run);
  return ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => {
    const score = run.axes[axis];
    return score !== undefined && score.n > 0;
  }) && run.composite !== null;
}

// "Fits" = the smallest GPU VRAM tier a variant runs on at the displayed context (from the
// quant-decision rig-match). Null tier = larger than the biggest modelled card.
function formatFitTier(decision: QuantDecisionRow | undefined): string {
  if (decision === undefined || decision.vramEstimate === null) {
    return "n/a";
  }
  return decision.fitTierGb === null ? ">512 GB" : `${decision.fitTierGb} GB`;
}

// Headline + present axes (n > 0) for this model's runs, in canonical display order.
function variantAxisColumns(runs: readonly VariantRun[]): readonly string[] {
  if (runs.some((run) => run.axes["tool_use"] !== undefined)) {
    return ["tool_use", "knowledge", "instruction", "coding", "math"].filter((key) =>
      runs.some((run) => run.axes[key] !== undefined),
    );
  }
  const present = new Set<string>();
  for (const run of runs) {
    for (const [axis, score] of Object.entries(run.axes)) {
      if (score !== undefined && score.n > 0) {
        present.add(axis);
      }
    }
  }
  return AXIS_CONFIG.map((axis) => axis.key).filter((key) => present.has(key));
}

function sortVariantRowsBySeason(rows: readonly VariantRow[]): readonly VariantRow[] {
  const groups = new Map<string, VariantRow[]>();
  for (const row of rows) {
    const version = displayIndexVersion(row.run);
    groups.set(version, [...(groups.get(version) ?? []), row]);
  }
  return [...groups.values()].flatMap((group) => group.sort(
    (left, right) => (headlineScoreForDisplay(right.run)?.point ?? 0) - (headlineScoreForDisplay(left.run)?.point ?? 0),
  ));
}

function sortRunsBySeason(runs: readonly VariantRun[]): readonly VariantRun[] {
  const groups = new Map<string, VariantRun[]>();
  for (const run of runs) {
    const version = displayIndexVersion(run);
    groups.set(version, [...(groups.get(version) ?? []), run]);
  }
  return [...groups.values()].flatMap((group) => group.sort(
    (left, right) => (headlineScoreForDisplay(right)?.point ?? 0) - (headlineScoreForDisplay(left)?.point ?? 0),
  ));
}

function rankWithinRunSeason(runs: readonly VariantRun[], index: number): number {
  const run = runs[index];
  if (run === undefined) return 0;
  return runs.slice(0, index + 1).filter((candidate) => displayIndexVersion(candidate) === displayIndexVersion(run)).length;
}

function rankWithinRowSeason(rows: readonly VariantRow[], index: number): number {
  const row = rows[index];
  if (row === undefined) return 0;
  return rows.slice(0, index + 1).filter(
    (candidate) => displayIndexVersion(candidate.run) === displayIndexVersion(row.run),
  ).length;
}
