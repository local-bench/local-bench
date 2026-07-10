"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type PendingTicket = {
  readonly model_label: string;
  readonly position: number;
  readonly queued_at: string;
  readonly submission_id: string;
  readonly suite_release_id: string | null;
};

type QueuePayload = {
  readonly cohort_cap: number;
  readonly submissions: readonly PendingTicket[];
  readonly total_pending: number;
};

type QueueState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly value: QueuePayload }
  | { readonly status: "unavailable" };

export function PendingVerificationQueue() {
  const [state, setState] = useState<QueueState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/submissions/queue", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`queue response ${response.status}`);
        return parseQueue(await response.json());
      })
      .then((value) => setState({ status: "ready", value }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState({ status: "unavailable" });
        }
      });
    return () => controller.abort();
  }, []);

  const cap = state.status === "ready" ? state.value.cohort_cap : 5;
  return (
    <section className="overflow-hidden rounded-lg border border-bench-line bg-bench-panel/70" aria-labelledby="verification-queue-title">
      <div className="border-b border-bench-line px-4 py-4">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">community bridge</p>
        <h3 id="verification-queue-title" className="mt-1 text-lg font-semibold text-bench-text">
          Pending agentic verification
        </h3>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-bench-muted">
          The maintainer completes agentic verification on the exact GGUF submitted. Work is FIFO and capped to
          the first {cap} pending tickets; later submissions keep their queue position but are outside the launch cohort.
          A pending ticket is not ranked or verified yet.
        </p>
      </div>
      <QueueBody state={state} />
    </section>
  );
}

function QueueBody({ state }: { readonly state: QueueState }) {
  if (state.status === "loading") {
    return <p className="px-4 py-5 text-sm text-bench-muted">Loading the maintainer queue…</p>;
  }
  if (state.status === "unavailable") {
    return (
      <p className="px-4 py-5 text-sm text-bench-muted">
        The live queue is temporarily unavailable. Individual ticket status remains available on the submission page.
      </p>
    );
  }
  if (state.value.submissions.length === 0) {
    return <p className="px-4 py-5 text-sm text-bench-muted">No completed submissions are waiting for verification.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-bench-text/85">
          <tr>
            <th className="px-4 py-3 font-semibold">Position</th>
            <th className="px-4 py-3 font-semibold">Model ticket</th>
            <th className="px-4 py-3 font-semibold">Suite</th>
            <th className="px-4 py-3 font-semibold">Queued</th>
            <th className="px-4 py-3 font-semibold">State</th>
          </tr>
        </thead>
        <tbody>
          {state.value.submissions.map((ticket) => (
            <tr key={ticket.submission_id} className="border-t border-bench-line/75">
              <td className="px-4 py-3 font-mono text-bench-text">#{ticket.position}</td>
              <td className="px-4 py-3">
                <Link href={`/submission?id=${encodeURIComponent(ticket.submission_id)}`} className="font-semibold text-bench-text hover:text-bench-accent">
                  {ticket.model_label}
                </Link>
              </td>
              <td className="px-4 py-3 font-mono text-xs text-bench-muted">{ticket.suite_release_id ?? "suite pending"}</td>
              <td className="px-4 py-3 font-mono text-xs text-bench-muted">{formatQueuedAt(ticket.queued_at)}</td>
              <td className="px-4 py-3">
                <span className="rounded-full border border-bench-warn/40 bg-bench-warn/10 px-2 py-1 text-xs font-semibold text-bench-warn">
                  Pending verification
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {state.value.total_pending > state.value.cohort_cap ? (
        <p className="border-t border-bench-line px-4 py-3 text-xs leading-5 text-bench-muted">
          {state.value.total_pending - state.value.cohort_cap} additional pending ticket
          {state.value.total_pending - state.value.cohort_cap === 1 ? " is" : "s are"} outside the capped launch cohort.
        </p>
      ) : null}
    </div>
  );
}

export function parseQueue(value: unknown): QueuePayload {
  if (!isRecord(value) || !Number.isInteger(value["cohort_cap"]) || !Number.isInteger(value["total_pending"]) || !Array.isArray(value["submissions"])) {
    throw new Error("invalid pending queue payload");
  }
  const submissions = value["submissions"].map((item) => {
    if (
      !isRecord(item) ||
      !Number.isInteger(item["position"]) ||
      typeof item["model_label"] !== "string" ||
      typeof item["queued_at"] !== "string" ||
      typeof item["submission_id"] !== "string"
    ) {
      throw new Error("invalid pending queue ticket");
    }
    return {
      model_label: item["model_label"],
      position: item["position"] as number,
      queued_at: item["queued_at"],
      submission_id: item["submission_id"],
      suite_release_id: nullableString(item["suite_release_id"]),
    };
  });
  return { cohort_cap: value["cohort_cap"] as number, submissions, total_pending: value["total_pending"] as number };
}

function nullableString(value: unknown): string | null {
  if (value === null || typeof value === "string") return value;
  throw new Error("queue field must be a string or null");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function formatQueuedAt(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toISOString().slice(0, 10);
}
