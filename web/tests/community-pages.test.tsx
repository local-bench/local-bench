import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../components/app-shell";
import { CommunityFamilyResults } from "../components/community-family-results";
import type { CommunityBoardRow } from "../lib/community-data";

const familyRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  axes: { knowledge: { ci: [0.4, 0.6], n: 20, score: 0.5, status: "measured" } },
  compositeFull: 0.5,
  declaredBaseModels: ["Qwen/Qwen3.5-9B"],
  detailPath: "/model/qwen3-5-9b",
  displayName: "Qwythos-9B v2",
  family: "Qwen3.5",
  globalRank: 2,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
  lineage: undefined,
  measuredHeadlineWeight: 1,
  missingHeadlineWeight: 0,
  partialComposite: 0.5,
  quantLabel: "Q4_K_M",
  submissionId: "ticket_visible",
  submitterDisplayName: "Ada",
};

describe("community results use the model-family namespace", () => {
  it("keeps Submissions in navigation without a Community destination", () => {
    const html = renderToStaticMarkup(
      <AppShell indexVersion="index-v3.0" suiteVersion="suite-v1" usesDemoData={false}>
        <div>content</div>
      </AppShell>,
    );
    expect(html).not.toContain('href="/community"');
    expect(html).not.toContain(">Community<");
    expect(html).toContain('href="/submissions"');
  });

  it("renders the reported run, axes, and submitter on the family surface", () => {
    const html = renderToStaticMarkup(<CommunityFamilyResults rows={[familyRow]} />);
    expect(html).toContain("Reported runs");
    expect(html).toContain("Qwythos-9B v2");
    expect(html).toContain("Per-axis breakdown");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).not.toContain("/community/model/");
  });
});
