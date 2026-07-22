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

describe("QualityVramScatter x-axis domain", () => {
  it("spans the default 4-64 GB frame for in-range data", () => {
    // Single point at 21.6 GB still gets the full shared frame: 4 GB left edge, 64 GB right.
    const html = render([run({})]);
    expect(html).toContain(">4 GB<");
    expect(html).toContain(">64 GB<");
    expect(html).toContain(">8GB<");
    expect(html).toContain(">64GB<");
    expect(html).not.toContain(">96GB<");
  });

  it("keeps identical bounds for pages with different in-range data", () => {
    const pageA = render([run({ vram_footprint_gb: 17.1 }), run({ vram_footprint_gb: 21.6 })]);
    const pageB = render([run({ vram_footprint_gb: 6.4 }), run({ vram_footprint_gb: 62.9 })]);
    for (const bound of ["4 GB", "64 GB"]) {
      expect(pageA).toContain(`>${bound}<`);
      expect(pageB).toContain(`>${bound}<`);
    }
    expect(pageB).not.toContain(">96GB<");
  });

  it("falls back to the walk-down bound when a point sits below 4 GB", () => {
    const html = render([run({ vram_footprint_gb: 2.5 })]);
    expect(html).toContain(">0 GB<");
    expect(html).toContain(">64 GB<");
  });

  it("keeps the empty-data placeholder domain", () => {
    const html = render([]);
    expect(html).toContain("No local runs include VRAM footprint yet.");
    expect(html).toContain(">0 GB<");
    expect(html).toContain(">8 GB<");
  });
});

describe("QualityVramScatter edge headroom above 64 GB", () => {
  it("walks up to the covering tier when a point exceeds 64 GB", () => {
    const html = render([run({ vram_footprint_gb: 70 })]);
    expect(html).toContain(">96GB<");
    expect(html).toContain(">96 GB<");
    expect(html).not.toContain(">128GB<");
  });

  it("steps to the next tier when an out-of-range point crowds the right bound", () => {
    // 94 GB against a 96 GB bound would render under the axis edge — expect a 128 GB bound.
    const html = render([run({ vram_footprint_gb: 94 })]);
    expect(html).toContain(">128GB<");
  });

  it("keeps the 64 GB bound when a point sits near it inside the frame", () => {
    const html = render([run({ vram_footprint_gb: 63 })]);
    expect(html).toContain(">64 GB<");
    expect(html).not.toContain(">96GB<");
  });
});

describe("QualityVramScatter point kinds", () => {
  it("renders project points with the same marker as catalog points, keeping the data attribute", () => {
    const html = render([run({ point_kind: "project" })]);
    const marker = /<circle data-point-kind="project"[^>]*/u.exec(html)?.[0];
    if (marker === undefined) throw new Error("missing project point marker");
    // Same solid accent dot as the catalog's own runs — no distinct project styling.
    expect(marker).toContain('r="6"');
    expect(marker).toContain("fill-bench-accent");
    expect(marker).not.toContain("fill-bench-panel");
  });

  it("keeps community points hollow and visually distinct", () => {
    const html = render([run({ point_kind: "community" })]);
    const marker = /<circle data-point-kind="community"[^>]*/u.exec(html)?.[0];
    if (marker === undefined) throw new Error("missing community point marker");
    expect(marker).toContain('r="7"');
    expect(marker).toContain("stroke-bench-better");
    expect(marker).toContain("fill-bench-panel");
  });
});

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

describe("QualityVramScatter point labels", () => {
  it("keeps chart labels legible on narrow viewports with an overflow cue", () => {
    const html = render([run({})]);

    expect(html).toContain("Swipe horizontally to inspect the full chart");
    expect(html).toContain("min-w-[760px]");
  });

  it("separates labels for nearby family points", () => {
    const html = render([
      run({ point_label: "Q4_K_M", vram_footprint_gb: 19.5, composite: { point: 44.4, lo: 41.7, hi: 47.1 } }),
      run({ point_label: "Qwopus 3.6 27B v2 MTP · Q4_K_M", vram_footprint_gb: 18.1, composite: { point: 43.3, lo: 40.5, hi: 46.1 } }),
    ]);
    const baseY = labelY(html, "Q4_K_M");
    const fineTuneY = labelY(html, "Qwopus 3.6 27B v2 MTP · Q4_K_M");

    expect(Math.abs(baseY - fineTuneY)).toBeGreaterThanOrEqual(14);
  });
});

function labelY(html: string, label: string): number {
  const match = new RegExp(`<text[^>]+y="([0-9.]+)"[^>]*>${label}</text>`, "u").exec(html);
  if (match?.[1] === undefined) throw new Error(`missing point label ${label}`);
  return Number(match[1]);
}
