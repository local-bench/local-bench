import { describe, expect, it } from "vitest";
import { getRankedQualityRows } from "../lib/quality-bars";
import type { AnchorReference } from "../lib/data";
import type { RigMatchCandidate } from "../lib/rig-match";

const ANCHORS = [
  { model_label: "GPT-5.5", run_id: "gpt-5-5__anchor", composite: { point: 92, lo: 91, hi: 93 } },
  { model_label: "Gemini 3.1 Pro", run_id: "gemini-3-1-pro__anchor", composite: { point: 94, lo: 93, hi: 95 } },
] as const satisfies readonly AnchorReference[];

const LOCAL_RUNS = [
  candidate("model-a-q3", "Model A", "model-a", "Q3_K_M", 68, 12, 24),
  candidate("model-a-q4", "Model A", "model-a", "Q4_K_M", 72, 19, 18),
  candidate("model-b-q5", "Model B", "model-b", "Q5_K_M", 81, 48, 9),
  candidate("anchor-row", "GPT-5.5", "gpt-5-5", null, 92, null, null, "anchor"),
] as const satisfies readonly RigMatchCandidate[];

describe("quality bar chart rows", () => {
  it("separates anchors above one representative local quant per model", () => {
    // Given anchor references and local model x quant rows.
    const anchors = ANCHORS;
    const localRuns = LOCAL_RUNS;

    // When rows are prepared for the ranked quality bars.
    const rows = getRankedQualityRows({ anchorRuns: anchors, runs: localRuns });

    // Then anchors sort by score first, and locals sort by their best representative quant.
    expect(rows.anchors.map((row) => [row.modelLabel, row.score, row.barWidthPercent])).toEqual([
      ["Gemini 3.1 Pro", 94, 94],
      ["GPT-5.5", 92, 92],
    ]);
    expect(rows.locals.map((row) => [row.modelLabel, row.quantLabel, row.score, row.vramFootprintGb])).toEqual([
      ["Model B", "Q5_K_M", 81, 48],
      ["Model A", "Q4_K_M", 72, 19],
    ]);
  });
});

function candidate(
  runId: string,
  modelLabel: string,
  modelSlug: string,
  quantLabel: string | null,
  point: number,
  vramFootprintGb: number | null,
  tokS: number | null,
  kind: "community" | "anchor" = "community",
): RigMatchCandidate {
  return {
    demo: kind === "community",
    family: modelLabel,
    kind,
    lane: kind === "community" ? "answer-only" : "api-uncapped",
    modelLabel,
    modelSlug,
    nItems: 252,
    nRuns: 1,
    quantLabel,
    runId,
    score: { point, lo: point - 2, hi: point + 2 },
    scoreStatus: "measured",
    tokS,
    vramFootprintGb,
    vramRequiredGb8k: null,
  };
}
