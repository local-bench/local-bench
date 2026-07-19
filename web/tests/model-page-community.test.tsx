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

    expect(html).toContain("Reported runs");
    expect(html).toContain("Qwythos-9B v2");
    expect(html).toContain("Reported artifact lineage");
    expect(html).toContain("historical incomplete report");
    expect(html).not.toContain("/community/model/");
    expect(html).not.toContain("Suppressed fixture model");
  });

  it("shows a lineage-free reported run on the catalog model page by artifact SHA", async () => {
    // Given: a public row whose only catalog identity is the Bonsai artifact SHA.
    const shaOnlyGroup = communityData.parseCommunityGroup({
      community_model_group_id: `community-group:${"2".repeat(32)}`,
      identity_label: "community-declared, identity-unverified",
      ranked: false,
      schema_version: "localbench.community_publication.v2",
      variants: [{
        artifact_sha256: "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757",
        display_name: "Opaque community declaration",
        projection_object_sha256: "c".repeat(64),
        quant_label: "Q2_0",
        ranked: false,
        scores: {
          measured_headline_weight: 0.53,
          missing_headline_weight: 0.48,
          partial_composite: 0.5696,
        },
        submission_id: "ticket_bonsai_sha_only",
      }],
    });
    if (shaOnlyGroup === null) throw new Error("SHA-only model page fixture must validate");
    const rowsMock = vi.spyOn(communityData, "getCommunityBoardRows").mockResolvedValue(
      communityData.communityBoardRows([shaOnlyGroup]),
    );

    // When: the catalog model page is rendered.
    const { default: ModelPage } = await import("../app/model/[slug]/page");
    const html = renderToStaticMarkup(await ModelPage({
      params: Promise.resolve({ slug: "bonsai-27b-ternary" }),
    }));
    rowsMock.mockRestore();

    // Then: the artifact-matched reported run appears on that model page.
    expect(html).toContain("Reported runs");
    expect(html).toContain("Opaque community declaration");
    expect(html).toContain("ticket_bonsai_sha_only");
  });
});
