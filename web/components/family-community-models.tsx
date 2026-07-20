"use client";

import Link from "next/link";
import { CommunityFreshness, useLiveCommunityRows } from "@/components/community-live-state";
import { SubmissionIdentity } from "@/components/leaderboard-provenance";
import { toDisplayScore } from "@/lib/board-adapter";
import type { CommunityBoardRow } from "@/lib/community-data";
import type { FamilyModelSummary } from "@/lib/families";
import type { FamilyResolutionContext } from "@/lib/family-resolution";
import { formatScore } from "@/lib/format";

type FamilyModelTableLiveProps = {
  readonly family: string;
  readonly models: readonly FamilyModelSummary[];
  readonly resolutionContext: FamilyResolutionContext;
  readonly rows: readonly CommunityBoardRow[];
};

export function FamilyModelTableLive({
  family,
  models,
  resolutionContext,
  rows,
}: FamilyModelTableLiveProps) {
  const state = useLiveCommunityRows(rows, true, resolutionContext);
  return (
    <>
      <div className="border-b border-bench-line px-5 py-2">
        <CommunityFreshness state={state} />
      </div>
      <FamilyModelTable family={family} models={models} rows={state.rows} />
    </>
  );
}

export function FamilyModelTable({
  family,
  models,
  rows,
}: {
  readonly family: string;
  readonly models: readonly FamilyModelSummary[];
  readonly rows: readonly CommunityBoardRow[];
}) {
  const entries = familyModelListEntries(models, rows, family);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead className="bg-white/[0.03] text-left font-mono text-xs uppercase tracking-wide text-bench-muted">
          <tr>
            <th className="px-5 py-3 font-semibold">Model</th>
            <th className="px-5 py-3 font-semibold">Headline composite</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => entry.source === "maintainer"
            ? <MaintainerFamilyRow key={entry.model.slug} entry={entry} />
            : <CommunityFamilyRow key={entry.row.submissionId} entry={entry} />)}
        </tbody>
      </table>
    </div>
  );
}

export function AwaitingFamilyAssignment({ rows }: { readonly rows: readonly CommunityBoardRow[] }) {
  const awaiting = awaitingFamilyAssignmentRows(rows);
  if (awaiting.length === 0) return null;
  return (
    <section className="mt-6 overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82">
      <div className="border-b border-bench-line px-5 py-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-warn">Needs catalog lineage</p>
        <h2 className="mt-1 text-2xl font-semibold text-bench-text">Awaiting family assignment</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          These complete self-reported runs remain visible, but their declared family is not authoritative enough to attach them to a model family.
        </p>
      </div>
      <div className="grid gap-px bg-bench-line sm:grid-cols-2 xl:grid-cols-3">
        {awaiting.map((row) => (
          <article key={row.submissionId} className="bg-bench-panel p-4">
            {row.detailPath === null ? (
              <h3 className="font-semibold text-bench-text">{row.displayName}</h3>
            ) : (
              <h3><Link href={row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">{row.displayName}</Link></h3>
            )}
            <p className="mt-1 font-mono text-xs text-bench-muted">
              {formatScore(toDisplayScore(row.compositeFull ?? 0))} · {row.family ?? "family not declared"}
            </p>
            <div className="mt-2"><SubmissionIdentity displayName={row.submitterDisplayName} /></div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function resolvedCommunityRowsForFamily(
  rows: readonly CommunityBoardRow[],
  family: string,
): readonly CommunityBoardRow[] {
  return rows.filter((row) =>
    row.headlineComplete
    && row.compositeFull !== null
    && row.confidence !== null
    && row.confidence !== undefined
    && row.confidence !== "declared-family"
    && row.familyLabel === family,
  );
}

export function awaitingFamilyAssignmentRows(
  rows: readonly CommunityBoardRow[],
): readonly CommunityBoardRow[] {
  return rows.filter((row) =>
    row.headlineComplete
    && row.compositeFull !== null
    && (row.confidence === null || row.confidence === undefined || row.confidence === "declared-family"),
  );
}

export function familyModelListEntries(
  models: readonly FamilyModelSummary[],
  rows: readonly CommunityBoardRow[],
  family: string,
): readonly FamilyListEntry[] {
  const communityRows = resolvedCommunityRowsForFamily(rows, family);
  const communityModelPaths = new Set(communityRows.flatMap((row) => row.detailPath === null ? [] : [row.detailPath]));
  return [
    ...models
      .filter((entry) => entry.score !== null || !communityModelPaths.has(`/model/${entry.model.slug}`))
      .map((entry) => ({ ...entry, source: "maintainer" as const })),
    ...communityRows.map((row) => ({
      row,
      score: toDisplayScore(row.compositeFull ?? 0),
      source: "community" as const,
    })),
  ].sort(compareFamilyListEntries);
}

export type MaintainerFamilyEntry = FamilyModelSummary & { readonly source: "maintainer" };
export type CommunityFamilyEntry = {
  readonly row: CommunityBoardRow;
  readonly score: number;
  readonly source: "community";
};
export type FamilyListEntry = MaintainerFamilyEntry | CommunityFamilyEntry;

function MaintainerFamilyRow({ entry }: { readonly entry: MaintainerFamilyEntry }) {
  return (
    <tr className="border-t border-bench-line/70">
      <td className="px-5 py-3">
        <Link href={`/model/${entry.model.slug}`} className="font-semibold text-bench-text hover:text-bench-accent">
          {entry.model.model_label}
        </Link>
      </td>
      <td className="px-5 py-3 font-mono text-bench-muted">
        {entry.score === null ? "awaiting a complete run" : formatScore(entry.score)}
      </td>
    </tr>
  );
}

function CommunityFamilyRow({ entry }: { readonly entry: CommunityFamilyEntry }) {
  return (
    <tr className="border-t border-bench-line/70 bg-white/[0.018]">
      <td className="px-5 py-3">
        {entry.row.detailPath === null ? (
          <span className="font-semibold text-bench-text">{entry.row.displayName}</span>
        ) : (
          <Link href={entry.row.detailPath} className="font-semibold text-bench-text hover:text-bench-accent">
            {entry.row.displayName}
          </Link>
        )}
        <div className="mt-1"><SubmissionIdentity displayName={entry.row.submitterDisplayName} /></div>
      </td>
      <td className="px-5 py-3 font-mono text-bench-muted">{formatScore(entry.score)}</td>
    </tr>
  );
}

function compareFamilyListEntries(left: FamilyListEntry, right: FamilyListEntry): number {
  if (left.score !== null && right.score !== null) return right.score - left.score;
  if (left.score !== null) return -1;
  if (right.score !== null) return 1;
  return familyEntryLabel(left).localeCompare(familyEntryLabel(right), "en", { numeric: true, sensitivity: "base" });
}

function familyEntryLabel(entry: FamilyListEntry): string {
  return entry.source === "maintainer" ? entry.model.model_label : entry.row.displayName;
}
