import { describe, expect, it } from "vitest";
import sitemap from "../app/sitemap";
import { getRunStaticParams } from "../lib/data";

const CURRENT_RUN_ID = "gemma-4-12b-it__gemma-4-12b-it-qat-ud-q4kxl-bounded-final-v2";
const LEGACY_RUN_ID = "qwen3-6-35b-a3b__qwen3.6-35b-a3b-q4";

describe("sitemap run URLs", () => {
  it("omits previous-index receipts from sitemap while keeping the pages buildable", async () => {
    // Given static run params still include all published receipt pages.
    const runParams = await getRunStaticParams();

    // When sitemap URLs are generated.
    const urls = (await sitemap()).map((entry) => entry.url);

    // Then only current-headline-lane receipts are advertised.
    expect(runParams).toContainEqual({ runId: LEGACY_RUN_ID });
    expect(urls).toContain(`https://local-bench.ai/run/${CURRENT_RUN_ID}/`);
    expect(urls).not.toContain(`https://local-bench.ai/run/${LEGACY_RUN_ID}/`);
  });
});
