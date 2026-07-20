import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { CommunityBoardRow } from "../lib/community-data";
import { IndexModelSchema } from "../lib/schemas";

const rankedModel = IndexModelSchema.parse({
  axes: {
    coding: { hi: 61, lo: 59, n: 10, n_errors: 0, n_no_answer: 0, point: 60, raw_accuracy: 0.6 },
    instruction: { hi: 61, lo: 59, n: 10, n_errors: 0, n_no_answer: 0, point: 60, raw_accuracy: 0.6 },
    knowledge: { hi: 61, lo: 59, n: 10, n_errors: 0, n_no_answer: 0, point: 60, raw_accuracy: 0.6 },
    math: { hi: 61, lo: 59, n: 10, n_errors: 0, n_no_answer: 0, point: 60, raw_accuracy: 0.6 },
    tool_use: { hi: 61, lo: 59, n: 10, n_errors: 0, n_no_answer: 0, point: 60, raw_accuracy: 0.6 },
  },
  best_run_id: "homepage-ranked-run",
  catalog_id: "Qwen/Qwen3.6-27B",
  composite: { hi: 0.61, lo: 0.59, point: 0.6 },
  demo: false,
  est_cost_usd: null,
  family: "Fixture",
  gpu: null,
  kind: "maintainer_project",
  index_version: "index-v4.1",
  lane: "bounded-final-v2",
  model_label: "Homepage Ranked Model",
  n_runs: 1,
  origin: "project_anchor",
  ranked: true,
  replicated: false,
  score_status: "measured",
  slug: "homepage-ranked",
  tier: "standard",
  tokens_to_answer_median: 128,
  trust_label: "project_anchor",
});

const bonsaiCatalogModel = IndexModelSchema.parse({
  ...rankedModel,
  axes: {},
  best_run_id: null,
  catalog_id: "prism-ml/Ternary-Bonsai-27B-unpacked",
  composite: null,
  family: "Qwen3.6",
  kind: "community",
  model_label: "Bonsai 27B Ternary",
  n_runs: 0,
  ranked: false,
  score_status: "missing",
  slug: "bonsai-27b-ternary",
  tier: null,
  tokens_to_answer_median: null,
});

const communityRow: CommunityBoardRow = {
  artifactSha256: "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757",
  axes: {},
  compositeFull: 0.67,
  declaredBaseModels: ["Qwen/Qwen3.6-27B"],
  detailPath: null,
  displayName: "Bonsai 27B Ternary",
  family: "qwen35",
  globalRank: null,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
  lineage: undefined,
  measuredHeadlineWeight: 0.75,
  missingHeadlineWeight: 0.25,
  partialComposite: 0.67,
  quantLabel: "Q4_K_M",
  ranked: false,
  submissionId: "homepage-community-ticket",
};

vi.mock("@/lib/data", () => ({
  getAgenticBySlug: async () => new Map(),
  getIndexData: async () => ({ index_version: "index-v4.1", models: [rankedModel, bonsaiCatalogModel] }),
  getIndexModelsWithArtifacts: async () => [
    { ...rankedModel, artifactSha256s: [] },
    { ...bonsaiCatalogModel, artifactSha256s: [communityRow.artifactSha256] },
  ],
  getHomePageData: async () => ({
    anchorRuns: [],
    catalogModels: [],
    communityCatalogModels: [
      { ...rankedModel, artifactSha256s: [] },
      { ...bonsaiCatalogModel, artifactSha256s: [communityRow.artifactSha256] },
    ],
    index: { index_version: "index-v4.1", models: [rankedModel, bonsaiCatalogModel] },
    rigAnchors: [],
    rigCandidates: [],
  }),
  getOnrampCatalog: async () => ({ models: [], popularityAsOf: null }),
}));

vi.mock("@/lib/community-data", () => ({
  getCommunityBoardRows: async () => [communityRow],
}));

import HomePage from "../app/page";
import LeaderboardPage from "../app/leaderboard/page";

describe("homepage unified board", () => {
  it("labels the landing family reduction without adding the caption to the full board", async () => {
    const landing = renderToStaticMarkup(await HomePage());
    const leaderboard = renderToStaticMarkup(await LeaderboardPage());

    expect(landing).toContain("Showing the best variant per base family");
    expect(landing).toContain('href="/leaderboard/"');
    // The unified "complete headline profile" phrase is version-derived board copy
    // (v4 scope) plus static methodology/submit/family copy — pinned in
    // methodology-page.test.tsx; this v3-shaped fixture never renders it.
    expect(leaderboard).not.toContain("Showing the best variant per base family");
  });
  it("renders a complete community row in the unified board", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-testid="full-leaderboard"');
    expect(html).toContain('data-testid="community-row-homepage-community-ticket"');
    expect(html).toContain("Bonsai 27B Ternary");
  });

  it("uses detail artifact identity before declared base lineage for the community route", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-href="/model/bonsai-27b-ternary/"');
    expect(html).not.toContain('data-href="/model/homepage-ranked"');
  });

  it("keeps the landing page free of the families launchpad and directory", async () => {
    // Given: the landing page has one indexed model family.
    // When: the page is prerendered.
    const html = renderToStaticMarkup(await HomePage());

    // Then: family browsing consumes no landing-page real estate.
    expect(html).not.toMatch(/<nav[^>]*id="families"/u);
    expect(html).not.toContain("Browse 1 family →");
    expect(html).not.toContain("Browse by model family");
    expect(html).not.toContain("Primary browse path");
  });
});
