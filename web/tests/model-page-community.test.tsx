import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import * as communityData from "../lib/community-data";

const communityGroup = communityData.parseCommunityGroup({
  community_model_group_id: `community-group:${"1".repeat(32)}`,
  identity_label: "community-declared, identity-unverified",
  ranked: false,
  schema_version: "localbench.community_publication.v2",
  variants: [{
    artifact_sha256: "a".repeat(64),
    display_name: "Qwythos-9B v2",
    lineage_enrichment: {
      artifact_sha256: "a".repeat(64),
      association: {
        artifact_to_repo: "unverified",
        basis: "maintainer-associated",
        note: "Local artifact association remains unproven.",
      },
      card_declared_edges: [{
        base: "Qwen/Qwen3.5-9B",
        base_revision: "d".repeat(40),
        child: "empero-ai/Qwythos-9B-v2",
        child_revision: "c".repeat(40),
        source: "hf-model-card",
      }],
      repo: { id: "empero-ai/Qwythos-9B-v2", revision: "c".repeat(40) },
      resolution: { resolved_at: "2026-07-18T01:30:00Z", status: "complete" },
    },
    projection_object_sha256: "b".repeat(64),
    quant_label: "Q4_K_M",
    ranked: false,
    scores: {
      measured_headline_weight: 0.75,
      missing_headline_weight: 0.25,
      partial_composite: 0.4171,
    },
    submission_id: "ticket_visible",
  }],
});

if (communityGroup === null) throw new Error("community page fixture must validate");
const communityRows = communityData.communityBoardRows([communityGroup]);

describe("model page community family results", () => {
  it("shows Qwythos on the Qwen3.5-9B page with honest association labeling", async () => {
    const rowsMock = vi.spyOn(communityData, "getCommunityBoardRows").mockResolvedValue(communityRows);
    const { default: ModelPage } = await import("../app/model/[slug]/page");
    const html = renderToStaticMarkup(await ModelPage({
      params: Promise.resolve({ slug: "qwen3-5-9b" }),
    }));
    rowsMock.mockRestore();

    expect(html).toContain("Community results for this family");
    expect(html).toContain("Qwythos-9B v2");
    expect(html).toContain("community");
    expect(html).toContain("not independently verified");
    expect(html).toContain("HF model-card-declared lineage (unverified)");
    expect(html).toContain("does not imply endorsement by the base model author");
    expect(html).toContain('href="/community/model/11111111111111111111111111111111"');
    expect(html).not.toContain("Suppressed fixture model");
  });
});
