import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../components/app-shell";
import { CommunityFamilyResults } from "../components/community-family-results";
import type { CommunityBoardRow } from "../lib/community-data";
import { compareFamilyNames } from "../lib/family-slug";

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
      <AppShell families={["Qwen3.6", "DeepSeek V3"]} indexVersion="index-v3.0" suiteVersion="suite-v1" usesDemoData={false}>
        <div>content</div>
      </AppShell>,
    );
    expect(html).not.toContain('href="/community"');
    expect(html).not.toContain(">Community<");
    expect(html).toContain('href="/submissions"');
  });

  it("renders the first destination as a family dropdown with directory and deep links", () => {
    // Given: the application shell is rendered with its standard navigation.
    // When: the header markup is generated.
    const html = renderToStaticMarkup(
      <AppShell families={["DeepSeek V3", "Qwen3.6"]} indexVersion="index-v3.0" suiteVersion="suite-v1" usesDemoData={false}>
        <div>content</div>
      </AppShell>,
    );
    const familiesSummary = html.search(/<summary[^>]*>Model families<\/summary>/u);
    const leaderboardLink = html.indexOf('href="/leaderboard"');

    // Then: families remains the emphasized first destination and exposes every directory target.
    expect(familiesSummary).toBeGreaterThan(-1);
    expect(familiesSummary).toBeLessThan(leaderboardLink);
    expect(html).toContain('href="/families">All families →</a>');
    expect(html).toContain('href="/families/deepseek-v3"');
    expect(html).toContain('href="/families/qwen3-6"');
    expect(html).toContain("sticky top-0");
    expect(html).not.toContain('href="/#families"');
    expect(html).not.toContain('href="/families#');
  });

  it("breaks family-name ties in user-visible alphabetical order", () => {
    expect(["GLM 5", "GPT OSS", "Gemma 3"].sort(compareFamilyNames)).toEqual(["Gemma 3", "GLM 5", "GPT OSS"]);
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
