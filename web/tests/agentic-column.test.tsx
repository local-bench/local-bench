import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgenticCell, formatAgenticPct } from "../components/agentic-column";
import type { AgenticModel } from "../lib/schemas";

const overRangeModel: AgenticModel = {
  asr: 1.004,
  asr_pct: 100.4,
  asr_series: [1.004],
  label: "Fixture",
  n_runs: 1,
  n_tasks: 96,
};

describe("agentic column display boundaries", () => {
  it("clamps percentage text and its bar to 100 percent", () => {
    const html = renderToStaticMarkup(<AgenticCell model={overRangeModel} />);

    expect(formatAgenticPct(overRangeModel)).toBe("100.0%");
    expect(html).toContain("100.0%");
    expect(html).not.toContain("100.4%");
    expect(html).toContain("width:100%");
  });

  it("uses an em dash for an absent agentic measurement", () => {
    const html = renderToStaticMarkup(<AgenticCell model={undefined} />);

    expect(formatAgenticPct(undefined)).toBe("—");
    expect(html).toContain(">—</div>");
    expect(html).not.toContain(">-</div>");
  });
});
