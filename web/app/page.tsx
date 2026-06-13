import { HomeLeaderboard } from "@/components/home-leaderboard";
import { QualityVramScatter } from "@/components/quality-vram-scatter";
import { RigMatchFinder } from "@/components/rig-match-finder";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getHomePageData } from "@/lib/data";

export default async function HomePage() {
  const { anchorRuns, index, rigAnchors, rigCandidates, scatterRuns } = await getHomePageData();
  const axisNames = AXIS_CONFIG.filter((axis) => index.models.some((model) => model.axes[axis.key] !== undefined)).map(
    (axis) => axis.label,
  );

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <RigMatchFinder anchors={rigAnchors} candidates={rigCandidates} />
      <QualityVramScatter
        anchorRuns={anchorRuns}
        ariaLabel="All local model quant runs plotted by composite quality and VRAM footprint with anchor ceiling lines"
        description="Every local run with a VRAM footprint, including the synthetic preview quant ladders."
        omittedLabel="local run(s) omitted from scatter x: no footprint"
        runs={scatterRuns}
        showPointLabels={false}
        title="Quality vs VRAM footprint"
      />
      <section className="flex flex-col gap-4">
        <div className="grid gap-5 border-b border-bench-line pb-5 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase text-bench-accent">
              {index.suite_version} · {index.index_version}
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-bench-text">Full leaderboard</h2>
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
        <HomeLeaderboard models={index.models} />
      </section>
    </main>
  );
}
