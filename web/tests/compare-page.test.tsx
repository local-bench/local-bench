import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ComparePage from "../app/compare/page";

describe("ComparePage presets", () => {
  it("renders as a static compare page while the client picker owns URL presets", async () => {
    const html = renderToStaticMarkup(await ComparePage());

    expect(html).toContain("Compare model configs");
    expect(html).toContain("Left config");
    expect(html).toContain("Right config");
    expect(html).toContain('href="/methodology#serving-engine-lanes"');
    expect(html).toContain('title="A lane fixes the serving engine and benchmark protocol used for a comparable run"');
  });
});
