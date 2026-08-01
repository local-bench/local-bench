import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CommunityVariantTableRow } from "../components/model-variant-community-row";
import { ExecutionProfileBadge } from "../components/execution-profile-badge";
import type { CommunityArtifactDetail } from "../lib/community-artifact-details";
import type { CommunityBoardRow } from "../lib/community-data";

describe("CommunityVariantTableRow", () => {
  it("links the Run column to the encoded public submission receipt", () => {
    // Given a live row whose model detail path is unrelated to its submission receipt.
    const html = renderCommunityRow({
      row: communityRow({
        detailPath: "/model/qwen3-6-27b/",
        submissionId: "ticket_live/with spaces",
      }),
    });
    const cells = rowCells(html);

    // When the table row renders, then Run always targets the submission record.
    expect(cells.at(-1)).toContain('href="/submission/?id=ticket_live%2Fwith%20spaces"');
    expect(cells.at(-1)).toContain(">receipt</a>");
    expect(cells.at(-1)).not.toContain("/model/qwen3-6-27b/");
    expect(cells.at(-1)).not.toContain(">detail</a>");
  });

  it("leads with the quant and omits the circular model link for an own-model row", () => {
    // Given a live row whose sha belongs to the model page being rendered.
    const html = renderCommunityRow({
      row: communityRow({
        detailPath: "/model/qwen3-6-27b/",
        displayName: "Qwen3.6 27B Q6_K",
        quantLabel: "Q6_K",
      }),
    });
    const variantCell = rowCells(html)[1] ?? "";

    // Then the quant is primary and the page's own model name is not a circular link.
    expect(variantCell).toContain('class="font-mono font-semibold text-bench-text">Q6_K</span>');
    expect(variantCell).not.toContain('href="/model/qwen3-6-27b/"');
    expect(variantCell).not.toContain(">Qwen3.6 27B</a>");
  });

  it("keeps the lineage, model link, and quant treatment for a guest row", () => {
    // Given a live row from a fine-tune shown on its base model's page.
    const html = renderCommunityRow({
      relation: "family-finetune",
      row: communityRow({
        detailPath: "/model/community-tune/",
        displayName: "Community Tune",
      }),
    });
    const variantCell = rowCells(html)[1] ?? "";

    // Then the other model's identity remains visible and linked.
    expect(variantCell).toContain(">fine-tune</span>");
    expect(variantCell).toContain('href="/model/community-tune/"');
    expect(variantCell).toContain(">Qwen3.6 27B</a>");
    expect(variantCell).toContain(">Q6_K</span>");
  });

  it("shows the server-derived execution profile badge", () => {
    // Given: a published row with a structured execution profile.
    const html = renderCommunityRow({
      row: communityRow({
        executionProfile: { id: "generic_think_tags_8192_v1" },
      }),
    });

    // When/Then: the row discloses the profile without exposing internal template detail.
    expect(html).toContain("execution profile: generic_think_tags_8192_v1");
    expect(html).toContain(">8k</span>");
    expect(html).toContain("8k static reasoning");
  });

  it("labels complete v2 profiles as 32k with a human-readable budget summary", () => {
    const html = renderToStaticMarkup(createElement(ExecutionProfileBadge, {
      profile: currentProfile(),
    }));

    expect(html).toContain(">32k</span>");
    expect(html).toContain("32k reasoning · 16k final · 64k context");
    expect(html).toContain("execution profile: generic_think_tags_32768_v1");
  });

  it("labels rich v1 and id-only profiles as 8k with readable summaries", () => {
    const rich = renderToStaticMarkup(createElement(ExecutionProfileBadge, {
      profile: {
        ...legacyProfile(),
        semantic_sha256: "a6bf105b73ad3f8120751151707ce2d15f4b20617a64250679a0dce8977d9bb3",
        server_context_tokens: 32768,
        static_final_tokens: 8192,
        static_think_tokens: 8192,
      },
    }));
    const idOnly = renderToStaticMarkup(createElement(ExecutionProfileBadge, {
      profile: { id: "answer_only_8192_v1" },
    }));

    expect(rich).toContain(">8k</span>");
    expect(rich).toContain("8k reasoning · 8k final · 32k context");
    expect(idOnly).toContain(">8k</span>");
    expect(idOnly).toContain("8k answer-only");
  });

  it("links a rerun row to the receipt it supersedes", () => {
    // Given: a rerun with a server-maintained supersedes relation.
    const priorSubmissionId = "ticket_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const html = renderCommunityRow({
      row: communityRow({ supersedesSubmissionId: priorSubmissionId }),
    });

    // When/Then: the row keeps the prior immutable receipt reachable.
    expect(html).toContain(`href="/submission/?id=${priorSubmissionId}"`);
    expect(html).toContain(`title="supersedes ${priorSubmissionId}"`);
  });
});

function legacyProfile() {
  return {
    answer_stops: ["</think>"],
    chat_template_kwargs: { enable_thinking: true },
    id: "generic_think_tags_8192_v1",
    prompt_renderer_engine: "llama.cpp.apply-template",
    runtime_probe_passed: true,
    selection_policy_id: "gguf-effective-template-v1",
    selection_reason: "gguf_template_thinking_markers",
    template_sha256: "f".repeat(64),
    template_source: "gguf-default",
  } as const;
}

function currentProfile() {
  return {
    ...legacyProfile(),
    agentic_context_tokens: 32768,
    agentic_max_generated_tokens_per_task: 65536,
    agentic_max_output_tokens_per_turn: 1024,
    agentic_max_turns: 40,
    context_extension_policy: "none",
    context_fit_policy: "exact-or-fail",
    id: "generic_think_tags_32768_v1",
    kv_cache_k_dtype: "f16",
    kv_cache_v_dtype: "f16",
    per_task_timeout_s: 3000,
    schema_version: "localbench.execution_profile.v2",
    semantic_sha256: "e02ef5b5e75f19ca39d8949711bdd2d6517d1ce9267012ac923abffb94fbf058",
    server_context_tokens: 65536,
    static_final_tokens: 16384,
    static_max_generated_tokens: 49152,
    static_think_tokens: 32768,
  } as const;
}

function renderCommunityRow({
  relation = null,
  row,
}: {
  readonly relation?: "family-finetune" | "base-model" | null;
  readonly row: CommunityBoardRow;
}): string {
  return renderToStaticMarkup(createElement(CommunityVariantTableRow, {
    artifactDetail: artifactDetail(),
    axisKeys: [],
    hasPerf: false,
    rank: 1,
    relation,
    row,
  }));
}

function artifactDetail(): CommunityArtifactDetail {
  return {
    artifactSha256: "a".repeat(64),
    fileGb: 22.9,
    modelLabel: "Qwen3.6 27B",
    quantLabel: "Q6_K",
    slug: "qwen3-6-27b",
    vramGb8k: 25.2,
  };
}

function communityRow(overrides: Partial<CommunityBoardRow> = {}): CommunityBoardRow {
  return {
    artifactSha256: "a".repeat(64),
    axes: {},
    compositeFull: 0.96,
    detailPath: "/model/qwen3-6-27b/",
    displayName: "Qwen3.6 27B Q6_K",
    family: "Qwen3.6",
    globalRank: 1,
    headlineComplete: true,
    identityLabel: "community-declared, identity-unverified",
    indexVersion: "index-v4.2",
    lineage: undefined,
    measuredHeadlineWeight: 1,
    missingHeadlineWeight: 0,
    origin: "community",
    partialComposite: null,
    quantLabel: "Q6_K",
    ranked: true,
    submissionId: "ticket_d65715b80b6f4e2fa54d63ca7ce5273b",
    ...overrides,
  };
}

function rowCells(html: string): readonly string[] {
  return [...html.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((match) => match[1] ?? "");
}
