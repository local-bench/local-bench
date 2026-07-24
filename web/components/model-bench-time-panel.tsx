import Link from "next/link";
import { communityArtifactDetailForSha, communityArtifactDetails, type CommunityArtifactDetail } from "@/lib/community-artifact-details";
import { communityScore } from "@/lib/community-scores";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { ModelDataWithConfiguredAxes, ModelFamilyScatterModel } from "@/lib/data";
import { formatGpuShort } from "@/lib/format";
import { WallTimeBar } from "@/components/wall-time-bar";
import { HEADLINE_LANE } from "@/lib/leaderboard-score";
import { declaredNameIsRedundant, sameModelName, variantNameInContext } from "@/lib/model-name";
import { runHref } from "@/lib/routes";
import type { ModelRun } from "@/lib/schemas";
import { hasCompleteSeason2Coverage, INDEX_VERSION_V4 } from "@/lib/scoring-seasons";

const LIMITATION = "Elapsed time for this exact full-suite run; not a general model-speed measurement.";

type BenchTimeRow = {
  readonly hardwareLabel: string | null;
  readonly href: string | null;
  readonly id: string;
  readonly label: string;
  readonly score: number;
  readonly wallTimeSeconds: number;
};

export function ModelBenchTimePanel({
  communityRows = [],
  familyModels = [],
  model,
}: {
  readonly communityRows?: readonly CommunityBoardRow[];
  readonly familyModels?: readonly ModelFamilyScatterModel[];
  readonly model: ModelDataWithConfiguredAxes;
}) {
  const ownRows = model.runs.flatMap((run) => toBakedTimeRow(
    run,
    run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell",
  ));
  const familyRows = familyModels.flatMap(({ model: familyModel }) =>
    familyModel.runs.flatMap((run) => toBakedTimeRow(
      run,
      `${variantNameInContext(familyModel.model_label, model.model_label)} · ${
        run.quant_label ?? run.run_id?.split("__").at(1) ?? run.run_id ?? "catalog shell"
      }`,
    )),
  );
  const artifactDetails = communityArtifactDetails([model, ...familyModels.map((entry) => entry.model)]);
  const liveRows = communityRows.flatMap((row) => toLiveTimeRow(
    row,
    communityArtifactDetailForSha(artifactDetails, row.artifactSha256),
    model.model_label,
  ));
  const rows = [...ownRows, ...familyRows, ...liveRows]
    .sort((left, right) => left.wallTimeSeconds - right.wallTimeSeconds);

  if (rows.length < 2) return null;

  const maxWallTime = Math.max(...rows.map((row) => row.wallTimeSeconds));
  return (
    <section
      data-testid="model-bench-time-panel"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82"
    >
      <div className="border-b border-bench-line bg-white/[0.02] px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Time to complete the benchmark</h2>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-bench-muted-2">
          measured full-suite runs · wall time on each run&apos;s rig
        </p>
        <p className="mt-1 max-w-3xl text-xs leading-5 text-bench-muted">
          Runs are ordered by elapsed time, shortest first. Output length affects totals —{" "}
          <span className="font-semibold text-bench-text">this is not an inference-speed ranking.</span>
        </p>
        <p className="mt-1 text-xs leading-5 text-bench-warn-soft">{LIMITATION}</p>
      </div>
      <div className="px-4 py-2">
        {rows.map((row, index) => (
          <BenchTimeBar
            key={row.id}
            maxWallTime={maxWallTime}
            rank={index + 1}
            row={row}
            shortest={index === 0}
          />
        ))}
      </div>
    </section>
  );
}

function BenchTimeBar({
  maxWallTime,
  rank,
  row,
  shortest,
}: {
  readonly maxWallTime: number;
  readonly rank: number;
  readonly row: BenchTimeRow;
  readonly shortest: boolean;
}) {
  const className = "group relative block border-t border-bench-line/40 py-2 outline-none transition-colors first:border-t-0 hover:bg-white/[0.035] focus-visible:bg-white/[0.035]";
  const tooltipPositionClass = rank === 1
    ? "top-[calc(100%-4px)]"
    : "bottom-[calc(100%-4px)]";
  const content = (
    <>
      <div className={`pointer-events-none absolute left-0 z-10 w-[280px] rounded border border-bench-line-strong bg-bench-bg px-2 py-1.5 font-mono text-[11px] leading-4 text-bench-muted opacity-0 shadow-2xl shadow-black/30 transition-opacity duration-100 group-hover:opacity-100 group-focus-visible:opacity-100 ${tooltipPositionClass}`}>
        <span className="font-semibold text-bench-text">{row.label}</span> · score {row.score.toFixed(2)}
        {row.hardwareLabel === null ? null : <> · {row.hardwareLabel}</>}
        <br />
        <span className="text-bench-warn-soft">{LIMITATION}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="min-w-0 text-[13px] font-semibold text-bench-text group-hover:text-bench-accent">
          {row.label}
        </span>
        <span className="ml-auto flex items-baseline gap-1.5">
          <span className="rounded-full border border-bench-line-strong px-1.5 py-px font-mono text-[10px] text-bench-text">
            #{rank}
          </span>
          <span className="font-mono text-[11px] tabular-nums text-bench-muted">{row.score.toFixed(2)}</span>
        </span>
      </div>
      <WallTimeBar
        maxWallTimeSeconds={maxWallTime}
        shortest={shortest}
        wallTimeSeconds={row.wallTimeSeconds}
      />
    </>
  );
  return row.href === null ? (
    <div tabIndex={0} className={className}>{content}</div>
  ) : (
    <Link href={row.href} className={className}>{content}</Link>
  );
}

function toBakedTimeRow(run: ModelRun, label: string): readonly BenchTimeRow[] {
  const wallTimeSeconds = run.wall_time_seconds;
  if (
    run.composite === null
    || run.lane !== HEADLINE_LANE
    || !isCompleteRun(run)
    || wallTimeSeconds === null
    || wallTimeSeconds === undefined
    || wallTimeSeconds <= 0
  ) {
    return [];
  }
  return [{
    hardwareLabel: null,
    href: run.run_id === null ? null : runHref(run.run_id),
    id: `baked:${run.run_id ?? label}`,
    label,
    score: run.composite.point,
    wallTimeSeconds,
  }];
}

function toLiveTimeRow(
  row: CommunityBoardRow,
  artifactDetail: CommunityArtifactDetail | undefined,
  pageModelLabel: string,
): readonly BenchTimeRow[] {
  const wallTimeSeconds = row.perf?.wall_time_seconds;
  if (
    !row.headlineComplete
    || row.compositeFull === null
    || wallTimeSeconds === null
    || wallTimeSeconds === undefined
    || wallTimeSeconds <= 0
  ) {
    return [];
  }
  const canonicalName = artifactDetail?.modelLabel ?? row.displayName;
  const contextName = sameModelName(canonicalName, pageModelLabel)
    ? null
    : variantNameInContext(canonicalName, pageModelLabel);
  const quantName = artifactDetail?.quantLabel ?? row.quantLabel ?? "quant unavailable";
  const declaredName = declaredNameIsRedundant(row.displayName, canonicalName, [
    artifactDetail?.quantLabel,
    row.quantLabel,
  ])
    ? ""
    : ` · declared as ${row.displayName}`;
  const gpuName = row.hardware?.gpu_name;
  const hardwareLabel = gpuName === null || gpuName === undefined || gpuName === ""
    ? null
    : formatGpuShort({ name: gpuName, vram_gb: row.hardware?.vram_gb ?? null });
  return [{
    hardwareLabel,
    href: row.detailPath,
    id: `live:${row.submissionId}`,
    label: `${contextName === null ? quantName : `${contextName} · ${quantName}`}${declaredName}`,
    score: communityScore(row.compositeFull).point,
    wallTimeSeconds,
  }];
}

function isCompleteRun(run: ModelRun): boolean {
  if (run.index_version === INDEX_VERSION_V4) return hasCompleteSeason2Coverage(run);
  return ["agentic", "knowledge", "instruction", "tool_calling", "coding", "math"].every((axis) => {
    const axisValue = run.axes[axis];
    return axisValue !== undefined && axisValue.n > 0;
  });
}
