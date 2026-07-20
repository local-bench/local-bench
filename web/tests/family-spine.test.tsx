import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogOnlyNotice } from "../components/catalog-only-notice";
import type { CommunityBoardRow } from "../lib/community-data";
import { communityBaseModelSlugs } from "../lib/data";
import type { CatalogModel } from "../lib/schemas";

const communityRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  compositeFull: null,
  detailPath: "/model/base-model",
  displayName: "Fixture derivative",
  family: "Fixture",
  globalRank: null,
  headlineComplete: false,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: null,
  lineage: {
    artifact_sha256: "a".repeat(64),
    association: {
      artifact_to_repo: "unverified",
      basis: "maintainer-associated",
      note: "Synthetic family-spine fixture.",
    },
    card_declared_edges: [{
      base: "Vendor/Base-Model",
      base_revision: null,
      child: "Vendor/Derivative",
      child_revision: "c".repeat(40),
      source: "hf-model-card",
    }],
    repo: { id: "Vendor/Derivative", revision: "c".repeat(40) },
    resolution: { resolved_at: "2026-07-18T01:00:00Z", status: "complete" },
  },
  measuredHeadlineWeight: 0.75,
  missingHeadlineWeight: 0.25,
  partialComposite: 0.5,
  quantLabel: "Q4_K_M",
  ranked: false,
  submissionId: "ticket_fixture",
};

const catalog: readonly CatalogModel[] = [{
  display_name: "Base Model",
  id: "Vendor/Base-Model",
  model_kind: "base",
  quants: [],
  slug: "base-model",
}];

describe("community family spine", () => {
  it("adds catalog slugs for baked lineage bases that lack an index route", () => {
    expect(communityBaseModelSlugs([communityRow], catalog, new Set())).toEqual(["base-model"]);
    expect(communityBaseModelSlugs([communityRow], catalog, new Set(["base-model"]))).toEqual([]);
  });

  it("adds the artifact owner's catalog route together with its transitive base", () => {
    const derivative: CatalogModel = {
      base_model: "Vendor/Base-Model",
      display_name: "Derivative",
      id: "Vendor/Derivative",
      model_kind: "finetune",
      quants: [{ file_sha256: "a".repeat(64), label: "Q4_K_M" }],
      slug: "derivative",
    };

    expect(communityBaseModelSlugs([communityRow], [...catalog, derivative], new Set()))
      .toEqual(["base-model", "derivative"]);
  });

  it("renders an honest catalog-only note and queue state", () => {
    const queued = renderToStaticMarkup(<CatalogOnlyNotice queued />);
    const unqueued = renderToStaticMarkup(<CatalogOnlyNotice queued={false} />);

    expect(queued).toContain("Base not yet benchmarked");
    expect(queued).toContain("Queued");
    expect(unqueued).not.toContain("Queued");
  });
});
