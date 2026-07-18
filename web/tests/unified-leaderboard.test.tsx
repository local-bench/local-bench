import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  HomeLeaderboard,
  filterUnifiedLeaderboardRows,
  sortUnifiedLeaderboardRows,
} from "../components/home-leaderboard";
import { communityBoardRows, parseCommunityGroup, type CommunityBoardRow } from "../lib/community-data";
import { IndexModelSchema, type IndexModel } from "../lib/schemas";

const rankedRows = [60, 51, 40, 30, null].map((score, index) => rankedModel(index + 1, score));
const communityGroup = parseCommunityGroup({
  community_model_group_id: `community-group:${"1".repeat(32)}`,
  identity_label: "community-declared, identity-unverified",
  ranked: false,
  schema_version: "localbench.community_publication.v2",
  variants: [{
    artifact_sha256: "a".repeat(64),
    display_name: "Qwythos-9B v2",
    projection_object_sha256: "b".repeat(64),
    quant_label: "Q4_K_M",
    ranked: false,
    scores: {
      known_headline_contribution: 0.3128,
      measured_headline_weight: 0.75,
      missing_headline_weight: 0.25,
      partial_composite: 0.5696,
      partial_composite_scope: "measured_headline_axes",
    },
    submission_id: "ticket_visible",
  }],
});

if (communityGroup === null) throw new Error("unified leaderboard fixture must validate");
const communityRows = communityBoardRows([communityGroup]);
const liveCommunityRows: readonly CommunityBoardRow[] = communityRows.map((row) => ({
  ...row,
  axes: {
    agentic: { ci: [0.4, 0.5], n: 10, score: 0.45, status: "measured" },
    coding: { ci: null, n: 0, score: null, status: "not_measured" },
    instruction: { ci: [0.5, 0.6], n: 10, score: 0.55, status: "measured" },
    knowledge: { ci: [0.6, 0.7], n: 10, score: 0.65, status: "measured" },
    math: { ci: [0.7, 0.8], n: 10, score: 0.75, status: "measured" },
    tool_use: { ci: null, n: 0, score: null, status: "not_measured" },
  },
  trust: {
    agentic_provenance: "self_reported",
    coding_state: "pending",
    replicated: false,
    tier: "re-scored",
    trust_label: "community_re_scored",
    verification_level: "bundle_rescored",
  },
}));

describe("unified leaderboard community rows", () => {
  it("renders the trust tier in the rank cell and marks partial axis coverage", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={liveCommunityRows} indexVersion="index-v4.1" />,
    );
    const rowStart = html.indexOf('data-testid="community-row-ticket_visible"');
    const rowEnd = html.indexOf("</tr>", rowStart);
    const rowHtml = html.slice(rowStart, rowEnd);
    const rankCellHtml = rowHtml.slice(rowHtml.indexOf("<td"), rowHtml.indexOf("</td>") + 5);

    expect(rowStart).toBeGreaterThan(-1);
    expect(rowHtml).toContain("Qwythos-9B v2");
    expect(rowHtml).toContain("community");
    expect(rowHtml).toContain("not independently verified");
    expect(rowHtml).toContain('href="/community/model/11111111111111111111111111111111"');
    expect(rowHtml).toContain("re-scored");
    expect(rowHtml).toContain("4/6 axes");
    expect(rankCellHtml).not.toContain("—");
    expect(rankCellHtml).not.toMatch(/>\d+</u);
    expect(rowHtml.indexOf(">community</span>")).toBeLessThan(
      rowHtml.indexOf("partial over measured headline axes"),
    );
  });

  it("interleaves community scores between ranked rows and keeps null scores last", () => {
    const rows = filterUnifiedLeaderboardRows(rankedRows, liveCommunityRows, "all");
    const sorted = sortUnifiedLeaderboardRows(rows, { key: "composite", direction: "desc" });

    expect(sorted.map((row) => row.source === "local-bench" ? row.model.slug : row.row.submissionId)).toEqual([
      "ranked-1",
      "ticket_visible",
      "ranked-2",
      "ranked-3",
      "ranked-4",
      "ranked-5",
    ]);
  });

  it("filters All, local-bench runs, and community without mixing row populations", () => {
    const all = filterUnifiedLeaderboardRows(rankedRows, communityRows, "all");
    const local = filterUnifiedLeaderboardRows(rankedRows, communityRows, "local-bench");
    const community = filterUnifiedLeaderboardRows(rankedRows, communityRows, "community");

    expect(all.map((row) => row.source)).toEqual([
      "local-bench",
      "local-bench",
      "local-bench",
      "local-bench",
      "local-bench",
      "community",
    ]);
    expect(local).toHaveLength(5);
    expect(local.every((row) => row.source === "local-bench")).toBe(true);
    expect(community).toHaveLength(1);
    expect(community.every((row) => row.source === "community")).toBe(true);
  });

  it("keeps the ranked count at five and omits suppressed fixture rows", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={liveCommunityRows} indexVersion="index-v4.1" />,
    );

    expect(html).toContain("5 ranked");
    expect(html).toContain("1 community");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain(">All</button>");
    expect(html).toContain("local-bench runs");
    expect(html).not.toContain("Suppressed fixture model");
    expect(html.indexOf("Ranked Model 1")).toBeLessThan(html.indexOf("Qwythos-9B v2"));
    expect(html.indexOf("Qwythos-9B v2")).toBeLessThan(html.indexOf("Ranked Model 2"));
  });
});

function rankedModel(position: number, score: number | null): IndexModel {
  const slug = `ranked-${position}`;
  return IndexModelSchema.parse({
    axes: {},
    best_run_id: `${slug}-run`,
    composite: score === null ? null : { hi: score + 0.01, lo: score - 0.01, point: score },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "maintainer_project",
    lane: "bounded-final-v2",
    model_label: `Ranked Model ${position}`,
    n_runs: 1,
    origin: "project_anchor",
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug,
    tier: "standard",
    tokens_to_answer_median: 128,
    trust_label: "project_anchor",
  });
}
