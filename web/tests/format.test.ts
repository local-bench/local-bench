import { describe, expect, it } from "vitest";
import { displayDelta, formatDuration, formatLatencySeconds, formatScore, formatSignedScore } from "../lib/format";

describe("formatScore", () => {
  it("clamps displayed scores to the zero-to-100 range", () => {
    expect(formatScore(100.4)).toBe("100.0");
    expect(formatScore(-0.4)).toBe("0.0");
  });

  it("preserves sign and magnitude for score deltas", () => {
    expect(formatSignedScore(-5.1)).toBe("-5.1");
    expect(formatSignedScore(5.1)).toBe("+5.1");
  });

  it("subtracts the displayed one-decimal operands", () => {
    expect(formatSignedScore(displayDelta(87.4, 83.4))).toBe("+4.0");
    expect(formatSignedScore(displayDelta(9.4, 8.3))).toBe("+1.1");
    expect(formatSignedScore(displayDelta(8.3, 9.4))).toBe("-1.1");
  });

});

describe("formatLatencySeconds", () => {
  it("formats sub-90s values as whole seconds with a tilde", () => {
    expect(formatLatencySeconds(13.4)).toBe("~13 s");
  });
  it("rolls up to minutes at or above 90s", () => {
    expect(formatLatencySeconds(132)).toBe("~2.2 min");
  });
  it("treats exactly 90s as the minutes boundary", () => {
    expect(formatLatencySeconds(90)).toBe("~1.5 min");
  });
  it("renders an em dash for null/undefined", () => {
    expect(formatLatencySeconds(null)).toBe("—");
    expect(formatLatencySeconds(undefined)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("renders an em dash for null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
  it("shows whole seconds under a minute", () => {
    expect(formatDuration(45)).toBe("45s");
  });
  it("rolls up to whole minutes under an hour", () => {
    expect(formatDuration(125)).toBe("2 min");
  });
  it("rolls up to hours with one decimal at or above an hour", () => {
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(20113.8)).toBe("5.6 h");
  });
});
