import { describe, expect, it } from "vitest";
import {
  bakedBestVariantCandidates,
  communityBestVariantCandidates,
  selectAcrossBestVariantCandidates,
} from "../lib/best-variant";
import type { CommunityArtifactDetail } from "../lib/community-artifact-details";
import type { CommunityBoardRow } from "../lib/community-data";
import { buildFamilyResolutionContext } from "../lib/family-resolution";
import { HEADLINE_LANE } from "../lib/leaderboard-score";
import { sameModelName, variantNameInContext } from "../lib/model-name";
import type { RigMatchCandidate } from "../lib/rig-match";
import type { CatalogModel } from "../lib/schemas";

const ARTIFACT_SHA = "a".repeat(64);

function liveRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: ARTIFACT_SHA,
    axes: {
      tool_use: { status: "measured", score: 40, n: 100, ci: null },
      knowledge: { status: "measured", score: 60, n: 100, ci: null },
      instruction: { status: "measured", score: 55, n: 100, ci: null },
      coding: { status: "measured", score: 50, n: 100, ci: null },
      math: { status: "measured", score: 45, n: 100, ci: null },
    },
    compositeFull: 51.5,
    detailPath: "/model/fixture-base/",
    displayName: "fixture-base-q4-k-m",
    family: "Fixture",
    globalRank: null,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    origin: "project_anchor",
    partialComposite: null,
    perf: {
      decode_tps: 180,
      latency_s_median: 21.5,
      overall_tps: 120,
      prefill_tps: 2400,
      tokens_to_answer_median: 900,
      wall_time_seconds: 49_880,
    },
    quantLabel: "Q4_K_M",
    submissionId: "ticket_fixture_live",
    hardware: { gpu_name: "NVIDIA GeForce RTX 5090", vram_gb: 31.8 },
    ...overrides,
  };
}

function artifactDetail(overrides: Partial<CommunityArtifactDetail> = {}): CommunityArtifactDetail {
  return {
    artifactSha256: ARTIFACT_SHA,
    fileGb: 5.7,
    modelLabel: "Fixture Base",
    quantLabel: "Q4_K_M",
    slug: "fixture-base",
    vramGb8k: 7.2,
    ...overrides,
  };
}

function catalogModel(overrides: Partial<CatalogModel> = {}): CatalogModel {
  return {
    id: "Fixture/Base",
    slug: "fixture-base",
    display_name: "Fixture Base",
    model_kind: "base",
    // The artifact sha ties the live row to this catalog root (artifact-sha resolution),
    // exactly how production envelope rows join the family tree.
    quants: [{ label: "Q4_K_M", file_sha256: ARTIFACT_SHA }],
    ...overrides,
  };
}

function bakedCandidate(overrides: Partial<RigMatchCandidate> = {}): RigMatchCandidate {
  return {
    axes: {},
    demo: false,
    family: "Fixture",
    kind: "community",
    lane: HEADLINE_LANE,
    modelLabel: "Fixture Base",
    modelSlug: "fixture-base",
    nItems: 100,
    nRuns: 1,
    origin: "project_anchor",
    quantLabel: "Q8_0",
    ranked: true,
    runId: "baked-run",
    score: { point: 48, lo: 45, hi: 51 },
    scoreStatus: "measured",
    tier: "standard",
    tokS: 30,
    trustLabel: "project_anchor",
    vramFootprintGb: 8,
    vramRequiredGb8k: 10,
    latencySMedian: 13.2,
    wallTimeSeconds: 4200,
    ...overrides,
  };
}

describe("communityBestVariantCandidates", () => {
  const context = buildFamilyResolutionContext([catalogModel()]);

  it("carries catalog identity, timing, and effective throughput onto the point", () => {
    const candidates = communityBestVariantCandidates([liveRow()], [artifactDetail()], context);
    expect(candidates).toHaveLength(1);
    const point = candidates[0]?.point;
    expect(point?.modelSlug).toBe("fixture-base");
    expect(point?.modelLabel).toBe("Fixture Base");
    expect(point?.runId).toBe("ticket_fixture_live");
    expect(point?.quantLabel).toBe("Q4_K_M");
    expect(point?.wallTimeSeconds).toBe(49_880);
    expect(point?.tokS).toBe(120);
    expect(point?.effectiveVramGb).toBe(7.2);
    expect(point?.hardwareLabel).toContain("5090");
    expect(candidates[0]?.source).toBe("maintainer");
  });

  it("labels non-anchor rows as community source", () => {
    const candidates = communityBestVariantCandidates(
      [liveRow({ origin: "community" })],
      [artifactDetail()],
      context,
    );
    expect(candidates[0]?.source).toBe("community");
  });

  it("excludes rows without a catalog-joined artifact or VRAM figure", () => {
    expect(communityBestVariantCandidates([liveRow()], [], context)).toHaveLength(0);
    expect(
      communityBestVariantCandidates([liveRow()], [artifactDetail({ vramGb8k: null })], context),
    ).toHaveLength(0);
    expect(
      communityBestVariantCandidates([liveRow({ headlineComplete: false })], [artifactDetail()], context),
    ).toHaveLength(0);
  });
});

describe("selectAcrossBestVariantCandidates", () => {
  const context = buildFamilyResolutionContext([catalogModel()]);

  it("collapses a baked and a live run of the same family to the higher composite", () => {
    const baked = bakedBestVariantCandidates([bakedCandidate()], { catalogModels: [catalogModel()] });
    const live = communityBestVariantCandidates([liveRow()], [artifactDetail()], context);
    const points = selectAcrossBestVariantCandidates([...baked, ...live]);
    expect(points).toHaveLength(1);
    expect(points[0]?.runId).toBe("ticket_fixture_live");
  });

  it("keeps the baked winner when it outscores the live row", () => {
    const baked = bakedBestVariantCandidates(
      [bakedCandidate({ score: { point: 60, lo: 57, hi: 63 } })],
      { catalogModels: [catalogModel()] },
    );
    const live = communityBestVariantCandidates([liveRow()], [artifactDetail()], context);
    const points = selectAcrossBestVariantCandidates([...baked, ...live]);
    expect(points).toHaveLength(1);
    expect(points[0]?.runId).toBe("baked-run");
  });
});

describe("model-name helpers", () => {
  it("treats a slugified twin as the same name", () => {
    expect(sameModelName("Bonsai 27B Ternary", "bonsai-27b-ternary")).toBe(true);
    expect(sameModelName("Bonsai 27B Ternary", "Totally Different 13B")).toBe(false);
  });

  it("drops tokens shared with the context model name", () => {
    expect(variantNameInContext("Qwopus 3.6 27B v2 MTP", "Qwen3.6 27B")).toBe("Qwopus v2 MTP");
    expect(variantNameInContext("Bonsai 27B Ternary", "Qwen3.6 27B")).toBe("Bonsai Ternary");
  });

  it("falls back to the full name when every token overlaps", () => {
    expect(variantNameInContext("Qwen3.6 27B", "Qwen3.6 27B")).toBe("Qwen3.6 27B");
  });
});
