import type { ReactNode } from "react";

export function DetailGrid({ children }: { readonly children: ReactNode }) {
  return <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>;
}

export function DetailItem({
  label,
  value,
}: {
  readonly label: string;
  readonly value: ReactNode;
}) {
  return (
    <div className="rounded-md border border-bench-line bg-white/[0.025] p-3">
      <dt className="text-[11px] font-semibold uppercase text-bench-muted">{label}</dt>
      <dd className="mt-1 break-words font-mono text-sm text-bench-text">{value}</dd>
    </div>
  );
}
