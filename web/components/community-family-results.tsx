import Link from "next/link";
import { AttributionChip } from "@/components/leaderboard-provenance";
import { formatScore } from "@/lib/format";
import type { CommunityBoardRow } from "@/lib/community-data";

export function CommunityFamilyResults({ rows }: { readonly rows: readonly CommunityBoardRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section
      aria-label="Community results for this family"
      className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/60"
    >
      <div className="border-b border-bench-line px-4 py-3">
        <h2 className="text-lg font-semibold text-bench-text">Community results for this family</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-bench-muted">
          Associated from repository owner-declared card metadata. The lineage is unverified and does not imply
          endorsement by the base model author.
        </p>
      </div>
      <div className="grid gap-3 p-4">
        {rows.map((row) => (
          <article key={row.artifactSha256} className="rounded border border-bench-line/75 bg-bench-panel-2/70 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold text-bench-text">{row.displayName}</h3>
                  <AttributionChip source="community" />
                </div>
                <p className="mt-1 font-mono text-xs text-bench-muted">
                  {row.quantLabel ?? "quant unavailable"} · not independently verified
                </p>
              </div>
              {row.detailPath === null ? (
                <span
                  className="rounded border border-bench-line px-2.5 py-1.5 text-sm font-medium text-bench-muted"
                  title="detail page publishes with the next site deploy"
                >
                  Detail available next deploy
                </span>
              ) : (
                <Link
                  href={row.detailPath}
                  className="rounded border border-bench-line px-2.5 py-1.5 text-sm font-medium text-bench-accent transition-colors hover:border-bench-accent hover:text-bench-text"
                >
                  View community record
                </Link>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-bench-muted">
              <span>partial {percentage(row.partialComposite)}</span>
              <span>measured {percentage(row.measuredHeadlineWeight)}</span>
              <span>missing {percentage(row.missingHeadlineWeight)}</span>
            </div>
            <p className="mt-3 text-xs text-bench-muted">HF model-card-declared lineage (unverified)</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function percentage(value: number | null): string {
  return value === null ? "unavailable" : `${formatScore(value * 100)}%`;
}
