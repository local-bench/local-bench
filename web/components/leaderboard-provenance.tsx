import Link from "next/link";
import type { AgenticProvenance, BoardOrigin, IndexModel } from "@/lib/schemas";

type ProvenanceModel = {
  readonly agentic_provenance?: AgenticProvenance | undefined;
  readonly axes: IndexModel["axes"];
  readonly origin?: BoardOrigin | undefined;
  readonly trust_label?: string | undefined;
};

export function ProvenanceLabels({ model }: { readonly model: ProvenanceModel }) {
  const trust = trustChip(model);
  const agentic = agenticChip(model);
  if (trust === null && agentic === null) {
    return null;
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {trust}
      {agentic}
    </div>
  );
}

export function SubmitterCell({ model }: { readonly model: IndexModel }) {
  const displayName = model.submitter_display_name ?? model.submitted_by;
  if (displayName === null || displayName === undefined || displayName === "") {
    return <span className="font-mono text-xs text-bench-muted">—</span>;
  }
  return <span className="text-xs text-bench-muted">submitted by {displayName}</span>;
}

function trustChip(model: ProvenanceModel) {
  if (model.origin === undefined && model.trust_label === undefined) {
    return null;
  }
  const origin = model.origin ?? originFromTrustLabel(model.trust_label);
  const anchor = origin === "project_anchor";
  return (
    <span
      className={[
        "inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold uppercase",
        anchor
          ? "border-bench-anchor/45 bg-bench-anchor/10 text-bench-anchor"
          : "border-bench-community/35 bg-bench-community/10 text-bench-community",
      ].join(" ")}
      title={model.trust_label ?? origin}
    >
      {anchor ? "project anchor" : "community"}
    </span>
  );
}

function agenticChip(model: ProvenanceModel) {
  if (model.axes["agentic"] === undefined || model.agentic_provenance === undefined || model.agentic_provenance === "none") {
    return null;
  }
  return (
    <Link
      href="/methodology"
      className="inline-flex rounded border border-bench-accent/45 bg-bench-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-accent hover:bg-bench-accent/15"
      title="Agentic provenance label; methodology explains attested and self-reported rows"
    >
      {agenticProvenanceLabel(model.agentic_provenance)}
    </Link>
  );
}

function originFromTrustLabel(trustLabel: string | undefined): BoardOrigin {
  return trustLabel === "project_anchor" ? "project_anchor" : "community";
}

function agenticProvenanceLabel(value: AgenticProvenance): string {
  switch (value) {
    case "none":
      return "";
    case "project_attested":
      return "attested";
    case "self_reported":
      return "self-reported";
    default:
      return assertNever(value);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled agentic provenance: ${String(value)}`);
}
