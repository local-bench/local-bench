import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ModelPageCommunityViews } from "../components/model-page-community";
import { parseCommunityLiveBoard, reconcileCommunityRows } from "../lib/community-live";
import * as communityData from "../lib/community-data";
import { getModelPageData } from "../lib/data";
import { familyResolutionContext } from "../lib/family-resolution-data";
import { bonsaiLiveEnvelope } from "./fixtures/bonsai-live-community";

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
  it("feeds one live-reconciled row to the board, scatter, and reported results", async () => {
    const pageData = await getModelPageData("qwen3-6-27b");
    const resolutionContext = familyResolutionContext();
    const parsed = parseCommunityLiveBoard(bonsaiLiveEnvelope());
    if (parsed === null) throw new Error("expected valid Bonsai live envelope");
    const rows = reconcileCommunityRows([], parsed.rows, resolutionContext);
    const artifactSha256s = pageData.model.artifacts?.map((artifact) => artifact.file_sha256);
    const target = {
      catalogId: pageData.model.catalog_id,
      family: pageData.model.family,
      modelLabel: pageData.model.model_label,
      slug: pageData.model.slug,
      ...(artifactSha256s === undefined ? {} : { artifactSha256s }),
    };

    const html = renderToStaticMarkup(<ModelPageCommunityViews
      anchorRuns={pageData.anchorRuns}
      familyModels={pageData.familyModels}
      model={pageData.model}
      state={{
        droppedRows: parsed.droppedRows,
        generatedAt: parsed.generatedAt,
        kind: "live",
        rows,
      }}
      target={target}
    />);
    const boardCells = rowCellsContaining(html, "bonsai-27b-ternary");

    expect(boardCells[2]).toContain("36.7");
    expect(boardCells[3]).toContain("42.0");
    expect(boardCells[4]).toContain("51.0");
    expect(boardCells[5]).toContain("63.0");
    expect(boardCells[6]).toContain("85.0");
    expect(boardCells[7]).toContain("90.0");
    expect(html).toContain('data-point-kind="community"');
    expect(html).toContain("~9.5 GB to run");
    expect(html).not.toContain("31.8 GB");
    expect(html).toContain("Reported runs");
    expect(html).toContain("Instruction following");
    expect(html).toContain("63.0 · n=20");
  });

  it("renders a maintainer-submitted live row with project provenance on every model-page surface", async () => {
    // Given: a live row whose ticket-minted origin is project_anchor.
    const pageData = await getModelPageData("qwen3-6-27b");
    const resolutionContext = familyResolutionContext();
    const parsed = parseCommunityLiveBoard(bonsaiLiveEnvelope());
    if (parsed === null) throw new Error("expected valid Bonsai live envelope");
    const rows = reconcileCommunityRows([], parsed.rows.map((row) => ({
      ...row,
      badge: "project-run",
      origin: "project_anchor",
    })), resolutionContext);
    const artifactSha256s = pageData.model.artifacts?.map((artifact) => artifact.file_sha256);

    // When: the project result is rendered through the shared model-page views.
    const html = renderToStaticMarkup(<ModelPageCommunityViews
      anchorRuns={pageData.anchorRuns}
      familyModels={pageData.familyModels}
      model={pageData.model}
      state={{
        droppedRows: parsed.droppedRows,
        generatedAt: parsed.generatedAt,
        kind: "live",
        rows,
      }}
      target={{
        catalogId: pageData.model.catalog_id,
        family: pageData.model.family,
        modelLabel: pageData.model.model_label,
        slug: pageData.model.slug,
        ...(artifactSha256s === undefined ? {} : { artifactSha256s }),
      }}
    />);
    const projectCells = rowCellsContaining(html, "bonsai-27b-ternary");

    // Then: the table, scatter, and reported-result card all use project framing.
    expect(projectCells[1]).toContain(">project run</span>");
    expect(html).toContain('data-point-kind="project"');
    expect(html).toContain("Project runs");
    expect(html).not.toContain(">self-reported</span>");
    expect(html).not.toContain("submitted as");
  });

  it("server-renders a baked composite without axes or a community scatter point", async () => {
    const pageData = await getModelPageData("qwen3-6-27b");
    const bakedRow: communityData.CommunityBoardRow = {
      artifactSha256: "b".repeat(64),
      axes: {},
      compositeFull: 0.3673,
      detailPath: null,
      displayName: "Baked fallback variant",
      family: null,
      globalRank: null,
      headlineComplete: true,
      identityLabel: "community-declared, identity-unverified",
      indexVersion: null,
      lineage: undefined,
      measuredHeadlineWeight: 1,
      missingHeadlineWeight: 0,
      origin: "community",
      partialComposite: 0.3673,
      quantLabel: "Q2_0",
      ranked: false,
      submissionId: "ticket_baked_fallback",
    };
    const html = renderToStaticMarkup(<ModelPageCommunityViews
      anchorRuns={pageData.anchorRuns}
      familyModels={pageData.familyModels}
      model={pageData.model}
      state={{ kind: "loading", rows: [bakedRow] }}
      target={{
        catalogId: pageData.model.catalog_id,
        family: pageData.model.family,
        modelLabel: pageData.model.model_label,
        slug: pageData.model.slug,
      }}
    />);
    const boardCells = rowCellsContaining(html, "Baked fallback variant");

    expect(boardCells[2]).toContain("36.7");
    expect(boardCells.slice(3, 8).every((cell) => cell.includes("n/a"))).toBe(true);
    expect(html).not.toContain('data-point-kind="community"');
  });

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

  it("shows a lineage-free reported run on its transitive base model page by artifact SHA", async () => {
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
          composite_full: 0.3673,
          headline_score: 0.3673,
          measured_headline_weight: 1,
          missing_headline_weight: 0,
          partial_composite: 0.3673,
        },
        submission_id: "ticket_bonsai_sha_only",
      }],
    });
    if (shaOnlyGroup === null) throw new Error("SHA-only model page fixture must validate");
    const rowsMock = vi.spyOn(communityData, "getCommunityBoardRows").mockResolvedValue(
      communityData.communityBoardRows([shaOnlyGroup]),
    );

    // When: the transitive base model page is rendered.
    const { default: ModelPage } = await import("../app/model/[slug]/page");
    const html = renderToStaticMarkup(await ModelPage({
      params: Promise.resolve({ slug: "qwen3-6-27b" }),
    }));
    rowsMock.mockRestore();

    // Then: the artifact-matched reported run appears through its resolved catalog chain.
    expect(html).toContain("Reported runs");
    expect(html).toContain("Opaque community declaration");
    expect(html).toContain("ticket_bonsai_sha_only");
    expect(html).toContain('data-source="community"');
    expect(html).toContain('data-point-kind="community"');
    expect(html).toContain(">self-reported</span>");
  });
});

function rowCellsContaining(html: string, text: string): readonly string[] {
  const row = [...html.matchAll(/<tr[\s\S]*?<\/tr>/gu)]
    .map((match) => match[0])
    .find((candidate) => candidate.includes(text)) ?? "";
  return [...row.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((match) => match[1] ?? "");
}
