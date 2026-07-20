import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  AwaitingFamilyAssignment,
  FamilyModelTable,
} from "../components/family-community-models";
import { FamilyDirectory } from "../components/family-directory";
import type { CommunityBoardRow } from "../lib/community-data";
import { familySummaries } from "../lib/families";
import { EMPTY_FAMILY_RESOLUTION_CONTEXT } from "../lib/family-resolution";
import { IndexModelSchema, type IndexModel } from "../lib/schemas";

describe("family community surfaces", () => {
  it("includes resolved community models in the family directory preview", () => {
    const model = indexModel("base", "Base model", 50);
    const community = communityRow({
      compositeFull: 0.6,
      confidence: "artifact-sha",
      detailPath: "/model/community-fine-tune",
      displayName: "Community fine-tune",
      familyLabel: "Fixture",
    });
    const html = renderToStaticMarkup(
      <FamilyDirectory
        communityRows={[community]}
        models={[model]}
        resolutionContext={EMPTY_FAMILY_RESOLUTION_CONTEXT}
      />,
    );

    expect(html).toContain("Community fine-tune");
    expect(html).toContain('href="/model/community-fine-tune/"');
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).toContain("2 models");
  });

  it("sorts resolved complete community runs into the measured family list", () => {
    // Given: a community fine-tune beats one measured maintainer model while a catalog shell awaits a run.
    const measured = indexModel("base", "Base model", 50);
    const awaiting = indexModel("catalog-shell", "Catalog shell", null);
    const summary = familySummaries([measured, awaiting])[0];
    if (summary === undefined) throw new Error("missing family summary fixture");
    const community = communityRow({
      compositeFull: 0.6,
      confidence: "artifact-sha",
      detailPath: "/model/community-fine-tune",
      displayName: "Community fine-tune",
      familyLabel: "Fixture",
    });

    // When: the family model table renders the shared measured population.
    const html = renderToStaticMarkup(
      <FamilyModelTable family="Fixture" models={summary.models} rows={[community]} />,
    );

    // Then: the community winner appears before measured maintainer data and catalog-only shells.
    const communityAt = html.indexOf("Community fine-tune");
    const measuredAt = html.indexOf("Base model");
    const awaitingAt = html.indexOf("Catalog shell");
    expect(communityAt).toBeGreaterThan(-1);
    expect(communityAt).toBeLessThan(measuredAt);
    expect(measuredAt).toBeLessThan(awaitingAt);
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).toContain("awaiting a complete run");
  });

  it("renders only unresolved complete rows in awaiting family assignment", () => {
    // Given: complete unresolved and declared-only rows sit beside a resolved row and an incomplete row.
    const unresolved = communityRow({ confidence: null, displayName: "Unresolved complete" });
    const declaredOnly = communityRow({
      confidence: "declared-family",
      displayName: "Declared only",
      familyLabel: "Fixture",
      submissionId: "ticket_declared_only",
    });
    const resolved = communityRow({
      confidence: "lineage",
      displayName: "Resolved complete",
      submissionId: "ticket_resolved",
    });
    const incomplete = communityRow({
      confidence: null,
      displayName: "Unresolved incomplete",
      headlineComplete: false,
      submissionId: "ticket_incomplete",
    });

    // When: the unassigned section renders.
    const html = renderToStaticMarkup(
      <AwaitingFamilyAssignment rows={[unresolved, declaredOnly, resolved, incomplete]} />,
    );

    // Then: only honest complete rows lacking authoritative assignment are visible.
    expect(html).toContain("Awaiting family assignment");
    expect(html).toContain("Unresolved complete");
    expect(html).toContain("Declared only");
    expect(html).not.toContain("Resolved complete");
    expect(html).not.toContain("Unresolved incomplete");
  });

  it("renders nothing when every complete row has authoritative family resolution", () => {
    // Given: the only complete row resolves through catalog lineage.
    const rows = [communityRow({ confidence: "lineage" })];

    // When: the unassigned section renders.
    const html = renderToStaticMarkup(<AwaitingFamilyAssignment rows={rows} />);

    // Then: no empty section consumes directory space.
    expect(html).toBe("");
  });
});

function indexModel(slug: string, label: string, point: number | null): IndexModel {
  return IndexModelSchema.parse({
    axes: point === null ? {} : Object.fromEntries(
      ["agentic", "coding", "instruction", "knowledge", "math", "tool_calling"].map((axis) => [axis, {
        hi: point + 1,
        lo: point - 1,
        n: 10,
        n_errors: 0,
        n_no_answer: 0,
        point,
        raw_accuracy: point / 100,
      }]),
    ),
    best_run_id: point === null ? null : `${slug}-run`,
    composite: point === null ? null : { hi: point + 1, lo: point - 1, point },
    composite_full: point === null ? null : { hi: point + 1, lo: point - 1, point },
    demo: false,
    est_cost_usd: null,
    family: "Fixture",
    kind: "maintainer_project",
    lane: point === null ? "answer-only" : "bounded-final-v2",
    model_label: label,
    n_runs: point === null ? 0 : 1,
    ranked: point !== null,
    replicated: false,
    score_status: point === null ? "missing" : "measured",
    slug,
    tier: point === null ? null : "standard",
    tokens_to_answer_median: point === null ? null : 128,
  });
}

function communityRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: "a".repeat(64),
    chainCatalogIds: [],
    compositeFull: 0.55,
    confidence: null,
    detailPath: null,
    displayName: "Community fixture",
    family: null,
    familyLabel: null,
    globalRank: null,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    partialComposite: 0.55,
    quantLabel: "Q4_K_M",
    rootCatalogId: null,
    rootSlug: null,
    submissionId: "ticket_unresolved",
    submitterDisplayName: "Ada",
    ...overrides,
  };
}
