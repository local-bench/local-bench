import Link from "next/link";
import { CatalogShells } from "@/components/catalog-shells";
import { HomeLeaderboard } from "@/components/home-leaderboard";
import {
  LOCAL_INTELLIGENCE_INDEX_NAME,
  LOCAL_INTELLIGENCE_INDEX_PROFILE,
  LOCAL_INTELLIGENCE_INDEX_QUALIFIER,
  SEASON_2_INDEX_PROFILE,
  SEASON_2_INDEX_QUALIFIER,
} from "@/components/local-intelligence-index";
import { AXIS_CONFIG } from "@/lib/axis-config";
import { getCommunityBoardRows } from "@/lib/community-data";
import { communityRowsWithFamilyPaths } from "@/lib/community-family";
import { axisLabel } from "@/lib/format";
import { getAgenticBySlug, getFineTuneBaseBySlug, getIndexData } from "@/lib/data";
import { isFullIndexRow } from "@/lib/leaderboard-score";
import { INDEX_VERSION_V4, SEASON_2_HEADLINE_AXES } from "@/lib/scoring-seasons";
import { publicProtocolLabel } from "@/lib/board-adapter";

export default async function LeaderboardPage() {
  const [index, agenticBySlug] = await Promise.all([
    getIndexData(),
    getAgenticBySlug(),
  ]);
  const communityRows = await getCommunityBoardRows();
  const ranked = index.models.filter(isFullIndexRow);
  const catalog = index.models.filter((model) => !isFullIndexRow(model));
  const rankedForDisplay = index.index_version === INDEX_VERSION_V4
    ? ranked.map((model) => model.index_version === undefined ? { ...model, index_version: INDEX_VERSION_V4 } : model)
    : ranked;
  const fineTuneBaseBySlug = await getFineTuneBaseBySlug(index.models);
  const communityRowsForDisplay = communityRows === null ? [] : communityRowsWithFamilyPaths(communityRows, index.models);
  const season2 = index.index_version === INDEX_VERSION_V4;
  // On a season-2 board the copy must list the season-2 headline axes; the v3 axis palette
  // (AXIS_CONFIG) still names Agentic / Tool calling, which legacy diagnostic rows carry.
  const axisKeysForCopy: readonly string[] = season2 ? SEASON_2_HEADLINE_AXES : AXIS_CONFIG.map((axis) => axis.key);
  const axisNames = axisKeysForCopy
    .filter((key) => index.models.some((model) => model.axes[key] !== undefined))
    .map((key) => axisLabel(key));
  const hasMeasuredRankedData = ranked.length > 0 || communityRowsForDisplay.some((row) => row.headlineComplete);
  const suiteLabel = index.suite_version ?? "scoreless catalog";
  const axisCopy = hasMeasuredRankedData
    ? `Every ranked model is scored on the same frozen suite${axisNames.length > 0 ? ` across ${axisNames.join(", ")}` : ""}. This is the initial measured ladder — more models land as runs are submitted.`
    : "Catalog models are listed as score-less shells until complete benchmark runs land.";

  return (
    <main className="mx-auto flex w-full max-w-[1480px] flex-col gap-6 px-5 py-7 lg:px-8">
      <section className="flex flex-col gap-4">
        <div className="grid gap-5 border-b border-bench-line pb-5 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase text-bench-accent">
              {suiteLabel} / {publicProtocolLabel(index.index_version)}
            </p>
            <h1 className="mt-2 text-2xl font-semibold text-bench-text">Global comparison</h1>
            <p className="mt-3 max-w-3xl text-base leading-7 text-bench-muted">
              {axisCopy} The {LOCAL_INTELLIGENCE_INDEX_NAME} ({season2 ? SEASON_2_INDEX_QUALIFIER : LOCAL_INTELLIGENCE_INDEX_QUALIFIER}) appears only
              after a complete run publishes. {season2 ? SEASON_2_INDEX_PROFILE : LOCAL_INTELLIGENCE_INDEX_PROFILE}.
            </p>
          </div>
          {/* Score-less shells are split out below so they can never sort into or dwarf the measured rank. */}
          <div className="rounded-lg border border-bench-line bg-bench-panel/60 p-4 text-sm leading-6 text-bench-muted">
            Every complete project and community run shares this ranking and the same composite. The global view is a
            cross-family reference; <Link href="/families" className="text-bench-accent hover:underline">browse model families</Link> to choose among related variants. Note: {season2
              ? "the Agentic axis is near-floor for every current local entrant, so it compresses headline gaps — read the composite alongside the per-axis columns and the facet breakdown."
              : "the Agentic axis is near-floor for every current local entrant, so it compresses headline gaps — read the composite alongside the per-axis columns and the Static Index."}
          </div>
        </div>
        <HomeLeaderboard
          models={rankedForDisplay}
          agenticBySlug={agenticBySlug}
          communityRows={communityRowsForDisplay}
          fineTuneBaseBySlug={fineTuneBaseBySlug}
          indexVersion={index.index_version}
        />
        <CatalogShells models={catalog} />
      </section>
    </main>
  );
}
