import { capturePage, expect, test, visitRoute } from "./fixtures";

const RUN_CASES = [
  {
    expectedComposite: "94.4",
    modelLabel: "Gemini 3.1 Pro",
    runId: "gemini-3-1-pro__anchor-gemini-quick",
    screenshotName: "run-gemini-3-1-pro__anchor-gemini-quick",
  },
  {
    expectedComposite: "85.2",
    modelLabel: "Qwen3.5 9B",
    runId: "qwen3-5-9b__quick-9b-var1",
    screenshotName: "run-qwen3-5-9b__quick-9b-var1",
  },
] as const;

for (const runCase of RUN_CASES) {
  test(`renders run detail for ${runCase.runId}`, async ({ page }) => {
    await visitRoute(page, `/run/${runCase.runId}/`);

    await expect(page.getByRole("heading", { name: runCase.modelLabel })).toBeVisible();
    await expect(page.getByText(runCase.runId)).toBeVisible();
    await expect(page.locator("main header")).toContainText(runCase.expectedComposite);
    await expect(page.locator("main header")).toContainText(/±\d+\.\d 95% CI/);

    const axisSection = page.locator("section").filter({ hasText: "Axis breakdown" });
    await expect(axisSection.getByText("genmath")).toBeVisible();
    await expect(axisSection.getByText("IFEval")).toBeVisible();
    await expect(axisSection.getByText("MMLU-Pro")).toBeVisible();
    await expect(axisSection.locator("div.relative.mt-3.h-7")).toHaveCount(3);
    await expect(axisSection).toContainText(/±\d+\.\d/);

    const manifestSection = page.locator("section").filter({ hasText: "Manifest" });
    await expect(manifestSection.getByText("model")).toBeVisible();
    await expect(manifestSection.getByText("lane")).toBeVisible();
    await expect(manifestSection.getByText("hardware")).toBeVisible();
    await expect(manifestSection).toContainText(/NVIDIA GeForce RTX 5090|API/);

    const provenance = page.locator("footer").filter({ hasText: "Provenance" });
    await expect(provenance).toContainText("genmath_quick.jsonl");
    await expect(provenance).toContainText("ifeval_quick.jsonl");
    await expect(provenance).toContainText("mmlu_pro_quick.jsonl");
    await expect(provenance).toContainText(/[a-f0-9]{64}/);

    await capturePage(page, runCase.screenshotName);
  });
}
