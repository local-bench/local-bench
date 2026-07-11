import { describe, expect, it } from "vitest";
import { selectBestVariantPoints } from "../lib/best-variant";
import { splitLeaderboard } from "../lib/leaderboard";
import { buildLaneRanks } from "../lib/leaderboard-sort";
import { selectTrustedHeaderSource } from "../lib/trusted-population";
import type { RigMatchCandidate } from "../lib/rig-match";
import { IndexModelSchema } from "../lib/schemas";

describe("trusted ranked population exclusion", () => {
  it("an arbitrarily high community score cannot change ranks, representatives, or a maintainer header", () => {
    const trusted = indexRow("maintainer", 55, "project_anchor", "project_anchor");
    const adversary = indexRow("community-adversary", 100, "community", "community_self_submitted");
    const baselineRanks = buildLaneRanks([trusted], "full");
    const attackedRanks = buildLaneRanks([trusted, adversary], "full");
    expect(splitLeaderboard([trusted, adversary]).ranked.map((row) => row.slug)).toEqual(["maintainer"]);
    expect(attackedRanks).toEqual(baselineRanks);

    const candidates = [rigCandidate("maintainer", 55, "project_anchor", "project_anchor"), rigCandidate("community-adversary", 100, "community", "community_self_submitted")];
    expect(selectBestVariantPoints(candidates).map((point) => point.modelSlug)).toEqual(["maintainer"]);
    const headerRows = [
      { origin: "community", ranked: true, trust_label: "community_self_submitted", label: "attacker" },
      { origin: "project_anchor", ranked: true, trust_label: "project_anchor", label: "maintainer" },
    ];
    expect(selectTrustedHeaderSource(headerRows)?.label).toBe("maintainer");
  });
});

function score(point: number) { return { hi: point, lo: point, point }; }
function axisScore(point: number) { return { ...score(point), n: 1, n_errors: 0, n_no_answer: 0, raw_accuracy: point / 100 }; }

function indexRow(slug: string, point: number, origin: string, trust_label: string) {
  return IndexModelSchema.parse({
    axes: { knowledge: axisScore(point) }, best_run_id: `${slug}-run`, composite: score(point), composite_full: score(point),
    demo: false, est_cost_usd: null, family: "Fixture", kind: "community",
    lane: "bounded-final-v2", model_label: slug, n_runs: 1, origin, ranked: true, replicated: false,
    score_status: "measured" as const, slug, tier: "standard", tokens_to_answer_median: null, trust_label,
  });
}

function rigCandidate(modelSlug: string, point: number, origin: string, trustLabel: string): RigMatchCandidate {
  return {
    axes: { knowledge: axisScore(point) }, demo: false, family: "Fixture", kind: "community",
    lane: "bounded-final-v2", modelLabel: modelSlug, modelSlug, nItems: 100, nRuns: 2, origin,
    quantLabel: "Q4_K_M", ranked: true, runId: `${modelSlug}-run`, score: score(point), scoreStatus: "measured" as const,
    tier: "standard", tokS: 10, latencySMedian: 1, wallTimeSeconds: 2, trustLabel,
    vramFootprintGb: 8, vramRequiredGb8k: null,
  };
}
