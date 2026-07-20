import { describe, expect, it } from "vitest";
import type { CommunityBoardRow } from "../lib/community-data";
import { communityRowsForModel, communityRowsWithFamilyPaths } from "../lib/community-family";
import { IndexModelSchema } from "../lib/schemas";

const ROW_SHA = "a".repeat(64);

function communityRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: ROW_SHA,
    compositeFull: null,
    detailPath: null,
    displayName: "Community Fixture",
    family: "Fixture Family",
    globalRank: null,
    headlineComplete: false,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: null,
    lineage: undefined,
    measuredHeadlineWeight: null,
    missingHeadlineWeight: null,
    partialComposite: null,
    quantLabel: null,
    submissionId: "ticket_community_fixture",
    ...overrides,
  };
}

function indexModel(slug: string, family: string, catalogId: string | null = null) {
  return IndexModelSchema.parse({
    axes: {},
    best_run_id: null,
    catalog_id: catalogId,
    composite: null,
    demo: false,
    est_cost_usd: null,
    family,
    kind: "community",
    lane: "answer-only",
    model_label: slug,
    n_runs: 0,
    ranked: false,
    replicated: false,
    score_status: "missing",
    slug,
    tier: null,
    tokens_to_answer_median: null,
  });
}

describe("community catalog family resolution", () => {
  it("prefers an artifact SHA match over an earlier family fallback", () => {
    // Given: the first catalog entry matches only the declared family and the second owns the artifact.
    const row = communityRow();
    const familyOnly = indexModel("family-only", "Fixture Family");
    const artifactOwner = {
      ...indexModel("artifact-owner", "Authoritative Family"),
      artifactSha256s: [ROW_SHA],
    };

    // When: the row is resolved to a catalog model.
    const [resolved] = communityRowsWithFamilyPaths([row], [familyOnly, artifactOwner]);

    // Then: artifact identity wins regardless of catalog order.
    expect(resolved).toMatchObject({
      catalogFamily: "Authoritative Family",
      detailPath: "/model/artifact-owner/",
      family: "Fixture Family",
    });
  });

  it("prefers lineage repository identity over an earlier family fallback", () => {
    // Given: a family-only candidate precedes the catalog entry named by declared lineage.
    const row = communityRow({ declaredBaseModels: ["Vendor/Lineage-Model"] });
    const familyOnly = indexModel("family-only", "Fixture Family");
    const lineageOwner = indexModel("lineage-owner", "Lineage Family", "Vendor/Lineage-Model");

    // When: the row is resolved to a catalog model.
    const [resolved] = communityRowsWithFamilyPaths([row], [familyOnly, lineageOwner]);

    // Then: lineage identity wins over family similarity.
    expect(resolved).toMatchObject({
      catalogFamily: "Lineage Family",
      detailPath: null,
    });
  });

  it("normalizes punctuation and casing for a label-only family fallback", () => {
    // Given: the declared and catalog family spellings differ only in formatting.
    const row = communityRow({ family: "Qwen 3.6" });

    // When: the row is resolved without artifact or lineage identity.
    const [resolved] = communityRowsWithFamilyPaths([row], [indexModel("qwen-family", "qWEN-3_6")]);

    // Then: normalized exact family equality supplies only an honest family label.
    expect(resolved).toMatchObject({
      catalogFamily: "qWEN-3_6",
      confidence: "declared-family",
      detailPath: null,
    });
  });

  it("uses exact normalized display-name to slug equality only after stronger identities miss", () => {
    // Given: the index has no artifact SHA field and the submitter family does not match the catalog family.
    const row = communityRow({ displayName: "Bonsai 27B Ternary", family: "qwen35" });

    // When: the row is resolved against the real catalog naming shape.
    const [resolved] = communityRowsWithFamilyPaths([row], [indexModel("bonsai-27b-ternary", "Qwen3.6")]);

    // Then: exact normalized name identity supplies family resolution without inventing an artifact-owned route.
    expect(resolved).toMatchObject({
      catalogFamily: "Qwen3.6",
      detailPath: null,
      family: "qwen35",
    });
  });

  it("keeps an unresolved row path null and its declared family auditable", () => {
    // Given: no catalog identity, family, or exact name matches the row.
    const row = communityRow({ family: "raw-declared-family" });

    // When: catalog resolution is attempted.
    const [resolved] = communityRowsWithFamilyPaths([row], [indexModel("unrelated", "Other Family")]);

    // Then: the row stays unresolved and retains its declared family for auditing.
    expect(resolved).toMatchObject({
      confidence: null,
      detailPath: null,
      family: "raw-declared-family",
      familyLabel: null,
    });
  });

  it("matches a model-page target by artifact SHA without lineage", () => {
    // Given: a public row with no declared base and a model target carrying the catalog artifact SHA.
    const row = communityRow({ declaredBaseModels: [] });

    // When: the model-page matcher filters the community rows.
    const visible = communityRowsForModel([row], {
      artifactSha256s: [ROW_SHA],
      catalogId: "Vendor/Unrelated-Catalog-Id",
      family: "Unrelated Family",
      modelLabel: "Unrelated Label",
      slug: "unrelated-slug",
    });

    // Then: the reported artifact is visible on that model page.
    expect(visible).toEqual([row]);
  });

  it("attaches a community fine-tune to every catalog model in its resolved chain", () => {
    // Given: Bonsai resolves through its own catalog entry to the Qwen3.6-27B root.
    const row = communityRow({
      chainCatalogIds: [
        "prism-ml/Ternary-Bonsai-27B-unpacked",
        "Qwen/Qwen3.6-27B",
      ],
      declaredBaseModels: [],
      family: "qwen35",
    });

    // When: the base model page filters reported community runs.
    const visible = communityRowsForModel([row], {
      catalogId: "Qwen/Qwen3.6-27B",
      family: "Qwen3.6",
      modelLabel: "Qwen3.6 27B",
      slug: "qwen3-6-27b",
    });

    // Then: the resolved transitive chain attaches Bonsai without trusting its declared family.
    expect(visible).toEqual([row]);
  });

  it("does not place a row on an unrelated model page from free-text family alone", () => {
    // Given: a row and target share a normalized family but have no matching artifact, lineage, or name.
    const row = communityRow({ displayName: "Bonsai 27B Ternary", family: "Qwen3.6" });

    // When: an unrelated Qwen catalog page filters community results.
    const visible = communityRowsForModel([row], {
      catalogId: "Qwen/Qwen3.6-35B-A3B",
      family: "Qwen3.6",
      modelLabel: "Qwen3.6 35B A3B",
      slug: "qwen3-6-35b-a3b",
    });

    // Then: submitter free-text does not broaden model-page membership.
    expect(visible).toEqual([]);
  });
});
