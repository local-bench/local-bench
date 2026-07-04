import { kindLabel } from "@/lib/format";
import type { Kind } from "@/lib/schemas";

export function KindBadge({
  kind,
  runCount,
}: {
  readonly kind: Kind;
  readonly runCount?: number;
}) {
  const isAnchor = kind === "anchor";
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-semibold uppercase",
        isAnchor
          ? "border-bench-anchor/45 bg-bench-anchor/10 text-bench-anchor"
          : "border-bench-community/35 bg-bench-community/10 text-bench-community",
      ].join(" ")}
    >
      {kindLabel(kind)}
      {!isAnchor && runCount !== undefined ? <span className="text-bench-muted">N={runCount}</span> : null}
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
