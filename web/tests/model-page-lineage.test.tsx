import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ModelPage from "../app/model/[slug]/page";

async function renderModel(slug: string): Promise<string> {
  return renderToStaticMarkup(await ModelPage({ params: Promise.resolve({ slug }) }));
}

function variantBoardHtml(html: string): string {
  const start = html.indexOf('data-testid="model-variant-board"');
  const end = html.indexOf("<section", start + 1);
  if (start === -1 || end === -1) {
    throw new Error("Expected model variant board before another page section");
  }
  return html.slice(start, end);
}

describe("ModelPage lineage chip", () => {
  it("links the fine-tune chip when the base has a board row", async () => {
    const html = await renderModel("phi-4-reasoning");
    expect(html).toContain('href="/model/phi-4/"');
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

  it("withholds a measured fine-tune delta until both execution profiles are known", async () => {
    const html = await renderModel("qwen3-6-27b");
    expect(html).toContain("vs fine-tunes");
    expect(html).toContain("Qwopus 3.6 27B v2 MTP");
    expect(html).toContain("composite n/a");
    expect(html).toContain("different execution profiles");
    expect(html).toContain("compare to base");
  });

  it("plots a base model's current-lane measured family fine-tunes with receipt links", async () => {
    const html = await renderModel("qwen3-6-27b");

    expect(html).toContain("Family fine-tunes");
    expect(html).toContain('data-point-kind="family-finetune"');
    expect(html).toContain('href="/run/qwopus3-6-27b-v2-mtp__qwopus3-6-27b-v2-mtp-q4km-s2v5/"');
    expect(html).toContain("Qwopus 3.6 27B v2 MTP");
  });

  it("lists a base model's measured fine-tune rows in Variant profiles with lineage and model links", async () => {
    const html = variantBoardHtml(await renderModel("qwen3-6-27b"));

    expect(html).toContain("fine-tune");
    expect(html).toContain('href="/model/qwopus3-6-27b-v2-mtp/"');
    expect(html).toContain("Qwopus 3.6 27B v2 MTP");
    expect(html).toContain('href="/run/qwopus3-6-27b-v2-mtp__qwopus3-6-27b-v2-mtp-q4km-s2v5/"');
  });

  it("plots a fine-tune page's base model current-lane measured runs with receipt links", async () => {
    const html = await renderModel("qwopus3-6-27b-v2-mtp");

    expect(html).toContain("Base model");
    expect(html).toContain('data-point-kind="base-model"');
    expect(html).toContain('href="/run/qwen3-6-27b__qwen3-6-27b-q4km-s2v5/"');
    expect(html).toContain("Qwen3.6 27B");
  });

  it("lists a fine-tune page's measured base rows in Variant profiles with lineage and model links", async () => {
    const html = variantBoardHtml(await renderModel("qwopus3-6-27b-v2-mtp"));

    expect(html).toContain("base model");
    expect(html).toContain('href="/model/qwen3-6-27b/"');
    expect(html).toContain("Qwen3.6 27B");
    expect(html).toContain('href="/run/qwen3-6-27b__qwen3-6-27b-q4km-s2v5/"');
  });

  it("renders derivative vs-base missing states without fake numbers", async () => {
    const html = await renderModel("phi-4-reasoning");
    expect(html).toContain("vs base");
    expect(html).toContain("Phi 4 Reasoning");
    expect(html).toContain("base not yet benchmarked");
    expect(html).toContain("fine-tune not yet benchmarked");
  });

  it("keeps retired-lane runs off a model page after its season-2 row lands", async () => {
    const html = await renderModel("gemma-4-31b-it");
    expect(html).not.toContain("Retired-lane diagnostic receipts");
    expect(html).not.toContain('href="/run/gemma-4-31b-it__ladder-gemma4-31b-Q4_K_M"');
    expect(html).not.toContain("retired-lane");
    expect(html).toContain('href="/run/gemma-4-31b-it__gemma-4-31b-it-q4km-s2v5/"');
    expect(html).toContain("benchmark it");
  });
});
