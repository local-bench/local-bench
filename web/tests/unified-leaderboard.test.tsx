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
      composite_full: 0.56,
      headline_score: 0.56,
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
  detailPath: "/model/ranked-2",
  family: "Fixture",
  globalRank: 2,
  indexVersion: "index-v4.1",
  submitterDisplayName: "Ada",
  axes: {
    coding: { ci: [0.4, 0.5], n: 10, score: 0.45, status: "measured" },
    instruction: { ci: [0.5, 0.6], n: 10, score: 0.55, status: "measured" },
    knowledge: { ci: [0.6, 0.7], n: 10, score: 0.65, status: "measured" },
    math: { ci: [0.7, 0.8], n: 10, score: 0.75, status: "measured" },
    tool_use: { ci: [0.4, 0.5], n: 10, score: 0.45, status: "measured" },
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
  it("renders a numeric rank and plain submission detail in the shared board", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={liveCommunityRows} indexVersion="index-v4.1" />,
    );
    const rowStart = html.indexOf('data-testid="community-row-ticket_visible"');
    const rowEnd = html.indexOf("</tr>", rowStart);
    const rowHtml = html.slice(rowStart, rowEnd);
    const rankCellHtml = rowHtml.slice(rowHtml.indexOf("<td"), rowHtml.indexOf("</td>") + 5);

    expect(rowStart).toBeGreaterThan(-1);
    expect(rowHtml).toContain("Qwythos-9B v2");
    expect(rowHtml).toContain("submitted as Ada — unverified");
    expect(rowHtml).toContain('href="/model/ranked-2"');
    expect(rowHtml).not.toContain("re-scored");
    expect(html).toContain("Swipe horizontally for scores and axes");
    expect(rankCellHtml).not.toContain("—");
    expect(rankCellHtml).toMatch(/>2<\/td>/u);
  });

  it("interleaves community scores between ranked rows and keeps null scores last", () => {
    const rows = filterUnifiedLeaderboardRows(rankedRows, liveCommunityRows);
    const sorted = sortUnifiedLeaderboardRows(rows, { key: "composite", direction: "desc" });

    expect(sorted.map((row) => row.source === "local-bench" ? row.model.slug : row.row.submissionId)).toEqual([
      "ranked-1",
      "ticket_visible",
      "ranked-2",
      "ranked-3",
      "ranked-4",
    ]);
  });

  it("sorts live community axes on the same percentage scale as ranked axes", () => {
    const rankedWithInstruction: IndexModel = {
      ...rankedModel(6, 50),
      axes: {
        ...rankedModel(6, 50).axes,
        instruction: {
          hi: 51,
          lo: 49,
          n: 10,
          n_errors: 0,
          n_no_answer: 0,
          point: 50,
          raw_accuracy: 0.5,
        },
      },
    };
    const rows = filterUnifiedLeaderboardRows([rankedWithInstruction], liveCommunityRows);
    const sorted = sortUnifiedLeaderboardRows(rows, { key: "instruction", direction: "desc" });

    expect(sorted.map((row) => row.source)).toEqual(["community", "local-bench"]);
  });

  it("normalizes both fraction and percentage community axis scores before sorting", () => {
    const fixture = liveCommunityRows[0];
    if (fixture === undefined) throw new Error("missing live community fixture");
    const fraction = {
      ...fixture,
      axes: { ...fixture.axes, instruction: { ci: null, n: 10, score: 0.9, status: "measured" as const } },
      submissionId: "ticket_fraction",
    };
    const percentage = {
      ...fixture,
      axes: { ...fixture.axes, instruction: { ci: null, n: 10, score: 42, status: "measured" as const } },
      submissionId: "ticket_percentage",
    };
    const rows = filterUnifiedLeaderboardRows([], [percentage, fraction]);
    const sorted = sortUnifiedLeaderboardRows(rows, { key: "instruction", direction: "desc" });

    expect(sorted.map((row) => row.source === "community" ? row.row.submissionId : row.model.slug)).toEqual([
      "ticket_fraction",
      "ticket_percentage",
    ]);
  });

  it("keeps complete project and community rows in one population", () => {
    const all = filterUnifiedLeaderboardRows(rankedRows, liveCommunityRows);

    expect(all.map((row) => row.source)).toEqual([
      "local-bench",
      "community",
      "local-bench",
      "local-bench",
      "local-bench",
    ]);
    expect(all.map((row) => row.rank)).toEqual([1, 2, 3, 4, 5]);
  });

  it("shows one complete-run count and omits source segregation", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={liveCommunityRows} indexVersion="index-v4.1" />,
    );

    expect(html).toContain("5 complete ranked runs");
    expect(html).not.toContain("local-bench runs");
    expect(html).not.toContain("Suppressed fixture model");
    expect(html.indexOf("Ranked Model 1")).toBeLessThan(html.indexOf("Qwythos-9B v2"));
    expect(html.indexOf("Qwythos-9B v2")).toBeLessThan(html.indexOf("Ranked Model 2"));
  });
});

function rankedModel(position: number, score: number | null): IndexModel {
  const slug = `ranked-${position}`;
  return IndexModelSchema.parse({
    axes: score === null ? {} : {
      coding: axisScore(score),
      instruction: axisScore(score),
      knowledge: axisScore(score),
      math: axisScore(score),
      tool_use: axisScore(score),
    },
    best_run_id: `${slug}-run`,
    composite: score === null ? null : { hi: score + 0.01, lo: score - 0.01, point: score },
    composite_full: score === null ? null : { hi: score + 0.01, lo: score - 0.01, point: score },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: null,
    kind: "maintainer_project",
    index_version: "index-v4.1",
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

function axisScore(point: number) {
  return { hi: point + 0.01, lo: point - 0.01, n: 10, n_errors: 0, n_no_answer: 0, point, raw_accuracy: point / 100 };
}
