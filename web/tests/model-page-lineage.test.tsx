import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ModelPage from "../app/model/[slug]/page";

async function renderModel(slug: string): Promise<string> {
  return renderToStaticMarkup(await ModelPage({ params: Promise.resolve({ slug }) }));
}

describe("ModelPage lineage chip", () => {
  it("links the fine-tune chip when the base has a board row", async () => {
    const html = await renderModel("phi-4-reasoning");
    expect(html).toContain('href="/model/phi-4"');
    expect(html).toContain("Fine-tune of Phi 4");
  });

  it("renders unlinked lineage text when the base has no board row", async () => {
    const html = await renderModel("qwen3-0-6b");
    expect(html).toContain("Fine-tune of Qwen/Qwen3-0.6B-Base");
    expect(html).not.toContain('href="/model/Qwen/Qwen3-0.6B-Base"');
  });

  it("omits the fine-tune chip for base models", async () => {
    const html = await renderModel("qwen3-6-27b");
    expect(html).not.toContain("Fine-tune of");
  });
});
