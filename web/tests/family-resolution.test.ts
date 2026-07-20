import { describe, expect, it } from "vitest";
import type { CommunityBoardRow } from "../lib/community-data";
import {
  buildFamilyResolutionContext,
  resolveFamily,
} from "../lib/family-resolution";
import { overlayLineageByArtifactSha } from "../lib/overlay-lineage";
import type { CatalogModel } from "../lib/schemas";

const BONSAI_SHA = "868c11714cf8fe47f5ec9eeb2be0ab1a337112886f92ee0ede6b855c4fa31757";
const QWYTHOS_SHA = "c0a588704f422b713eca29b2c1f192ae6f69aea3f9e7cb64f9ecdb76ff7a85f4";

const qwen36 = catalogModel({
  id: "Qwen/Qwen3.6-27B",
  slug: "qwen3-6-27b",
  display_name: "Qwen3.6 27B",
  family: "Qwen3.6",
});
const bonsai = catalogModel({
  id: "prism-ml/Ternary-Bonsai-27B-unpacked",
  slug: "bonsai-27b-ternary",
  display_name: "Bonsai 27B Ternary",
  family: "Qwen3.6",
  base_model: qwen36.id,
  model_kind: "finetune",
  quants: [{ label: "Q2_0", file_sha256: BONSAI_SHA }],
});

describe("canonical family resolution", () => {
  it("routes a lineage-free Bonsai-shaped row through its artifact SHA", () => {
    // Given: Bonsai's live row has only the catalog artifact SHA and a misleading declared family.
    const context = buildFamilyResolutionContext([qwen36, bonsai]);
    const row = communityRow({
      artifactSha256: BONSAI_SHA,
      declaredBaseModels: [],
      displayName: "Opaque community declaration",
      family: "qwen35",
      lineage: undefined,
    });

    // When: the canonical resolver evaluates every identity signal.
    const resolution = resolveFamily(row, context);

    // Then: artifact identity wins and exposes the full catalog chain to the Qwen3.6 root.
    expect(resolution).toEqual({
      chainCatalogIds: [bonsai.id, qwen36.id],
      confidence: "artifact-sha",
      familyLabel: "Qwen3.6",
      rootCatalogId: qwen36.id,
      rootSlug: qwen36.slug,
    });
  });

  it("joins overlay lineage by artifact SHA when no catalog artifact owns the row", () => {
    // Given: the Qwythos artifact exists only in the maintainer overlay for this reduced catalog.
    const qwen35 = catalogModel({
      id: "Qwen/Qwen3.5-9B",
      slug: "qwen3-5-9b",
      display_name: "Qwen3.5 9B",
      family: "Qwen3.5",
    });
    const mythos = catalogModel({
      id: "empero-ai/Qwythos-9B-Claude-Mythos-5-1M",
      slug: "qwythos-9b-claude-mythos-5-1m",
      display_name: "Qwythos 9B Claude Mythos 5 1M",
      family: "Qwen3.5",
      base_model: qwen35.id,
      model_kind: "finetune",
    });
    const context = buildFamilyResolutionContext(
      [qwen35, mythos],
      [],
      overlayLineageByArtifactSha(),
    );

    // When: a live-only row has no declared lineage, family, or exact catalog name.
    const resolution = resolveFamily(communityRow({
      artifactSha256: QWYTHOS_SHA,
      declaredBaseModels: [],
      displayName: "Live-only Qwythos artifact",
      family: null,
    }), context);

    // Then: overlay edges resolve through the intermediate catalog entry to Qwen3.5-9B.
    expect(resolution).toEqual({
      chainCatalogIds: [mythos.id, qwen35.id],
      confidence: "lineage",
      familyLabel: "Qwen3.5",
      rootCatalogId: qwen35.id,
      rootSlug: qwen35.slug,
    });
  });

  it.each([
    {
      expected: {
        chainCatalogIds: [bonsai.id, qwen36.id],
        confidence: "lineage" as const,
        familyLabel: "Qwen3.6",
        rootCatalogId: qwen36.id,
        rootSlug: qwen36.slug,
      },
      label: "exact declared catalog lineage",
      row: communityRow({ declaredBaseModels: [bonsai.id], displayName: "Unknown", family: null }),
    },
    {
      expected: {
        chainCatalogIds: [],
        confidence: "declared-family" as const,
        familyLabel: "Qwen3.6",
        rootCatalogId: null,
        rootSlug: null,
      },
      label: "normalized declared family equality",
      row: communityRow({ artifactSha256: "b".repeat(64), displayName: "Unknown", family: "qwen36" }),
    },
    {
      expected: {
        chainCatalogIds: [bonsai.id, qwen36.id],
        confidence: "exact-name" as const,
        familyLabel: "Qwen3.6",
        rootCatalogId: qwen36.id,
        rootSlug: qwen36.slug,
      },
      label: "exact normalized model name",
      row: communityRow({ artifactSha256: "c".repeat(64), displayName: "Bonsai 27B Ternary", family: null }),
    },
    {
      expected: {
        chainCatalogIds: [],
        confidence: null,
        familyLabel: null,
        rootCatalogId: null,
        rootSlug: null,
      },
      label: "unresolved row",
      row: communityRow({ artifactSha256: "d".repeat(64), displayName: "Unknown", family: null }),
    },
  ])("uses $label only after stronger identities miss", ({ expected, row }) => {
    // Given: the row carries exactly one remaining usable identity signal.
    const context = buildFamilyResolutionContext([qwen36, bonsai], [], new Map());

    // When: the resolver applies the documented precedence.
    const resolution = resolveFamily(row, context);

    // Then: the matching confidence and authoritative family fields are returned.
    expect(resolution).toEqual(expected);
  });
});

function catalogModel(overrides: Partial<CatalogModel>): CatalogModel {
  return {
    id: "Fixture/Model",
    slug: "fixture-model",
    display_name: "Fixture Model",
    model_kind: "base",
    quants: [],
    ...overrides,
  };
}

function communityRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: "a".repeat(64),
    compositeFull: 0.4,
    detailPath: null,
    displayName: "Community fixture",
    family: null,
    globalRank: null,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    partialComposite: 0.4,
    quantLabel: "Q4_K_M",
    submissionId: "ticket_family_resolution_fixture",
    ...overrides,
  };
}
