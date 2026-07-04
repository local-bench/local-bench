import { describe, expect, it } from "vitest";
import { formatDuration, formatLatencySeconds } from "../lib/format";

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
