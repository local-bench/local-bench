"use client";

import { CommunityFreshness, type LiveCommunityState } from "@/components/community-live-state";
import { ProjectRunBadge, SubmissionIdentity } from "@/components/leaderboard-provenance";
import type { CommunityBoardRow, CommunityLineage } from "@/lib/community-data";
import { huggingFaceRepoUrl } from "@/lib/community-links";
import { toDisplayScore } from "@/lib/board-adapter";
import { axisLabel, formatScore } from "@/lib/format";

export function CommunityFamilyResultsLive({
  rows,
  state,
}: {
  readonly rows: readonly CommunityBoardRow[];
  readonly state: LiveCommunityState;
}) {
  return (
    <div className="space-y-2">
      <CommunityFreshness state={state} />
      <CommunityFamilyResults rows={rows} />
    </div>
  );
}

export function CommunityFamilyResults({ rows }: { readonly rows: readonly CommunityBoardRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section aria-label="Reported runs for this family" className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/60">
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Reported runs</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Project and community detail lives on the model family page. Complete reports rank on the global board;
          incomplete historical reports remain here as evidence-backed diagnostics.
        </p>
      </div>
      <div className="grid gap-3 p-4">
        {rows.map((row) => <ReportedRun key={row.submissionId} row={row} />)}
      </div>
    </section>
  );
}

function ReportedRun({ row }: { readonly row: CommunityBoardRow }) {
  return (
    <article className="rounded border border-bench-line/75 bg-bench-panel-2/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-bench-text">{row.displayName}</h3>
          <p className="mt-1 font-mono text-xs text-bench-muted">{row.quantLabel ?? "quant unavailable"}</p>
        </div>
        <div className="text-right font-mono text-xs">
          {row.headlineComplete && row.compositeFull !== null ? (
            <>
              <div className="font-semibold text-bench-text">{formatScore(toDisplayScore(row.compositeFull))}</div>
              <div className="text-bench-muted">{row.globalRank === null ? "complete ranked run" : `global rank #${row.globalRank}`}</div>
            </>
          ) : <div className="text-bench-warn">historical incomplete report</div>}
        </div>
      </div>
      <div className="mt-3">
        {row.origin === "project_anchor" ? (
          <ProjectRunBadge badge={row.badge} origin={row.origin} />
        ) : (
          <SubmissionIdentity displayName={row.submitterDisplayName} />
        )}
      </div>
      <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label="Per-axis breakdown">
        {Object.entries(row.axes ?? {}).sort(([left], [right]) => left.localeCompare(right)).map(([axis, value]) => (
          <div key={axis} className="rounded border border-bench-line/70 bg-bench-bg/35 px-3 py-2">
            <dt className="font-mono text-[10px] uppercase text-bench-muted">{axisLabel(axis)}</dt>
            <dd className="mt-1 font-mono text-sm text-bench-text">
              {value.status === "measured" && value.score !== null && value.score !== undefined
                ? `${formatScore(toDisplayScore(value.score))} · n=${value.n}`
                : value.status.replace("_", " ")}
            </dd>
          </div>
        ))}
      </dl>
      <details className="mt-4 border-t border-bench-line pt-3 text-sm text-bench-muted">
        <summary className="cursor-pointer font-medium text-bench-accent">Run details and evidence identity</summary>
        <dl className="mt-3 grid gap-2 font-mono text-xs sm:grid-cols-2">
          <div><dt className="text-bench-muted">submission</dt><dd className="break-all text-bench-text">{row.submissionId}</dd></div>
          <div><dt className="text-bench-muted">artifact sha256</dt><dd className="break-all text-bench-text">{row.artifactSha256}</dd></div>
        </dl>
        {row.lineage === undefined ? null : <LineageDetails lineage={row.lineage} />}
      </details>
    </article>
  );
}

function LineageDetails({ lineage }: { readonly lineage: CommunityLineage }) {
  return (
    <section className="mt-4" aria-label="Reported artifact lineage">
      <h4 className="font-semibold text-bench-text">Reported artifact lineage</h4>
      <p className="mt-1">{lineage.association.note}</p>
      <a
        href={huggingFaceRepoUrl(lineage.repo.id)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-2 inline-block font-mono text-xs text-bench-accent hover:text-bench-text"
      >
        {lineage.repo.id} · {lineage.repo.revision.slice(0, 7)}
      </a>
      <ol className="mt-3 grid gap-2">
        {lineage.card_declared_edges.map((edge) => (
          <li key={`${edge.child}@${edge.child_revision}`} className="rounded border border-bench-line p-3">
            {edge.child} @ {edge.child_revision.slice(0, 7)} → {edge.base} @ {edge.base_revision?.slice(0, 7) ?? "unresolved"}
          </li>
        ))}
      </ol>
    </section>
  );
}
