import {
  ARCHIVED_OPERATING_POINT_LABEL,
  operatingPointViewHref,
  type OperatingPointView,
} from "@/lib/operating-point-view";

const VIEW_LINKS: readonly {
  readonly label: string;
  readonly view: OperatingPointView;
}[] = [
  { label: "8k + 32k", view: "mixed" },
  { label: "32k", view: "32k" },
  { label: ARCHIVED_OPERATING_POINT_LABEL, view: "archived-8k" },
];

export function OperatingPointViewToggle({ view }: { readonly view: OperatingPointView }) {
  return (
    <nav
      aria-label="Operating point view"
      className="flex flex-wrap items-center gap-2 border-b border-bench-line bg-white/[0.015] px-3 py-2"
    >
      <span className="font-mono text-[10px] font-semibold uppercase tracking-wide text-bench-muted">
        Operating point
      </span>
      <div className="flex flex-wrap gap-1.5">
        {VIEW_LINKS.map((item) => {
          const active = item.view === view;
          return (
            <a
              aria-current={active ? "page" : undefined}
              className={active
                ? "rounded border border-bench-accent/50 bg-bench-accent/[0.10] px-2 py-1 font-mono text-[11px] font-semibold text-bench-accent"
                : "rounded border border-bench-line bg-bench-panel-2 px-2 py-1 font-mono text-[11px] text-bench-muted transition-colors hover:border-bench-accent/40 hover:text-bench-text"}
              href={operatingPointViewHref(item.view)}
              key={item.view}
            >
              {item.label}
            </a>
          );
        })}
      </div>
    </nav>
  );
}
