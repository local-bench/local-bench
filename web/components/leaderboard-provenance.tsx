import Link from "next/link";
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

function staticTrustChip(model: ProvenanceModel) {
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

// Who ran the benchmark: community submissions carry the submitter's credit line; every other
// measured row was run by the project itself and is credited to local-bench. Catalog shells and
// demo fixtures were run by nobody, so they show a placeholder.
export function RunByCell({ model }: { readonly model: IndexModel }) {
  const submitter = model.submitter_display_name ?? model.submitted_by;
  if (submitter !== null && submitter !== undefined && submitter !== "") {
    return <span className="text-xs text-bench-muted">submitted by {submitter}</span>;
  }
  if (model.score_status === "measured" && !model.demo) {
    return <span className="font-mono text-xs text-bench-text">local-bench</span>;
  }
  return <span className="font-mono text-xs text-bench-muted">—</span>;
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
