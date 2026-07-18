import { describe, expect, it } from "vitest";
import {
  huggingFaceRepoUrl,
  parseCommunityGroup,
} from "../lib/community-data";

const artifactSha = "a".repeat(64);
const projectionSha = "b".repeat(64);

function groupFixture(displayName = "Qwythos-9B v2", repoId = "empero-ai/Qwythos-9B-v2") {
  return {
    community_model_group_id: `community-group:${"1".repeat(32)}`,
    identity_label: "community-declared, identity-unverified",
    ranked: false,
    schema_version: "localbench.community_publication.v2",
    variants: [{
      artifact_sha256: artifactSha,
      display_name: displayName,
      lineage_enrichment: {
        artifact_sha256: artifactSha,
        association: {
          artifact_to_repo: "unverified",
          basis: "maintainer-associated",
          note: "Maintainer-associated local conversion; artifact-to-repo match is unproven.",
        },
        card_declared_edges: [{
          base: "Qwen/Qwen3.5-9B",
          base_revision: "d".repeat(40),
          child: repoId,
          child_revision: "c".repeat(40),
          source: "hf-model-card",
        }],
        repo: { id: repoId, revision: "c".repeat(40) },
        resolution: { resolved_at: "2026-07-18T01:30:00Z", status: "complete" },
      },
      projection_object_sha256: projectionSha,
      quant_label: "Q4_K_M",
      ranked: false,
      scores: {
        measured_headline_weight: 0.75,
        missing_headline_weight: 0.25,
        partial_composite: 0.4171,
      },
      submission_id: "ticket_fixture",
    }],
  };
}

function firstVariant(group: ReturnType<typeof groupFixture>) {
  const variant = group.variants[0];
  if (variant === undefined) throw new Error("expected fixture variant");
  return variant;
}

describe("community static-data boundary", () => {
  it("parses a strict v2 community group and builds the HF link from repo components", () => {
    const parsed = parseCommunityGroup(groupFixture());
    expect(parsed).not.toBeNull();
    const lineage = parsed?.variants[0]?.lineage_enrichment;
    expect(lineage).toBeDefined();
    if (lineage === undefined) throw new Error("expected validated lineage fixture");
    expect(huggingFaceRepoUrl(lineage.repo.id)).toBe("https://huggingface.co/empero-ai/Qwythos-9B-v2");
  });

  it.each([
    ["oversized display name", "x".repeat(121)],
    ["bidi override", "Qwythos\u202ev2"],
    ["control character", "Qwythos\u0000v2"],
    ["newline", "Qwythos\nv2"],
  ])("rejects %s", (_label, displayName) => {
    expect(parseCommunityGroup(groupFixture(displayName))).toBeNull();
  });

  it.each([
    "javascript:alert(1)/model",
    "https://huggingface.co/owner/name",
  ])("rejects injected HF repo id %s", (repoId) => {
    expect(parseCommunityGroup(groupFixture("Qwythos-9B v2", repoId))).toBeNull();
  });

  it("rejects non-finite, out-of-range, and unknown score data", () => {
    const nonfinite = groupFixture();
    firstVariant(nonfinite).scores.partial_composite = Number.POSITIVE_INFINITY;
    expect(parseCommunityGroup(nonfinite)).toBeNull();

    const outOfRange = groupFixture();
    firstVariant(outOfRange).scores.measured_headline_weight = 1.01;
    expect(parseCommunityGroup(outOfRange)).toBeNull();

    const unknown = groupFixture();
    Object.assign(firstVariant(unknown).scores, { unexpected: 0.5 });
    expect(parseCommunityGroup(unknown)).toBeNull();
  });
});
