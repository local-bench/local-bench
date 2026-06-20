import { HomeLeaderboard } from "@/components/home-leaderboard";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { RigMatchFinder } from "@/components/rig-match-finder";
import { BestVariantVramScatter } from "@/components/best-variant-scatter";
import { BestVariantTable } from "@/components/best-variant-table";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getHomePageData } from "@/lib/data";
import { selectBestVariantPoints } from "@/lib/best-variant";

export default async function HomePage() {
  const { anchorRuns, index, rigAnchors, rigCandidates } = await getHomePageData();
  const bestVariantPoints = selectBestVariantPoints(rigCandidates);
  const axisNames = AXIS_CONFIG.filter((axis) => index.models.some((model) => model.axes[axis.key] !== undefined)).map(
    (axis) => axis.label,
  );
  const suiteLabel = index.suite_version ?? "scoreless catalog";
  const axisCopy = axisNames.length > 0
    ? `Every measured model is scored on the same frozen suite across ${axisNames.join(", ")}.`
    : "Catalog models are listed as score-less shells until benchmark runs land.";

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <RigMatchFinder anchors={rigAnchors} candidates={rigCandidates} />
      <BestVariantVramScatter anchorRuns={anchorRuns} points={bestVariantPoints} />
      <BestVariantTable points={bestVariantPoints} />
      <section className="flex flex-col gap-4">
        <div className="grid gap-5 border-b border-bench-line pb-5 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase text-bench-accent">
              {suiteLabel} / {index.index_version}
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-bench-text">Full leaderboard</h2>
            <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
              {axisCopy} The {LOCAL_INTELLIGENCE_INDEX_NAME} ({LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) appears only
              after a measured run attaches to a catalog model and quant. {LOCAL_INTELLIGENCE_INDEX_PROFILE}.
            </p>
          </div>
          {/* Single table preserves sortable browsing; this caveat prevents cross-lane order being read as rank. */}
          <div className="rounded-lg border border-bench-warn/35 bg-bench-warn/[0.08] p-4 text-sm leading-6 text-bench-warn-soft">
            <strong className="text-bench-warn">Quick tier = personal estimate, UNRANKED.</strong> Standard tier is
            the only ranked board, and ranks are only within the same reasoning lane. Rows are sorted for browsing
            only; reasoning lanes are not directly comparable.
          </div>
        </div>
        <HomeLeaderboard models={index.models} />
      </section>
    </main>
  );
}
