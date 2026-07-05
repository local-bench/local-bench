// Who-ran-this credit chip for model pages. Community submissions carry the submitter's name;
// everything else on the board was measured by the project and is credited to local-bench.
export function RunByBadge({ submitter }: { readonly submitter: string | null | undefined }) {
  const hasSubmitter = submitter !== null && submitter !== undefined && submitter !== "";
  return (
    <span className="inline-flex items-center gap-1 rounded border border-bench-accent/45 bg-bench-accent/10 px-2 py-1 text-[11px] font-semibold uppercase text-bench-accent">
      {hasSubmitter ? `submitted by ${submitter}` : "run by local-bench"}
    </span>
  );
}

export function TierBadge({ tier }: { readonly tier: string }) {
  const isQuick = tier.toLowerCase() === "quick";
  return (
    <span
      className={[
        "inline-flex rounded border px-2 py-1 text-[11px] font-semibold uppercase",
        isQuick
          ? "border-bench-muted/40 bg-bench-muted/10 text-bench-muted"
          : "border-bench-accent/45 bg-bench-accent/10 text-bench-accent",
      ].join(" ")}
    >
      {isQuick ? "Quick · unranked" : tier}
    </span>
  );
}

export function LaneBadge({ lane }: { readonly lane: string | null }) {
  return (
    <span className="inline-flex rounded border border-bench-line bg-white/[0.03] px-2 py-1 text-[11px] font-medium uppercase text-bench-muted">
      {lane ?? "n/a"}
    </span>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex rounded border border-bench-warn/55 bg-bench-warn/12 px-2 py-1 text-[11px] font-semibold uppercase text-bench-warn">
      DEMO
    </span>
  );
}
