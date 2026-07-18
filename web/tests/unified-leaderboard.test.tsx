import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomeLeaderboard, filterUnifiedLeaderboardRows } from "../components/home-leaderboard";
import { communityBoardRows, parseCommunityGroup } from "../lib/community-data";
import { IndexModelSchema, type IndexModel } from "../lib/schemas";

const rankedRows = [1, 2, 3, 4, 5].map(rankedModel);
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
      partial_composite: 0.4171,
      partial_composite_scope: "measured_headline_axes",
    },
    submission_id: "ticket_visible",
  }],
});

if (communityGroup === null) throw new Error("unified leaderboard fixture must validate");
const communityRows = communityBoardRows([communityGroup]);

describe("unified leaderboard community rows", () => {
  it("renders the community badge and detail link without assigning a rank number", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={communityRows} indexVersion="index-v4.1" />,
    );
    const rowStart = html.indexOf('data-testid="community-row-ticket_visible"');
    const rowEnd = html.indexOf("</tr>", rowStart);
    const rowHtml = html.slice(rowStart, rowEnd);

    expect(rowStart).toBeGreaterThan(-1);
    expect(rowHtml).toContain("Qwythos-9B v2");
    expect(rowHtml).toContain("community");
    expect(rowHtml).toContain("not independently verified");
    expect(rowHtml).toContain('href="/community/model/11111111111111111111111111111111"');
    expect(rowHtml).toContain(">—</td>");
    expect(rowHtml).not.toContain(">6</td>");
  });

  it("keeps ranked ordering unchanged when community rows are present", () => {
    const withoutCommunity = filterUnifiedLeaderboardRows(rankedRows, [], "all");
    const withCommunity = filterUnifiedLeaderboardRows(rankedRows, communityRows, "all");

    expect(withCommunity.ranked.map((row) => row.slug)).toEqual(
      withoutCommunity.ranked.map((row) => row.slug),
    );
    expect(withCommunity.community.map((row) => row.partialComposite)).toEqual([0.4171]);
  });

  it("filters All, local-bench runs, and community without mixing row populations", () => {
    const all = filterUnifiedLeaderboardRows(rankedRows, communityRows, "all");
    const local = filterUnifiedLeaderboardRows(rankedRows, communityRows, "local-bench");
    const community = filterUnifiedLeaderboardRows(rankedRows, communityRows, "community");

    expect(all).toMatchObject({ ranked: { length: 5 }, community: { length: 1 } });
    expect(local).toMatchObject({ ranked: { length: 5 }, community: { length: 0 } });
    expect(community).toMatchObject({ ranked: { length: 0 }, community: { length: 1 } });
  });

  it("keeps the ranked count at five and omits suppressed fixture rows", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={rankedRows} communityRows={communityRows} indexVersion="index-v4.1" />,
    );

    expect(html).toContain("5 ranked");
    expect(html).toContain("1 community");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain(">All</button>");
    expect(html).toContain("local-bench runs");
    expect(html).not.toContain("Suppressed fixture model");
    expect(html.indexOf("Ranked Model 5")).toBeLessThan(html.indexOf("Qwythos-9B v2"));
  });
});

function rankedModel(position: number): IndexModel {
  const slug = `ranked-${position}`;
  return IndexModelSchema.parse({
    axes: {},
    best_run_id: `${slug}-run`,
    composite: { hi: 101 - position, lo: 99 - position, point: 100 - position },
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
