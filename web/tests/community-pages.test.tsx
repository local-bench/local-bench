import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../components/app-shell";
import { CommunityDetail } from "../components/community-detail";
import { CommunityListing } from "../components/community-listing";
import { parseCommunityGroup } from "../lib/community-data";

const visibleArtifact = "a".repeat(64);
const visible = parseCommunityGroup({
  community_model_group_id: `community-group:${"1".repeat(32)}`,
  identity_label: "community-declared, identity-unverified",
  ranked: false,
  schema_version: "localbench.community_publication.v2",
  variants: [{
    artifact_sha256: visibleArtifact,
    display_name: "Qwythos-9B v2",
    lineage_enrichment: {
      artifact_sha256: visibleArtifact,
      association: {
        artifact_to_repo: "unverified",
        basis: "maintainer-associated",
        note: "Local GGUF association by maintainer knowledge; no matching repository blob.",
      },
      card_declared_edges: [
        {
          base: "empero-ai/Qwythos-9B-Claude-Mythos-5-1M",
          base_revision: "2".repeat(40),
          child: "empero-ai/Qwythos-9B-v2",
          child_revision: "1".repeat(40),
          source: "hf-model-card",
        },
        {
          base: "Qwen/Qwen3.5-9B",
          base_revision: "3".repeat(40),
          child: "empero-ai/Qwythos-9B-Claude-Mythos-5-1M",
          child_revision: "2".repeat(40),
          source: "hf-model-card",
        },
      ],
      repo: { id: "empero-ai/Qwythos-9B-v2", revision: "1".repeat(40) },
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

if (visible === null) throw new Error("visible community fixture must validate");

describe("community listing", () => {
  it("links the generic Community surface from site navigation", () => {
    const html = renderToStaticMarkup(
      <AppShell indexVersion="index-v3.0" suiteVersion="suite-v1" usesDemoData={false}>
        <div>content</div>
      </AppShell>,
    );
    expect(html).toContain('href="/community"');
    expect(html).toContain(">Community<");
  });

  it("renders visible post-suppression fixture data and omits the suppressed fixture", () => {
    const html = renderToStaticMarkup(<CommunityListing groups={[visible]} />);
    expect(html).toContain("Qwythos-9B v2");
    expect(html).toContain("Q4_K_M");
    expect(html).toContain("41.7%");
    expect(html).toContain("measured 75.0%");
    expect(html).toContain("missing 25.0%");
    expect(html).toContain("community-declared, identity-unverified");
    expect(html).toContain('href="/community/model/11111111111111111111111111111111"');
    expect(html).not.toContain("Suppressed fixture model");
  });
});

describe("community detail lineage", () => {
  it("renders the safe HF link and keeps association plus both card claims distinct", () => {
    const html = renderToStaticMarkup(<CommunityDetail group={visible} />);
    expect(html).toContain('href="https://huggingface.co/empero-ai/Qwythos-9B-v2"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('aria-label="Open Hugging Face repository: empero-ai/Qwythos-9B-v2"');
    expect(html).toContain("HF model-card-declared lineage (unverified)");
    expect(html).toContain("Layer 1 — artifact → repository association");
    expect(html).toContain("maintainer-associated and unproven");
    expect(html).toContain("Layer 2 — repository owner’s model-card claim");
    expect(html).toContain("Layer 3 — repository owner’s model-card claim");
    expect(html).toContain("1111111");
    expect(html).toContain("2222222");
    expect(html).toContain("3333333");
    expect(html).not.toContain("HF says");
  });

  it("renders a neutral state for unavailable data", () => {
    const html = renderToStaticMarkup(<CommunityDetail group={null} />);
    expect(html).toContain("Community data unavailable");
    expect(html).not.toContain("ticket_visible");
  });
});
