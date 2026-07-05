import { describe, expect, it } from "vitest";
import { AxisScoreSchema } from "../lib/schemas";

const AXIS_SCORE = {
  hi: 100,
  hi_raw: 1,
  lo: 100,
  lo_raw: 1,
  n: 141,
  n_errors: 0,
  n_no_answer: 0,
  point: 100,
  point_raw: 1,
  raw_accuracy: 1,
} as const;

describe("axis score schema", () => {
  it("accepts old axis scores without n_unscoreable", () => {
    const parsed = AxisScoreSchema.parse(AXIS_SCORE);

    expect(parsed.n_unscoreable).toBeUndefined();
  });

  it("preserves typed coding n_unscoreable", () => {
    const parsed = AxisScoreSchema.parse({ ...AXIS_SCORE, n_unscoreable: 7 });

    expect(parsed.n_unscoreable).toBe(7);
    expect(() => AxisScoreSchema.parse({ ...AXIS_SCORE, n_unscoreable: "7" })).toThrow();
  });
});
