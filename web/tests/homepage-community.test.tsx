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

const communityRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  axes: {},
  compositeFull: 0.57,
  detailPath: null,
  displayName: "Homepage Community Model",
  family: "Fixture",
  globalRank: null,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
  lineage: undefined,
  measuredHeadlineWeight: 0.75,
  missingHeadlineWeight: 0.25,
  partialComposite: 0.57,
  quantLabel: "Q4_K_M",
  ranked: false,
  submissionId: "homepage-community-ticket",
};

vi.mock("@/lib/data", () => ({
  getAgenticBySlug: async () => new Map(),
  getFineTuneBaseBySlug: async () => new Map(),
  getHomePageData: async () => ({
    anchorRuns: [],
    catalogModels: [],
    index: { index_version: "index-v4.1", models: [rankedModel] },
    rigAnchors: [],
    rigCandidates: [],
  }),
  getOnrampCatalog: async () => ({ models: [], popularityAsOf: null }),
}));

vi.mock("@/lib/community-data", () => ({
  getCommunityBoardRows: async () => [communityRow],
}));

import HomePage from "../app/page";

describe("homepage unified board", () => {
  it("renders a community row in the same board markup as ranked rows", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-testid="full-leaderboard"');
    expect(html).toContain("Homepage Ranked Model");
    expect(html).toContain('data-testid="community-row-homepage-community-ticket"');
    expect(html).toContain("Homepage Community Model");
  });
});
