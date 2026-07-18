export function CatalogOnlyNotice({ queued }: { readonly queued: boolean }) {
  return (
    <section className="rounded-lg border border-bench-warn/35 bg-bench-warn/[0.07] p-4 text-sm text-bench-muted">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold text-bench-text">Base not yet benchmarked</h2>
        {queued ? (
          <span className="rounded border border-bench-warn/45 bg-bench-warn/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-bench-warn">
            Queued
          </span>
        ) : null}
      </div>
      <p className="mt-2 leading-6">
        This catalog shell anchors the family while community variants publish. It will gain measured profiles when
        a project or qualifying community run lands.
      </p>
    </section>
  );
}
