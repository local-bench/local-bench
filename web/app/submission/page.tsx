"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { useLiveCommunityRows } from "@/components/community-live-state";
import { TrustTierChip } from "@/components/leaderboard-provenance";
import type { CommunityBoardRow } from "@/lib/community-data";
import { reasonCodeLabel } from "@/lib/submission-lifecycle";
import {
  SubmissionStatusSchema,
  type HistoryItem,
  type SubmissionStatus,
} from "@/lib/submission-status";
import { PUBLISH_COPY, statusCopy } from "./status-copy";

const EMPTY_COMMUNITY_ROWS: readonly CommunityBoardRow[] = [];

type LoadState =
  | { readonly kind: "empty" }
  | { readonly kind: "loading"; readonly submissionId: string }
  | { readonly kind: "loaded"; readonly value: SubmissionStatus }
  | { readonly kind: "not_found"; readonly submissionId: string }
  | { readonly kind: "error"; readonly message: string };

export default function SubmissionPage() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "empty" });
  const requestSequence = useRef(0);
  const community = useLiveCommunityRows(EMPTY_COMMUNITY_ROWS);

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("id")?.trim() ?? "";
    if (initial.length > 0) {
      setQuery(initial);
      startLoad(initial);
    }
  }, []);

  const title = useMemo(() => {
    if (state.kind === "loaded") {
      return state.value.submission_id;
    }
    if (state.kind === "loading" || state.kind === "not_found") {
      return state.submissionId;
    }
    return "Submission status";
  }, [state]);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const submissionId = query.trim();
    if (submissionId.length === 0) {
      requestSequence.current += 1;
      setState({ kind: "empty" });
      window.history.replaceState(null, "", "/submission");
      return;
    }
    window.history.replaceState(null, "", `/submission?id=${encodeURIComponent(submissionId)}`);
    startLoad(submissionId);
  }

  function startLoad(submissionId: string): void {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    void loadSubmission(submissionId, (nextState) => {
      if (requestSequence.current === requestId) {
        setState(nextState);
      }
    });
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-5 py-8 lg:px-8">
      <Breadcrumbs items={[{ label: "Leaderboard", href: "/" }, { label: "Submission status" }]} />
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">submission lifecycle</p>
        <h1 className="mt-2 break-all text-4xl font-semibold text-bench-text">{title}</h1>
        <p className="mt-3 leading-7 text-bench-muted">
          Track the server-side state for a submitted result bundle. The id is printed by{" "}
          <code className="font-mono text-bench-text">localbench submit run</code>.
        </p>
      </header>

      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-bench-line bg-bench-panel p-4 sm:grid-cols-[1fr_auto]">
        <label className="grid gap-2 text-sm text-bench-muted">
          <span className="font-mono text-xs uppercase tracking-wide">submission id</span>
          <input
            className="min-w-0 rounded-md border border-bench-line bg-bench-panel-2 px-3 py-2 font-mono text-sm text-bench-text outline-none transition-colors focus:border-bench-accent"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="sub_..."
            type="text"
            value={query}
          />
        </label>
        <button
          className="self-end rounded-md border border-bench-accent/60 px-4 py-2 text-sm font-semibold text-bench-accent transition-colors hover:border-bench-accent hover:bg-bench-accent/10 focus:outline-none focus:ring-2 focus:ring-bench-accent/40"
          type="submit"
        >
          Check
        </button>
      </form>

      {renderState(state, community.rows)}
    </main>
  );
}

function renderState(state: LoadState, communityRows: readonly CommunityBoardRow[]) {
  switch (state.kind) {
    case "empty":
      return (
        <section className="rounded-lg border border-bench-line bg-bench-panel p-5 text-bench-muted">
          <h2 className="text-lg font-semibold text-bench-text">Find your id</h2>
          <p className="mt-3 leading-7">
            After upload, the CLI prints a line like <code className="font-mono text-bench-text">submission sub_...</code>.
            Paste that id here or open <code className="font-mono text-bench-text">/submission?id=&lt;submission_id&gt;</code>.
          </p>
        </section>
      );
    case "loading":
      return <StatusPanel tone="text-bench-accent" title="Loading" body={`Fetching ${state.submissionId}`} />;
    case "not_found":
      return (
        <StatusPanel
          tone="text-bench-warn"
          title="Unknown submission"
          body={`No public submission record exists for ${state.submissionId}. Check the id printed by the CLI.`}
        />
      );
    case "error":
      return <StatusPanel tone="text-bench-worse" title="Fetch error" body={state.message} />;
    case "loaded":
      return (
        <SubmissionDetails
          liveRow={communityRows.find((row) => row.submissionId === state.value.submission_id)}
          value={state.value}
        />
      );
    default:
      return assertNever(state);
  }
}

export function SubmissionDetails({
  liveRow,
  value,
}: {
  readonly liveRow?: CommunityBoardRow | undefined;
  readonly value: SubmissionStatus;
}) {
  const copy = statusCopy(value.status);
  const reason = value.reason_code === null || value.reason_code === undefined
    ? value.status_reason
    : reasonCodeLabel(value.reason_code);
  const trustLabel = value.trust_label ?? value.tier ?? liveRow?.trust?.trust_label ?? null;
  return (
    <section className="grid gap-5">
      <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <p className={`font-mono text-xs font-semibold uppercase tracking-wide ${copy.tone}`}>{copy.label}</p>
        <h2 className="mt-2 text-xl font-semibold text-bench-text">Current state</h2>
        <p className="mt-3 leading-7 text-bench-muted">{copy.body}</p>
        <p className="mt-2 leading-7 text-bench-muted">{copy.next}</p>
        <p className="mt-4 rounded-md border border-bench-line bg-bench-panel-2 p-3 text-sm text-bench-muted">
          {PUBLISH_COPY[value.publish_state]}
        </p>
        {value.publish_state === "published" && trustLabel !== null ? (
          <div className="mt-3 flex items-center gap-2 text-sm text-bench-muted">
            <span>Published tier</span>
            <TrustTierChip trustLabel={trustLabel} />
          </div>
        ) : null}
        {value.status === "rejected" && reason ? (
          <p className="mt-3 rounded-md border border-bench-worse/40 bg-bench-worse/[0.08] p-3 text-sm text-bench-worse">
            {reason}
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-bench-line bg-bench-panel p-5">
        <h2 className="text-lg font-semibold text-bench-text">Bundle</h2>
        <dl className="mt-4 grid gap-3 text-sm">
          <Detail label="submission_id" value={value.submission_id} />
          <Detail label="raw_bundle_sha256" value={value.raw_bundle_sha256 ?? "n/a"} />
          <Detail label="suite_release_id" value={value.suite_release_id ?? "n/a"} />
          <Detail label="submitter_display_name" value={value.submitter_display_name ?? "n/a"} />
        </dl>
      </div>

      <HistoryTimeline history={value.history ?? []} />
    </section>
  );
}

function Detail({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="grid gap-1 rounded-md border border-bench-line bg-bench-panel-2 p-3 sm:grid-cols-[190px_1fr]">
      <dt className="font-mono text-xs text-bench-muted">{label}</dt>
      <dd className="break-all font-mono text-xs text-bench-text">{value}</dd>
    </div>
  );
}

function HistoryTimeline({ history }: { readonly history: readonly HistoryItem[] }) {
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <h2 className="text-lg font-semibold text-bench-text">History</h2>
      {history.length === 0 ? (
        <p className="mt-3 text-sm text-bench-muted">No transition rows have been recorded yet.</p>
      ) : (
        <ol className="mt-4 grid gap-3">
          {history.map((item) => (
            <li key={`${item.created_at}-${item.to_status}`} className="rounded-md border border-bench-line bg-bench-panel-2 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs uppercase text-bench-accent">{item.to_status}</span>
                <span className="font-mono text-xs text-bench-muted">{item.actor}</span>
                <span className="font-mono text-xs text-bench-muted">{item.created_at}</span>
              </div>
              {item.reason ? <p className="mt-2 text-sm text-bench-muted">{item.reason}</p> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function StatusPanel({ title, body, tone }: { readonly body: string; readonly title: string; readonly tone: string }) {
  return (
    <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
      <p className={`font-mono text-xs font-semibold uppercase tracking-wide ${tone}`}>{title}</p>
      <p className="mt-3 break-words leading-7 text-bench-muted">{body}</p>
    </section>
  );
}

async function loadSubmission(submissionId: string, setState: (state: LoadState) => void): Promise<void> {
  setState({ kind: "loading", submissionId });
  try {
    const response = await fetch(`/api/submissions/${encodeURIComponent(submissionId)}`, {
      headers: { accept: "application/json" },
    });
    if (response.status === 404) {
      setState({ kind: "not_found", submissionId });
      return;
    }
    if (!response.ok) {
      setState({ kind: "error", message: `status endpoint returned HTTP ${response.status}` });
      return;
    }
    const parsed = SubmissionStatusSchema.safeParse(await response.json());
    if (!parsed.success) {
      setState({ kind: "error", message: "status endpoint returned an unexpected response shape" });
      return;
    }
    setState({ kind: "loaded", value: parsed.data });
  } catch (error) {
    setState({ kind: "error", message: error instanceof Error ? error.message : "status fetch failed" });
  }
}

function assertNever(value: never): never {
  throw new Error(`unhandled state: ${JSON.stringify(value)}`);
}
