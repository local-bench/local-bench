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
