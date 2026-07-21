import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityFamilyResults } from "../components/community-family-results";
import { CommunityLeaderboardRow } from "../components/community-leaderboard-row";
import { CommunityFreshness } from "../components/community-live-state";
import type { CommunityBoardRow } from "../lib/community-data";
import { communityRowsWithFamilyPaths } from "../lib/community-family";
import { IndexModelSchema } from "../lib/schemas";

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
  it("renders the joined catalog family and its logo without overwriting the declared family", () => {
    // Given: a row whose free-text family differs from the exact catalog name match.
    const catalogModel = IndexModelSchema.parse({
      axes: {},
      best_run_id: null,
      catalog_id: "prism-ml/Ternary-Bonsai-27B-unpacked",
      composite: null,
      demo: false,
      est_cost_usd: null,
      family: "Qwen3.6",
      kind: "community",
      lane: "answer-only",
      model_label: "Bonsai 27B Ternary",
      n_runs: 0,
      ranked: false,
      replicated: false,
      score_status: "missing",
      slug: "bonsai-27b-ternary",
      tier: null,
      tokens_to_answer_median: null,
    });
    const [joined] = communityRowsWithFamilyPaths([
      { ...liveOnlyRow, displayName: "bonsai-27b-ternary", family: "qwen35" },
    ], [{ ...catalogModel, artifactSha256s: [liveOnlyRow.artifactSha256] }]);
    if (joined === undefined) throw new Error("expected joined community row");

    // When: the joined board row is rendered.
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={[]}
        rank={1}
        row={joined}
        showAgenticColumn={false}
        showStaticIndexColumn={false}
      /></tbody></table>,
    );

    // Then: display and logo use catalog family while the adapter's declared family remains untouched.
    expect(joined.family).toBe("qwen35");
    expect(html).toContain('data-href="/model/bonsai-27b-ternary/"');
    expect(html).toContain('src="/logos/qwen.jpg"');
    expect(html).toContain(">Qwen3.6</div>");
    expect(html).not.toContain(">qwen35</div>");
  });

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
    expect(rowCells(html)[7]).toContain("not captured");
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

    expect(html).toContain("n/a");
    expect(html).not.toContain(">0.0</td>");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).not.toContain("re-scored");
    expect(html).not.toContain("self-reported");
    expect(html).not.toContain('href="https://github.com/');
  });

  it("renders canonical live axes under legacy baked board columns", () => {
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={["tool_use", "instruction", "tool_calling"]}
        rank={1}
        row={{
          ...liveOnlyRow,
          axes: {
            agentic: { ci: null, n: 10, score: 0.71, status: "measured" },
            instruction_following: { ci: null, n: 10, score: 0.66, status: "measured" },
            tool_calling: { ci: null, n: 10, score: 0.81, status: "measured" },
          },
        }}
        showAgenticColumn={false}
        showStaticIndexColumn={false}
      /></tbody></table>,
    );

    expect(html).toContain("71.0");
    expect(html).toContain("66.0");
    expect(html).toContain("81.0");
  });

  it("renders community rows with ranked-row score visuals, family identity, protocol, and hidden sample metadata", () => {
    const html = renderToStaticMarkup(
      <table><tbody><CommunityLeaderboardRow
        axisKeys={["agentic", "knowledge"]}
        rank={1}
        row={{
          ...liveOnlyRow,
          axes: {
            agentic: { ci: [0.21, 0.25], n: 400, score: 0.234, status: "measured" },
            knowledge: { ci: [0.48, 0.52], n: 200, score: 0.5, status: "measured" },
            long_context: { ci: null, n: 32, score: 0.61, status: "measured" },
            tool_calling: { ci: null, n: 80, score: 0.72, status: "measured" },
          },
          compositeFull: 0.444,
          declaredBaseModels: ["Qwen/Qwen3.6-27B"],
          detailPath: "/model/qwen3-6-27b",
          displayName: "Qwopus 27B",
          family: "Qwen3.6",
          hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 32 },
          perf: { decode_tps: 71.5, tokens_to_answer_median: 512, wall_time_seconds: 3660 },
          runtime: { backend: "cuda", name: "llama.cpp", version: "b7421" },
        }}
        showAgenticColumn={false}
        showStaticIndexColumn={false}
      /></tbody></table>,
    );
    const visibleText = html.replace(/<[^>]+>/gu, "");

    expect(html).toContain('src="/logos/qwen.jpg"');
    expect(html).not.toContain('title="Qwen (Alibaba)"');
    expect(html).toContain("LB-2026-07");
    expect(html).toContain("Fine-tune of Qwen/Qwen3.6-27B");
    expect(html).toContain("h-1.5 overflow-hidden rounded-full");
    expect(html).toContain("h-1 overflow-hidden rounded-full");
    expect(html).toContain('title="n=400 scored items"');
    expect(visibleText).toContain("n=400");
    expect(html).toContain("AppWorld task-goal completion");
    expect(html).toContain("Call formatting");
    expect(html).toContain("BFCL v3 multi-turn base — frozen snapshot");
    expect(html).toContain("RULER 32K");
    expect(html).toMatch(/BFCL single-turn<\/dt><dd[^>]*>not measured<\/dd>/u);
    expect(html).toMatch(/RULER 32K<\/dt><dd[^>]*>61\.0<\/dd>/u);
    expect(html).toContain("llama.cpp");
    expect(html).toContain("b7421");
    expect(html).toContain("RTX 5090 · 32 GB");
    expect(html).toContain("512");
    expect(html).toContain("1 h");
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

function rowCells(html: string): readonly string[] {
  const row = html.match(/<tr[\s\S]*?<\/tr>/u)?.[0] ?? "";
  return [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((match) => match[1] ?? "");
}
