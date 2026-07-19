import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityFamilyResults } from "../components/community-family-results";
import { CommunityLeaderboardRow } from "../components/community-leaderboard-row";
import { CommunityFreshness } from "../components/community-live-state";
import type { CommunityBoardRow } from "../lib/community-data";

const liveOnlyRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  axes: {},
  communityModelGroupId: `community-group:${"1".repeat(32)}`,
  compositeFull: 0.5,
  declaredBaseModels: [],
  detailPath: null,
  displayName: "Live-only model",
  family: "Fixture",
  globalRank: 1,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
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
        rank={1}
        row={liveOnlyRow}
        showAgenticColumn={false}
        showStaticIndexColumn={false}
      /></tbody></table>,
    );

    expect(html).toContain("family detail unavailable for this row");
    expect(html).toContain("Live-only model");
    expect(html).not.toContain('href="/community/model/');
  });

  it("renders live axes, attribution, trust, and a non-numeric pending coding state", () => {
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={["coding"]}
        rank={1}
        row={{
          ...liveOnlyRow,
          axes: { coding: { ci: null, n: 0, score: null, status: "not_measured" } },
          submitterDisplayName: "Ada",
          submitterGithubLogin: "octocat",
          submitterKeyFingerprint: "abcdef123456",
          trust: {
            agentic_provenance: "self_reported",
            coding_state: "pending",
            replicated: false,
            tier: "re-scored",
            trust_label: "community_re_scored",
            verification_level: "bundle_rescored",
          },
        }}
        showAgenticColumn
        showStaticIndexColumn={false}
      /></tbody></table>,
    );

    expect(html).toContain("not measured");
    expect(html).not.toContain(">0.0</td>");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).not.toContain("re-scored");
    expect(html).not.toContain("self-reported");
    expect(html).not.toContain('href="https://github.com/');
  });

  it("renders live freshness, held-back rows, and honest snapshot fallback copy", () => {
    const live = renderToStaticMarkup(<CommunityFreshness state={{
      droppedRows: 2,
      generatedAt: "2026-07-18T04:00:00Z",
      kind: "live",
      rows: [liveOnlyRow],
    }} now={new Date("2026-07-18T04:00:07Z").getTime()} />);
    const snapshot = renderToStaticMarkup(<CommunityFreshness
      communityUnavailable
      state={{ kind: "snapshot", rows: [liveOnlyRow] }}
    />);

    expect(live).toContain("live · updated 7s ago · 2 rows held back");
    expect(snapshot).toContain("showing last published snapshot");
    expect(snapshot).toContain("live data unavailable");
  });

  it("renders live axes and submission details on the family record", () => {
    const html = renderToStaticMarkup(<CommunityFamilyResults rows={[{
        ...liveOnlyRow,
        axes: {
          coding: { ci: null, n: 0, score: null, status: "not_measured" },
          knowledge: { ci: [0.4, 0.6], n: 20, score: 0.5, status: "measured" },
        },
        submitterDisplayName: "Ada",
        submitterGithubLogin: "octocat",
        submitterKeyFingerprint: "abcdef123456",
        trust: {
          agentic_provenance: "self_reported",
          coding_state: "pending",
          replicated: false,
          tier: "re-scored",
          trust_label: "community_re_scored",
          verification_level: "bundle_rescored",
        },
      }]} />);

    expect(html).toContain("Knowledge");
    expect(html).toContain("50.0 · n=20");
    expect(html).toContain("not measured");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).toContain("Per-axis breakdown");
    expect(html).not.toContain("re-scored");
  });
});
