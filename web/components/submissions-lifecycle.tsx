"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { TrustTierChip } from "@/components/leaderboard-provenance";
import { useLiveCommunityRows } from "@/components/community-live-state";
import type { CommunityBoardRow } from "@/lib/community-data";
import {
  mergeSubmissionLifecycleRows,
  parseSubmissionLifecyclePage,
  type SubmissionDisplayRow,
  type SubmissionLifecycleRow,
} from "@/lib/submission-lifecycle";

const EMPTY_COMMUNITY_ROWS: readonly CommunityBoardRow[] = [];

type LifecycleState =
  | { readonly kind: "loading" }
  | { readonly kind: "unavailable"; readonly message: string }
  | {
    readonly kind: "ready";
    readonly loadingMore: boolean;
    readonly nextCursor: string | null;
    readonly rows: readonly SubmissionLifecycleRow[];
  };

export function SubmissionsLifecycle() {
  const [state, setState] = useState<LifecycleState>({ kind: "loading" });
  const activeRequest = useRef<AbortController | null>(null);
  const community = useLiveCommunityRows(EMPTY_COMMUNITY_ROWS);

  useEffect(() => {
    const controller = new AbortController();
    activeRequest.current = controller;
    void fetchLifecyclePage(null, controller.signal).then((page) => {
      if (page === null) {
        setState({ kind: "unavailable", message: "The public lifecycle endpoint is temporarily unavailable." });
        return;
      }
      setState({ kind: "ready", loadingMore: false, nextCursor: page.nextCursor, rows: page.submissions });
    });
    return () => controller.abort();
  }, []);

  const displayRows = useMemo(() => state.kind === "ready"
    ? mergeSubmissionLifecycleRows(state.rows, community.rows)
    : [], [community.rows, state]);

  function loadMore(): void {
    if (state.kind !== "ready" || state.nextCursor === null || state.loadingMore) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const cursor = state.nextCursor;
    setState({ ...state, loadingMore: true });
    void fetchLifecyclePage(cursor, controller.signal).then((page) => {
      if (page === null) {
        setState((current) => current.kind === "ready" ? { ...current, loadingMore: false } : current);
        return;
      }
      setState((current) => current.kind === "ready" ? {
        kind: "ready",
        loadingMore: false,
        nextCursor: page.nextCursor,
        rows: appendUnique(current.rows, page.submissions),
      } : current);
    });
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Submissions" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">public pipeline</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Submission lifecycle</h1>
        <p className="mt-3 max-w-3xl leading-7 text-bench-muted">
          Follow every public submission from receipt through verification, publication, review holds, or rejection.
          Published tiers come from the live community board.
        </p>
      </header>

      {state.kind === "loading" ? <LifecycleNotice title="Loading submissions" body="Fetching the first lifecycle page." /> : null}
      {state.kind === "unavailable" ? <LifecycleNotice title="Lifecycle unavailable" body={state.message} /> : null}
      {state.kind === "ready" ? (
        <SubmissionsTable
          loadingMore={state.loadingMore}
          nextCursor={state.nextCursor}
          onLoadMore={loadMore}
          rows={displayRows}
        />
      ) : null}
    </main>
  );
}

export function SubmissionsTable({
  loadingMore,
  nextCursor,
  onLoadMore,
  rows,
}: {
  readonly loadingMore: boolean;
  readonly nextCursor: string | null;
  readonly onLoadMore: () => void;
  readonly rows: readonly SubmissionDisplayRow[];
}) {
  return (
    <section className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-bench-line bg-bench-panel">
        <table className="min-w-[900px] w-full border-collapse text-sm">
          <thead className="bg-white/[0.03] text-left font-mono text-xs uppercase tracking-wide text-bench-muted">
            <tr>
              <th className="px-4 py-3">Submission</th>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Submitter</th>
              <th className="px-4 py-3">State</th>
              <th className="px-4 py-3">Published tier</th>
              <th className="px-4 py-3">Details</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.submissionId} className="border-t border-bench-line/70 align-top">
                <td className="px-4 py-3 font-mono text-xs text-bench-text" title={row.submissionId}>
                  {shortSubmissionId(row.submissionId)}
                  <span className="mt-1 block text-[10px] text-bench-muted">{formatInstant(row.submittedAt)}</span>
                </td>
                <td className="px-4 py-3 text-bench-text">
                  {row.communityDetailPath === null
                    ? row.modelLabel
                    : <Link className="hover:text-bench-accent" href={row.communityDetailPath}>{row.modelLabel}</Link>}
                </td>
                <td className="px-4 py-3 text-bench-muted">{row.submitterLabel}</td>
                <td className="px-4 py-3">
                  <span className="font-semibold text-bench-text">{row.stateLabel}</span>
                  {row.reasonLabel === null ? null : <span className="mt-1 block text-xs text-bench-worse">{row.reasonLabel}</span>}
                </td>
                <td className="px-4 py-3">
                  {row.trustLabel === null ? <span className="text-bench-muted">—</span> : <TrustTierChip trustLabel={row.trustLabel} />}
                </td>
                <td className="px-4 py-3">
                  <Link className="font-semibold text-bench-accent hover:underline" href={`/submission?id=${encodeURIComponent(row.submissionId)}`}>
                    View status
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 ? <p className="text-sm text-bench-muted">No public submissions are available.</p> : null}
      {nextCursor === null ? null : (
        <button
          className="rounded-md border border-bench-accent/60 px-4 py-2 text-sm font-semibold text-bench-accent transition-colors hover:bg-bench-accent/10 disabled:cursor-wait disabled:opacity-60"
          disabled={loadingMore}
          onClick={onLoadMore}
          type="button"
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}

async function fetchLifecyclePage(cursor: string | null, signal: AbortSignal) {
  try {
    const query = cursor === null ? "" : encodeURIComponent(cursor);
    const response = await fetch(`/api/submissions/list?cursor=${query}`, {
      headers: { accept: "application/json" },
      signal,
    });
    if (!response.ok) return null;
    return parseSubmissionLifecyclePage(await response.json());
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return null;
    return null;
  }
}

function appendUnique(
  current: readonly SubmissionLifecycleRow[],
  incoming: readonly SubmissionLifecycleRow[],
): readonly SubmissionLifecycleRow[] {
  const byId = new Map(current.map((row) => [row.submission_id, row] as const));
  for (const row of incoming) byId.set(row.submission_id, row);
  return [...byId.values()];
}

function shortSubmissionId(value: string): string {
  return value.length <= 18 ? value : `${value.slice(0, 15)}…`;
}

function formatInstant(value: string): string {
  return value.replace("T", " ").replace(/(?:\.\d+)?Z$/u, " UTC");
}

function LifecycleNotice({ title, body }: { readonly body: string; readonly title: string }) {
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">{title}</h2>
      <p className="mt-2 text-bench-muted">{body}</p>
    </section>
  );
}
