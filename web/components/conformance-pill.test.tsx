import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ConformancePill } from "./conformance-pill";
import type { ConformanceGate } from "@/lib/schemas";

function gate(band: ConformanceGate["band"], overrides: Partial<ConformanceGate> = {}): ConformanceGate {
  return {
    id: "tc_json_v1",
    label: "JSON tool-call gate",
    band,
    pass_rate: { point: 82, lo: 78, hi: 86 },
    invalid_json_rate: 2.3,
    n_items: 330,
    threshold_version: "tc_json_v1",
    band_reasons: [],
    ...overrides,
  };
}

describe("ConformancePill", () => {
  it.each(["green", "amber", "red"] as const)("renders the %s gate band from the artifact", (band) => {
    // Given: the board artifact has already computed the gate band.
    const html = renderToStaticMarkup(<ConformancePill gate={gate(band)} />);

    // Then: the pill renders that band and the CI without recomputing thresholds.
    expect(html).toContain(`GATE ${band.toUpperCase()}`);
    expect(html).toContain("82.0%");
    expect(html).toContain("[78.0-86.0]");
  });

  it("renders a grey not measured state when no gate is present", () => {
    // Given: the board omitted the gate for an unmeasured row.
    const html = renderToStaticMarkup(<ConformancePill gate={undefined} />);

    // Then: missing data is neutral, not amber or red.
    expect(html).toContain("not measured");
    expect(html).not.toContain("GATE");
  });

  it("renders the board-provided red band even for a high pass rate", () => {
    // Given: invalid JSON forced the scorer-side gate red despite an 82% pass rate.
    const html = renderToStaticMarkup(
      <ConformancePill gate={gate("red", { invalid_json_rate: 18, band_reasons: ["invalid_json>15"] })} showReason />,
    );

    // Then: the web layer displays the artifact band and reason; it does not recolor by pass rate.
    expect(html).toContain("GATE RED");
    expect(html).toContain("82.0%");
    expect(html).toContain("invalid JSON 18.0%");
  });
});
