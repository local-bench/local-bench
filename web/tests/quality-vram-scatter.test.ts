import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { QualityVramScatter, type QualityVramRun } from "../components/quality-vram-scatter";

function run(overrides: Partial<QualityVramRun>): QualityVramRun {
  return {
    run_id: "model__quant",
    quant_label: "Q4_K_M",
    composite: { point: 61.2, lo: 59.0, hi: 63.4 },
    axes: {},
    demo: false,
    vram_footprint_gb: 21.6,
    wall_time_seconds: 44_835,
    ...overrides,
  } as QualityVramRun;
}

function render(runs: readonly QualityVramRun[]): string {
  return renderToStaticMarkup(
    createElement(QualityVramScatter, {
      anchorRuns: [],
      ariaLabel: "test scatter",
      description: "test",
      runs,
      title: "test",
    }),
  );
}

describe("QualityVramScatter hover tooltip", () => {
  it("renders a CSS hover tooltip with measured bench time and RAM", () => {
    const html = render([run({})]);
    // The hover mechanics: enlarged hit target + group-hover reveal.
    expect(html).toContain('r="14"');
    expect(html).toContain("group-hover:opacity-100");
    // The content the tooltip carries.
    expect(html).toContain("benched in 12.5 h");
    expect(html).toContain("to run");
  });

  it("omits bench time for demo rows and rows without wall time", () => {
    const demoHtml = render([run({ demo: true })]);
    expect(demoHtml).not.toContain("benched in");

    const noWallHtml = render([run({ wall_time_seconds: null })]);
    expect(noWallHtml).not.toContain("benched in");
    expect(noWallHtml).toContain("to run");
  });
});
