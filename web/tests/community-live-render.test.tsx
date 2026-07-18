import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityLeaderboardRow } from "../components/community-leaderboard-row";
import { CommunityDetailRows } from "../components/community-detail";
import { CommunityFreshness } from "../components/community-live-state";
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

  it("renders live axes, attribution, trust, and a non-numeric pending coding state", () => {
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={["coding"]}
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

    expect(html).toContain("pending verification");
    expect(html).not.toContain(">0.0</td>");
    expect(html).toContain("re-scored");
    expect(html).toContain("self-reported");
    expect(html).toContain("submitted by @octocat");
    expect(html).toContain("Ada");
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

  it("renders live axis and trust evidence on a community detail record", () => {
    const html = renderToStaticMarkup(<CommunityDetailRows
      groupId={`community-group:${"1".repeat(32)}`}
      rows={[{
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
      }]}
    />);

    expect(html).toContain("knowledge 50.0 · n=20");
    expect(html).toContain("coding pending verification");
    expect(html).toContain("@octocat");
    expect(html).toContain("Ada");
    expect(html).not.toContain('href="https://github.com/');
    expect(html).toContain("re-scored");
  });
});
