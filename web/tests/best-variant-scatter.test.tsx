import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BestVariantVramScatter } from "../components/best-variant-scatter";

describe("BestVariantVramScatter responsive legibility", () => {
  it("keeps chart labels legible on narrow viewports with an overflow cue", () => {
    const html = renderToStaticMarkup(<BestVariantVramScatter anchorRuns={[]} points={[]} />);

    expect(html).toContain("Swipe horizontally to inspect the full chart");
    expect(html).toContain("min-w-[820px]");
  });
});
