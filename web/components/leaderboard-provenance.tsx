import type { BoardOrigin, IndexModel } from "@/lib/schemas";

export function ProjectRunBadge({
  badge,
  origin,
}: {
  readonly badge?: "project-run" | undefined;
  readonly origin: BoardOrigin | undefined;
}) {
  if (badge !== "project-run" && origin !== "project_anchor") return null;
  return (
    <span
      className="inline-flex rounded border border-bench-accent/40 bg-bench-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-accent"
      title="This benchmark was run by the local-bench project"
    >
      project run
    </span>
  );
}

export function SubmissionIdentity({
  displayName,
  emptyLabel = "submitter not provided",
}: {
  readonly displayName: string | null | undefined;
  readonly emptyLabel?: string;
}) {
  return (
    <span className="font-mono text-[10px] leading-4 text-bench-muted">
      submitted as {displayName?.trim() || emptyLabel} — unverified
    </span>
  );
}

export function ProvenanceLabels({ model }: { readonly model: Pick<IndexModel, "badge" | "origin"> }) {
  return <ProjectRunBadge badge={model.badge} origin={model.origin} />;
}

export function RunByCell({ model }: { readonly model: IndexModel }) {
  if (model.badge === "project-run" || model.origin === "project_anchor") {
    return <ProjectRunBadge badge={model.badge} origin={model.origin} />;
  }
  if (model.score_status === "measured") {
    return <SubmissionIdentity displayName={model.submitter_display_name ?? model.submitted_by} />;
  }
  return <span className="font-mono text-xs text-bench-muted">—</span>;
}
