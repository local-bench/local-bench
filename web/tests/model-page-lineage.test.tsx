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

  it("omits the header fine-tune chip for base models", async () => {
    const html = await renderModel("qwen3-6-27b");
    const headerHtml = html.slice(0, html.indexOf("This model"));
    expect(headerHtml).not.toContain("Fine-tune of");
  });

  it("renders a base model's measured fine-tune comparison with a real delta", async () => {
    // Both halves of the Qwopus/Qwen3.6-27B pair landed ranked bounded-final-v2 rows
    // on 2026-07-08, so the strip now shows the measured comparison instead of the
    // honest-missing placeholder this test asserted while only legacy runs existed.
    const html = await renderModel("qwen3-6-27b");
    expect(html).toContain("vs fine-tunes");
    expect(html).toContain("Qwopus 3.6 27B v2 MTP");
    expect(html).toContain("composite -");
    expect(html).toContain("compare to base");
    // Other catalog derivatives (e.g. the v1 preview) may still carry the honest
    // missing placeholder; only the measured v2 pair must show a real delta.
  });

  it("renders derivative vs-base missing states without fake numbers", async () => {
    const html = await renderModel("phi-4-reasoning");
    expect(html).toContain("vs base");
    expect(html).toContain("Phi 4 Reasoning");
    expect(html).toContain("base not yet benchmarked");
    expect(html).toContain("fine-tune not yet benchmarked");
  });

  it("links retired-lane receipts on legacy-only model pages", async () => {
    const html = await renderModel("gemma-4-31b-it");
    expect(html).toContain("Retired-lane diagnostic receipts");
    expect(html).toContain('href="/run/gemma-4-31b-it__ladder-gemma4-31b-Q4_K_M"');
    expect(html).toContain("Q4_K_M");
    expect(html).toContain("diagnostic receipt (retired lane)");
    expect(html).toContain("kept off this chart because the score uses a retired scale");
    expect(html).not.toContain("They appear below as diagnostics");
  });
});
