import type { BoardOrigin, IndexModel } from "@/lib/schemas";

// The Run-by column is uniformly name-based (owner call, 2026-07-23): a "project run"
// chip on every maintainer row carried no differential information — the submitter NAME
// is the differential. Maintainer rows attribute to the project by name, in the same
// visual grammar as community submitters, minus the "unverified" qualifier (maintainer
// runs are attested).
export function ProjectRunAttribution({
  badge,
  origin,
}: {
  readonly badge?: "project-run" | undefined;
  readonly origin: BoardOrigin | undefined;
}) {
  if (badge !== "project-run" && origin !== "project_anchor") return null;
  return (
    <span
      className="font-mono text-[10px] leading-4 text-bench-muted"
      title="Run by the local-bench project on the reference rig"
    >
      run by local-bench
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

export function AgenticProvenanceChip({ value }: { readonly value: "attested" | "self-reported" }) {
  return (
    <span className="inline-flex rounded border border-bench-accent/45 bg-bench-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-accent">
      {value}
    </span>
  );
}

export function ProvenanceLabels({ model }: { readonly model: Pick<IndexModel, "badge" | "origin"> }) {
  return <ProjectRunAttribution badge={model.badge} origin={model.origin} />;
}

export function RunByCell({ model }: { readonly model: IndexModel }) {
  if (model.badge === "project-run" || model.origin === "project_anchor") {
    return <ProjectRunAttribution badge={model.badge} origin={model.origin} />;
  }
  if (model.score_status === "measured") {
    return <SubmissionIdentity displayName={model.submitter_display_name ?? model.submitted_by} />;
  }
  return <span className="font-mono text-xs text-bench-muted">—</span>;
}
