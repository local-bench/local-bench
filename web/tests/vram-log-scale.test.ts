import { describe, expect, it } from "vitest";
import { getVramLogDomain, scaleVramLogX, VRAM_LOG_LABEL_TICKS } from "../lib/vram-log-scale";

const CHART = { left: 64, right: 188, width: 920 } as const;

describe("vram log scale", () => {
  it("keeps the sub-192 GB local range expanded while compacting higher tiers", () => {
    const domain = getVramLogDomain([]);
    const left = scaleVramLogX(2, domain, CHART);
    const x16 = scaleVramLogX(16, domain, CHART);
    const x32 = scaleVramLogX(32, domain, CHART);
    const x128 = scaleVramLogX(128, domain, CHART);
    const x192 = scaleVramLogX(192, domain, CHART);
    const x512 = scaleVramLogX(512, domain, CHART);

    expect(domain).toEqual({ min: 2, max: 512 });
    expect((x192 - left) / (x512 - left)).toBeGreaterThan(0.8);
    expect(x32 - x16).toBeGreaterThan(x192 - x128);
  });

  it("extends beyond 512 GB only when a measured point needs it", () => {
    const domain = getVramLogDomain([12, 768]);

    expect(domain.min).toBe(2);
    expect(domain.max).toBeGreaterThan(768);
  });

  it("labels the local-card range densely and summarizes the high-VRAM tail", () => {
    expect(VRAM_LOG_LABEL_TICKS).toContain(192);
    expect(VRAM_LOG_LABEL_TICKS).not.toContain(256);
    expect(VRAM_LOG_LABEL_TICKS).not.toContain(384);
    expect(VRAM_LOG_LABEL_TICKS).toContain(512);
  });
});
