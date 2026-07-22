"use client";

import Link from "next/link";
import {
  AwaitingFamilyAssignment,
  familyModelListEntries,
} from "@/components/family-community-models";
import { FamilyLogoMark } from "@/components/family-logo-mark";
import { CommunityFreshness, useLiveCommunityRows } from "@/components/community-live-state";
import { SubmissionIdentity } from "@/components/leaderboard-provenance";
import type { CommunityBoardRow } from "@/lib/community-data";
import { familySummaries } from "@/lib/families";
import type { FamilyResolutionContext } from "@/lib/family-resolution";
import { formatScore } from "@/lib/format";
import { familyHref, modelHref } from "@/lib/routes";
import type { IndexModel } from "@/lib/schemas";

type FamilyDirectoryProps = {
  readonly communityRows: readonly CommunityBoardRow[];
  readonly models: readonly IndexModel[];
  readonly resolutionContext: FamilyResolutionContext;
};

export function FamilyDirectory({ communityRows, models, resolutionContext }: FamilyDirectoryProps) {
  const families = familySummaries(models, resolutionContext);
  const state = useLiveCommunityRows(communityRows, true, resolutionContext);
  return (
    <>
      <section id="families" className="scroll-mt-24 overflow-hidden rounded-lg border border-bench-line bg-bench-panel/82">
        <div className="border-b border-bench-line px-5 py-4">
          <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">Primary browse path</p>
          <h1 className="mt-1 text-2xl font-semibold text-bench-text">Browse by model family</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
            Start with the base-model family, then compare its fine-tunes, distills, quants, reported runs, VRAM,
            and per-axis results in one place.
          </p>
          <div className="mt-2"><CommunityFreshness state={state} /></div>
        </div>
        <div className="grid gap-px bg-bench-line sm:grid-cols-2 xl:grid-cols-3">
          {families.map((summary) => {
            const entries = familyModelListEntries(summary.models, state.rows, summary.family);
            const bestScore = entries.find((entry) => entry.score !== null)?.score ?? null;
            const benchmarkSlug = summary.models[0]?.model.slug;
            return (
              <article id={summary.slug} key={summary.family} className="scroll-mt-48 bg-bench-panel p-4 sm:scroll-mt-32 lg:scroll-mt-24">
                <div className="flex items-center gap-2">
                  <FamilyLogoMark modelLabel={summary.family} size={20} />
                  <h2 className="font-semibold text-bench-text">
                    <Link href={familyHref(summary.slug)} className="hover:text-bench-accent">
                      {summary.family}
                    </Link>
                  </h2>
                </div>
                <p className="mt-2 font-mono text-xs text-bench-muted">
                  {entries.length} model{entries.length === 1 ? "" : "s"}
                  {bestScore === null ? " · awaiting a complete run" : ` · best ${formatScore(bestScore)}`}
                  {bestScore === null && benchmarkSlug !== undefined ? (
                    <> · <Link href={`/submit/?model=${encodeURIComponent(benchmarkSlug)}`} className="text-bench-warn hover:underline">benchmark it →</Link></>
                  ) : null}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {entries.slice(0, 5).map((entry) => entry.source === "maintainer" ? (
                    <Link
                      key={entry.model.slug}
                      href={modelHref(entry.model.slug)}
                      className="rounded border border-bench-line px-2 py-1 text-xs text-bench-muted hover:border-bench-accent hover:text-bench-text"
                    >
                      {entry.model.model_label}
                    </Link>
                  ) : (
                    <span key={entry.row.submissionId} className="rounded border border-bench-accent/40 bg-bench-accent/10 px-2 py-1 text-xs text-bench-text">
                      {entry.row.detailPath === null ? entry.row.displayName : (
                        <Link href={entry.row.detailPath} className="hover:text-bench-accent">{entry.row.displayName}</Link>
                      )}
                      {/* Project-run rows carry no badge in the directory preview (owner call, 2026-07-22). */}
                      {entry.row.origin === "project_anchor" ? null : (
                        <span className="ml-1">
                          <SubmissionIdentity displayName={entry.row.submitterDisplayName} />
                        </span>
                      )}
                    </span>
                  ))}
                </div>
                <Link href={familyHref(summary.slug)} className="mt-4 inline-flex text-sm font-semibold text-bench-accent hover:underline">
                  View family →
                </Link>
              </article>
            );
          })}
        </div>
      </section>
      <AwaitingFamilyAssignment rows={state.rows} />
    </>
  );
}
