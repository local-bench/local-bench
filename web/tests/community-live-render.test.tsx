import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityLeaderboardRow } from "../components/community-leaderboard-row";
import type { CommunityBoardRow } from "../lib/community-data";

const liveOnlyRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  axes: {},
  communityModelGroupId: `community-group:${"1".repeat(32)}`,
  declaredBaseModels: [],
  detailPath: null,
  displayName: "Live-only model",
  identityLabel: "community-declared, identity-unverified",
  lineage: undefined,
  measuredHeadlineWeight: 1,
  missingHeadlineWeight: 0,
  partialComposite: 0.5,
  quantLabel: "Q4_K_M",
  ranked: false,
  submissionId: `ticket_${"2".repeat(32)}`,
};

describe("live-only community links", () => {
  it("renders a live-only row as plain text with the next-deploy tooltip", () => {
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={[]}
        row={liveOnlyRow}
        showAgenticColumn={false}
        showStaticIndexColumn={false}
      /></tbody></table>,
    );

    expect(html).toContain("detail page publishes with the next site deploy");
    expect(html).toContain("Live-only model");
    expect(html).not.toContain('href="/community/model/');
  });
});
