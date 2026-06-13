import { HomeLeaderboard } from "@/components/home-leaderboard";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getIndexData } from "@/lib/data";

export default async function HomePage() {
  const index = await getIndexData();
  const axisNames = AXIS_CONFIG.filter((axis) => index.models.some((model) => model.axes[axis.key] !== undefined)).map(
    (axis) => axis.label,
  );

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <header className="flex flex-col gap-4 border-b border-bench-line pb-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase text-bench-accent">
              {index.suite_version} · {index.index_version}
            </p>
            <h1 className="mt-2 text-4xl font-semibold text-bench-text">Local AI quality leaderboard</h1>
            <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
              Every model is scored on the same frozen suite across {axisNames.join(", ")}. Composite is the
              equal-weighted mean of chance-corrected axis scores with a 95% bootstrap CI.
            </p>
          </div>
          {/* Single table preserves sortable browsing; this caveat prevents cross-lane order being read as rank. */}
          <div className="rounded-lg border border-amber-300/35 bg-amber-300/[0.08] p-4 text-sm leading-6 text-amber-100">
            <strong className="text-amber-50">Quick tier = personal estimate, UNRANKED.</strong> Standard tier is
            the only ranked board, and ranks are only within the same reasoning lane. Rows are sorted for browsing
            only; reasoning lanes are not directly comparable.
          </div>
        </div>
      </header>
      <HomeLeaderboard models={index.models} />
    </main>
  );
}
