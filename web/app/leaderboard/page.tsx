import { HomeLeaderboard } from "@/components/home-leaderboard";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getIndexData } from "@/lib/data";

export default async function LeaderboardPage() {
  const index = await getIndexData();
  const axisNames = AXIS_CONFIG.filter((axis) => index.models.some((model) => model.axes[axis.key] !== undefined)).map(
    (axis) => axis.label,
  );
  const hasMeasuredRankedData = index.models.some(
    (model) => model.score_status === "measured" && model.ranked && !model.demo && model.composite !== null,
  );
  const suiteLabel = index.suite_version ?? "scoreless catalog";
  const axisCopy = hasMeasuredRankedData
    ? `Every ranked model is scored on the same frozen suite${axisNames.length > 0 ? ` across ${axisNames.join(", ")}` : ""}. This is the initial measured ladder — more models land as runs are submitted.`
    : "Catalog models are listed as score-less shells until benchmark runs land.";

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
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
          {/* Single table preserves sortable browsing; this caveat prevents sorted order being read as rank. */}
          <div className="rounded-lg border border-bench-warn/35 bg-bench-warn/[0.08] p-4 text-sm leading-6 text-bench-warn-soft">
            <strong className="text-bench-warn">Quick tier = personal estimate, UNRANKED.</strong> Standard tier is
            the only ranked board. Rows are sorted for browsing only, so a higher row is not a higher rank unless its
            Rank cell is filled.
          </div>
        </div>
        <HomeLeaderboard models={index.models} />
      </section>
    </main>
  );
}
