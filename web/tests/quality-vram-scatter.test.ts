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
  it("snaps the domain outward to canonical GPU-tier breakpoints", () => {
    // Single point at 21.6 GB → domain [16, 24], so both boundary tier lines render.
    const html = render([run({})]);
    expect(html).toContain(">16GB<");
    expect(html).toContain(">24GB<");
    expect(html).not.toContain(">32GB<");
  });

  it("keeps identical bounds for pages whose data spans the same tiers", () => {
    const pageA = render([run({ vram_footprint_gb: 17.1 }), run({ vram_footprint_gb: 21.6 })]);
    const pageB = render([run({ vram_footprint_gb: 16.4 }), run({ vram_footprint_gb: 23.9 })]);
    for (const tier of ["16GB", "24GB"]) {
      expect(pageA).toContain(`>${tier}<`);
      expect(pageB).toContain(`>${tier}<`);
    }
  });

  it("widens a degenerate domain when every point sits on one breakpoint", () => {
    const html = render([run({ vram_footprint_gb: 16 })]);
    expect(html).toContain(">16GB<");
    expect(html).toContain(">24GB<");
  });
});

describe("QualityVramScatter edge headroom", () => {
  it("extends the domain to the next tier when a point sits near the right bound", () => {
    // 31.8 GB against a 32 GB bound would render under the axis edge — expect a 48 GB bound.
    const html = render([run({ vram_footprint_gb: 21.6 }), run({ vram_footprint_gb: 31.8 })]);
    expect(html).toContain(">32GB<");
    expect(html).toContain(">48GB<");
  });

  it("keeps the snapped bound when points sit comfortably inside it", () => {
    const html = render([run({ vram_footprint_gb: 17.1 }), run({ vram_footprint_gb: 21.6 })]);
    expect(html).toContain(">24GB<");
    expect(html).not.toContain(">32GB<");
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
