import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/app-shell";
import { HomeLeaderboard } from "../components/home-leaderboard";
import MethodologyPage from "../app/methodology/page";
import { ComparePicker } from "../components/compare-picker";
import { getCompareConfigs } from "../lib/compare";
import * as communityData from "../lib/community-data";
import type { CommunityBoardRow } from "../lib/community-data";
import { parseCommunityLiveBoard } from "../lib/community-live";
import { isFullIndexRow } from "../lib/leaderboard-score";
import { IndexModelSchema, ModelDataSchema } from "../lib/schemas";

const AXES = {
  coding: axis(58),
  instruction: axis(62),
  knowledge: axis(66),
  math: axis(54),
  tool_use: axis(42),
};
const LIVE_AXES = {
  agentic: axis(42),
  coding: axis(58),
  instruction_following: axis(62),
  knowledge: axis(66),
  math: axis(54),
  tool_calling: axis(10),
};

const COMPLETE_COMMUNITY_ROW: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  axes: Object.fromEntries(Object.entries(LIVE_AXES).map(([key, value]) => [key, {
    ci: [value.lo / 100, value.hi / 100],
    n: value.n,
    score: value.point / 100,
    status: "measured",
  }])),
  communityModelGroupId: `community-group:${"1".repeat(32)}`,
  compositeFull: 0.57,
  declaredBaseModels: ["Qwen/Qwen3.5-9B"],
  detailPath: "/model/fixture-9b/",
  displayName: "Fixture Community 9B",
  family: "Fixture",
  globalRank: 2,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
  lineage: undefined,
  measuredHeadlineWeight: 1,
  missingHeadlineWeight: 0,
  partialComposite: 0.57,
  quantLabel: "Q4_K_M",
  submissionId: "ticket_fixture",
  submitterDisplayName: "Ada",
  submitterGithubLogin: null,
  submitterKeyFingerprint: null,
  timestamps: null,
  trust: null,
};

describe("Simplicity Reset SITE contract", () => {
  it("parses the tolerant unified live-board shape in one boundary", () => {
    const parsed = parseCommunityLiveBoard({
      generated_at: "2026-07-19T00:00:00Z",
      rows: [{
        axes: Object.fromEntries(Object.entries(LIVE_AXES).map(([key, value]) => [key, {
          ci: [value.lo / 100, value.hi / 100],
          n: value.n,
          score: value.point / 100,
          status: "measured",
        }])),
        global_rank: 2,
        headline_complete: true,
        index_version: "index-v4.1",
        model: {
          display_name: "Fixture Community 9B",
          family: "Fixture",
          file_sha256: "a".repeat(64),
          quant_label: "Q4_K_M",
        },
        origin: "community",
        scores: { composite_full: 0.57, headline_score: 0.57 },
        submission_id: `ticket_${"2".repeat(32)}`,
        submitter: { unverified_handle: "Ada" },
      }],
    });

    expect(parsed).toMatchObject({
      droppedRows: 0,
      rows: [{
        axes: expect.objectContaining({ agentic: expect.anything(), tool_calling: expect.anything() }),
        globalRank: 2,
        headlineComplete: true,
        origin: "community",
        submitterDisplayName: "Ada",
      }],
    });
  });

  it("ranks complete community rows and reserves the only provenance badge for project runs", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard
        models={[projectModel()]}
        communityRows={[COMPLETE_COMMUNITY_ROW]}
        indexVersion="index-v4.1"
      />,
    );
    const communityStart = html.indexOf('data-testid="community-row-ticket_fixture"');
    const communityHtml = html.slice(communityStart, html.indexOf("</tr>", communityStart));

    expect(communityStart).toBeGreaterThan(-1);
    expect(communityHtml).toMatch(/<td[^>]*>\s*2\s*<\/td>/u);
    expect(html.match(/project run/giu)).toHaveLength(1);
    expect(communityHtml).toContain("submitted as Ada — unverified");
    expect(html).not.toMatch(/self[- ]reported|maintainer[- ]run|trust tier/iu);
    expect(html).not.toContain("local-bench runs");
    expect(html).not.toContain("Community rows never receive a rank");
  });

  it("offers family, size, quant, and RAM filters without source segregation", () => {
    const html = renderToStaticMarkup(
      <HomeLeaderboard models={[projectModel()]} communityRows={[COMPLETE_COMMUNITY_ROW]} indexVersion="index-v4.1" />,
    );

    expect(html).toContain('aria-label="Family filter"');
    expect(html).toContain('aria-label="Model size filter"');
    expect(html).toContain('aria-label="Quant filter"');
    expect(html).toContain('aria-label="RAM filter"');
    expect(html).not.toContain('aria-label="Leaderboard source filter"');
  });

  it("uses completeness rather than ranked:false or origin to admit a row", () => {
    const row = projectModel({ origin: "community", ranked: false, trust_label: "community_self_submitted" });

    expect(isFullIndexRow(row)).toBe(true);
  });

  it("adds complete live community rows to the compare picker", () => {
    const model = ModelDataSchema.parse({
      demo: false,
      family: "Fixture",
      kind: "maintainer_project",
      model_kind: "base",
      model_label: "Fixture Project 12B",
      runs: [],
      slug: "fixture-project-12b",
    });
    const configs = getCompareConfigs([model], [COMPLETE_COMMUNITY_ROW]);
    const html = renderToStaticMarkup(
      <ComparePicker
        configs={configs}
        fineTunePresets={[]}
        initialLeftId="ticket_fixture"
        initialRightId="ticket_fixture"
      />,
    );

    expect(configs).toContainEqual(expect.objectContaining({
      id: "ticket_fixture",
      modelLabel: "Fixture Community 9B",
      modelHref: "/model/fixture-9b/",
      modelSlug: "fixture-9b",
      quantLabel: "Q4_K_M",
    }));
    expect(html).toContain("Fixture Community 9B");
    expect(html).not.toContain("&gt;512 GB");
    expect(html).toContain("Open left model");
    expect(html).toContain("Swipe horizontally for per-axis deltas");
    const optionText = /<option[^>]*value="ticket_fixture"[^>]*>([^<]+)<\/option>/u.exec(html)?.[1] ?? "";
    expect(optionText).toContain("Fixture Community 9B");
    expect(optionText).toContain("Q4_K_M");
    expect(optionText).not.toMatch(/full index|n\/a/iu);
  });

  it("maps the active internal index to LB-2026-07 on public surfaces", () => {
    const html = renderToStaticMarkup(
      <AppShell families={["Fixture"]} indexVersion="index-v4.1" suiteVersion="suite-v1-full-exec-6axis-v1" usesDemoData={false}>
        <div>content</div>
      </AppShell>,
    );

    expect(html).toContain("LB-2026-07");
    expect(html).not.toContain("index-v4.1");
  });

  it("publishes the honest post-publication trust statement", async () => {
    const text = renderToStaticMarkup(await MethodologyPage()).replace(/\s+/gu, " ");

    expect(text).toContain("Community-reported results publish immediately");
    expect(text).toContain("preserves the submitted identity, protocol, scores, and evidence bundle");
    expect(text).toContain("computes the common composite");
    expect(text).toContain("suppresses rows when problems are demonstrated");
    expect(text).toContain("not independently reproduced by default");
  });

  it("folds community axes and submission detail into the matching family page", async () => {
    const rowsMock = vi.spyOn(communityData, "getCommunityBoardRows").mockResolvedValue([COMPLETE_COMMUNITY_ROW]);
    const { default: ModelPage } = await import("../app/model/[slug]/page");
    const html = renderToStaticMarkup(await ModelPage({ params: Promise.resolve({ slug: "qwen3-5-9b" }) }));
    rowsMock.mockRestore();

    expect(html).toContain("Fixture Community 9B");
    expect(html).toContain("Per-axis breakdown");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).not.toContain("/community/model/");
    expect(html).not.toContain("Community results for this family");
  });
});

function axis(point: number) {
  return {
    hi: point + 2,
    lo: point - 2,
    n: 20,
    n_errors: 0,
    n_no_answer: 0,
    point,
    raw_accuracy: point / 100,
  };
}

function projectModel(overrides: Readonly<Record<string, unknown>> = {}) {
  return IndexModelSchema.parse({
    axes: AXES,
    best_run_id: "fixture-project-12b__fixture-q4km",
    composite: { hi: 64, lo: 60, point: 62 },
    composite_full: { hi: 64, lo: 60, point: 62 },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    gpu: { driver: null, name: "Fixture GPU", vram_gb: 24, vram_mb: 24_576 },
    index_version: "index-v4.1",
    kind: "maintainer_project",
    lane: "bounded-final-v2",
    model_label: "Fixture Project 12B Q4_K_M",
    n_runs: 1,
    origin: "project_anchor",
    ranked: true,
    replicated: false,
    score_status: "measured",
    slug: "fixture-project-12b",
    tier: "standard",
    tokens_to_answer_median: 128,
    trust_label: "project_anchor",
    ...overrides,
  });
}
