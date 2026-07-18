import Link from "next/link";
import { trustTierLabel } from "@/lib/community-live";
import type { AgenticProvenance, IndexModel } from "@/lib/schemas";

type ProvenanceModel = {
  readonly agentic_provenance?: AgenticProvenance | undefined;
  readonly axes: IndexModel["axes"];
  readonly composite_static?: IndexModel["composite_static"];
  readonly trust_label?: string | undefined;
  readonly verdict_source?: string | null | undefined;
};

export function ProvenanceLabels({ model }: { readonly model: ProvenanceModel }) {
  const agentic = agenticChip(model);
  const staticTrust = staticTrustChip(model);
  if (agentic === null && staticTrust === null) {
    return null;
  }
  return <div className="mt-2 flex flex-wrap gap-1.5">{agentic}{staticTrust}</div>;
}

export function staticTrustChip(model: ProvenanceModel) {
  if (model.axes["agentic"] !== undefined || model.composite_static == null) return null;
  const verified = model.trust_label === "project_anchor" && model.verdict_source === "verifier";
  return (
    <Link
      href="/methodology"
      className="inline-flex rounded border border-bench-line bg-white/[0.025] px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-muted hover:text-bench-text"
      title="Static Index provenance; methodology explains the maintainer verification gate"
    >
      {verified ? "maintainer-verified" : "provenance pending"}
    </Link>
  );
}

export function TrustTierChip({ trustLabel }: { readonly trustLabel: string }) {
  const known = trustLabel === "project_anchor"
    || trustLabel === "community_re_scored"
    || trustLabel === "community_self_submitted";
  return (
    <span className={known
      ? "inline-flex rounded border border-bench-accent/35 bg-bench-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-accent"
      : "inline-flex rounded border border-bench-muted/40 bg-bench-muted/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-muted"}
    >
      {trustTierLabel(trustLabel)}
    </span>
  );
}

export function AgenticProvenanceChip({ value }: { readonly value: string }) {
  if (value === "none") return null;
  const known = value === "project_attested" || value === "self_reported"
    || value === "attested" || value === "self-reported";
  return (
    <span className={known
      ? "inline-flex rounded border border-bench-accent/45 bg-bench-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-accent"
      : "inline-flex rounded border border-bench-muted/40 bg-bench-muted/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-bench-muted"}
    >
      {agenticProvenanceLabel(value)}
    </span>
  );
}

// Who ran the benchmark: community submissions carry the submitter's credit line; every other
// measured row was run by the project itself and is credited to local-bench. Catalog shells and
// demo fixtures were run by nobody, so they show a placeholder.
export function RunByCell({ model }: { readonly model: IndexModel }) {
  const submitter = model.submitter_display_name ?? model.submitted_by;
  if (submitter !== null && submitter !== undefined && submitter !== "") {
    return <span className="text-xs text-bench-muted">submitted by {submitter}</span>;
  }
  if (model.score_status === "measured" && !model.demo) {
    return <AttributionChip source="local-bench" />;
  }
  return <span className="font-mono text-xs text-bench-muted">—</span>;
}

export function AttributionChip({ source }: { readonly source: "community" | "local-bench" }) {
  const community = source === "community";
  return (
    <span
      className={community
        ? "inline-flex rounded border border-bench-muted/40 bg-bench-muted/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-muted"
        : "inline-flex rounded border border-bench-accent/35 bg-bench-accent/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-accent"}
      title={community ? "Community submission; not independently verified" : "Benchmark run by local-bench"}
    >
      {source}
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

export function agenticProvenanceLabel(value: string): string {
  const labels: Readonly<Record<string, string>> = {
    none: "",
    project_attested: "attested",
    self_reported: "self-reported",
  };
  return labels[value] ?? value;
}
