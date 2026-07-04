import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MeasuredDiagnostics } from "../components/measured-diagnostics";
import { getIndexData } from "../lib/data";
import { splitLeaderboard } from "../lib/leaderboard";

describe("measured diagnostics", () => {
  it("renders measured rows left out of ranked and static boards", async () => {
    // Given the leaderboard split has ranked/static boards plus measured diagnostic leftovers.
    const index = await getIndexData();
    const { ranked, staticComposite } = splitLeaderboard(index.models);
    const displayedSlugs = new Set([...ranked, ...staticComposite].map((model) => model.slug));
    const diagnostics = index.models.filter(
      (model) => model.score_status === "measured" && !displayedSlugs.has(model.slug),
    );

    // When the diagnostics component renders the leftover measured rows.
    const html = renderToStaticMarkup(createElement(MeasuredDiagnostics, { models: diagnostics }));

    // Then it gives each orphaned measured row an inbound model link.
    expect(diagnostics).toHaveLength(7);
    expect(html).toContain("Measured diagnostics");
    expect(html).toContain("Diagnostic only — never rank-comparable.");
    expect(html).toContain('href="/model/gemma-4-31b-it"');
    expect(html).toContain('href="/model/qwen3-coder-next"');
  });

  it("renders nothing when there are no diagnostic rows", () => {
    expect(renderToStaticMarkup(createElement(MeasuredDiagnostics, { models: [] }))).toBe("");
  });
});
