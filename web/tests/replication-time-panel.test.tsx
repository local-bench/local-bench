import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { ReplicationTimePanel } from "../components/replication-time-panel";
import type { BestVariantPoint } from "../lib/best-variant";

function point(overrides: Partial<BestVariantPoint>): BestVariantPoint {
  return {
    modelSlug: "model",
    modelLabel: "Model",
    family: "gemma4",
    runId: "model__run",
    quantLabel: "Q4_K_M",
    score: { point: 50, lo: 45, hi: 55 },
    axes: {},
    tokS: 60,
    latencySMedian: null,
    wallTimeSeconds: 3600,
    effectiveVramGb: 20,
    nRuns: 1,
    isFrontier: false,
    ...overrides,
  } as BestVariantPoint;
}

// The five live season-2 rows (corrected 31b timing): rank order and time order are
// nearly inverted, which is exactly what the panel must NOT re-sort by.
function livePoints(): BestVariantPoint[] {
  return [
    point({ modelSlug: "gemma-4-31b-it", modelLabel: "Gemma 4 31B IT", runId: "a", score: { point: 55.49, lo: 52.7, hi: 58.2 }, wallTimeSeconds: 100_257, tokS: 48.4 }),
    point({ modelSlug: "qwen3-6-27b", modelLabel: "Qwen3.6 27B", runId: "b", score: { point: 46.38, lo: 44.2, hi: 48.5 }, wallTimeSeconds: 85_346, tokS: 69.4 }),
    point({ modelSlug: "qwopus3-6-27b-v2-mtp", modelLabel: "Qwopus 3.6 27B v2 MTP", runId: "c", score: { point: 45.12, lo: 43.0, hi: 47.2 }, wallTimeSeconds: 85_137, tokS: 63.8 }),
    point({ modelSlug: "qwen3-6-35b-a3b", modelLabel: "Qwen3.6 35B A3B", runId: "d", score: { point: 44.14, lo: 42.0, hi: 46.2 }, wallTimeSeconds: 33_278, tokS: 190.8 }),
    point({ modelSlug: "gemma-4-12b-it", modelLabel: "Gemma 4 12B IT", runId: "e", score: { point: 44.01, lo: 41.9, hi: 46.1 }, wallTimeSeconds: 61_750, tokS: 137.1 }),
  ];
}

function render(points: readonly BestVariantPoint[]): string {
  return renderToStaticMarkup(createElement(ReplicationTimePanel, { points }));
}

describe("ReplicationTimePanel", () => {
  it("orders rows by leaderboard rank, never by time", () => {
    const html = render(livePoints());
    const order = ["Gemma 4 31B IT", "Qwen3.6 27B", "Qwopus 3.6 27B v2 MTP", "Qwen3.6 35B A3B", "Gemma 4 12B IT"];
    const positions = order.map((label) => html.indexOf(label));
    expect(positions.every((index) => index >= 0)).toBe(true);
    expect([...positions].sort((left, right) => left - right)).toEqual(positions);
    expect(html).toContain("#1");
    expect(html).toContain("#5");
  });

  it("keeps the misread guard in visible text and pins the season scope", () => {
    const html = render(livePoints());
    expect(html).toContain("this is not an inference-speed ranking.");
    expect(html).toContain("Season 2 · index v4.1 · 1,457 items · RTX 5090 reference rig");
    expect(html).toContain("Estimate a full-suite run");
  });

  it("states full coverage as a census", () => {
    expect(render(livePoints())).toContain("5 of 5 ranked best variants have verified timing");
  });

  it("marks only the shortest run with the flame, run-oriented copy", () => {
    const html = render(livePoints());
    expect(html.split("\u{1F525}").length - 1).toBe(1);
    const flameAt = html.indexOf("\u{1F525}");
    const a3bAt = html.indexOf("Qwen3.6 35B A3B");
    const nextRowAt = html.indexOf("Gemma 4 12B IT");
    expect(flameAt).toBeGreaterThan(a3bAt);
    expect(flameAt).toBeLessThan(nextRowAt);
    expect(html).toContain("Shortest full-suite run this season");
    expect(html).not.toContain("fastest model");
  });

  it("scales the axis to the next five-hour bound", () => {
    const html = render(livePoints());
    expect(html).toContain("30 h");
  });

  it("lists an untimed row without a bar and discloses structural missingness", () => {
    const points = [...livePoints(), point({ modelSlug: "community-x", modelLabel: "Community X", runId: "f", score: { point: 43.5, lo: 41.0, hi: 45.5 }, wallTimeSeconds: null })];
    const html = render(points);
    expect(html).toContain("5 of 6 ranked best variants have verified timing");
    expect(html).toContain("Community X");
    expect(html).toContain("Timing unavailable in the board record for 1 ranked variant.");
    expect(html).toContain("Season 2 community submissions do not ingest timing fields.");
  });

  it("gates the comparative chart when fewer than four rows are timed", () => {
    const points = livePoints().map((entry, index) => (index < 3 ? entry : { ...entry, wallTimeSeconds: null }));
    const html = render(points);
    expect(html).toContain("not yet enough comparable timings");
    expect(html).not.toContain("\u{1F525}");
  });

  it("gates the comparative chart when the number-one row has no timing", () => {
    const points = livePoints().map((entry, index) => (index === 0 ? { ...entry, wallTimeSeconds: null } : entry));
    const html = render(points);
    expect(html).toContain("not yet enough comparable timings");
  });

  it("caps the landing card at eight rows and hands off to the leaderboard", () => {
    const points = Array.from({ length: 9 }, (_, index) =>
      point({
        modelSlug: `model-${index}`,
        modelLabel: `Model ${index}`,
        runId: `run-${index}`,
        score: { point: 60 - index, lo: 58 - index, hi: 62 - index },
        wallTimeSeconds: 40_000 + index * 1_000,
      }),
    );
    const html = render(points);
    expect(html).toContain("Showing 8 of 9 ranked models");
    expect(html).toContain("view all timings in the leaderboard");
    expect(html).not.toContain("Model 8");
  });

  it("renders the seasonal empty state when nothing is ranked", () => {
    const html = render([]);
    expect(html).toContain("No comparable full-suite timings have been published for this season yet.");
  });
});
