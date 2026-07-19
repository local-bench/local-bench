import { describe, expect, it } from "vitest";
import { selectBestVariantPoints } from "../lib/best-variant";
import { filterUnifiedLeaderboardRows } from "../lib/unified-leaderboard";
import type { RigMatchCandidate } from "../lib/rig-match";
import { IndexModelSchema } from "../lib/schemas";

describe("complete community population", () => {
  it("ranks a complete community row by score instead of excluding it by origin", () => {
    const project = indexRow("project", 55, "project_anchor", "project_anchor");
    const community = indexRow("community", 100, "community", "community_self_submitted");
    const rows = filterUnifiedLeaderboardRows([project, community], []);

    expect(rows.map((row) => row.source === "local-bench" ? row.model.slug : row.row.submissionId)).toEqual([
      "community",
      "project",
    ]);
    expect(rows.map((row) => row.rank)).toEqual([1, 2]);

    const candidates = [
      rigCandidate("project", 55, "project_anchor", "project_anchor"),
      rigCandidate("community", 100, "community", "community_self_submitted"),
    ];
    expect(selectBestVariantPoints(candidates).map((point) => point.modelSlug).sort()).toEqual(["community", "project"]);
  });
});

function score(point: number) { return { hi: point, lo: point, point }; }
function axisScore(point: number) { return { ...score(point), n: 1, n_errors: 0, n_no_answer: 0, raw_accuracy: point / 100 }; }
function axes(point: number) {
  return {
    agentic: axisScore(point),
    coding: axisScore(point),
    instruction: axisScore(point),
    knowledge: axisScore(point),
    math: axisScore(point),
    tool_calling: axisScore(point),
  };
}

function indexRow(slug: string, point: number, origin: string, trustLabel: string) {
  return IndexModelSchema.parse({
    axes: axes(point), best_run_id: `${slug}-run`, composite: score(point), composite_full: score(point),
    demo: false, est_cost_usd: null, family: "Fixture", kind: "community",
    lane: "bounded-final-v2", model_label: slug, n_runs: 1, origin, ranked: false, replicated: false,
    score_status: "measured" as const, slug, tier: "standard", tokens_to_answer_median: null, trust_label: trustLabel,
  });
}

function rigCandidate(modelSlug: string, point: number, origin: string, trustLabel: string): RigMatchCandidate {
  return {
    axes: axes(point), demo: false, family: "Fixture", kind: "community",
    lane: "bounded-final-v2", modelLabel: modelSlug, modelSlug, nItems: 100, nRuns: 2, origin,
    quantLabel: "Q4_K_M", ranked: false, runId: `${modelSlug}-run`, score: score(point), scoreStatus: "measured" as const,
    tier: "standard", tokS: 10, latencySMedian: 1, wallTimeSeconds: 2, trustLabel,
    vramFootprintGb: 8, vramRequiredGb8k: null,
  };
}
