import { capturePage, expect, test, visitRoute } from "./fixtures";

const RUN_CASES = [
  {
    expectedComposite: "50.2",
    modelLabel: "Qwen3.6-27B",
    runId: "qwen3-6-27b__lcpp-q8_0",
    screenshotName: "run-qwen3-6-27b__lcpp-q8_0",
  },
  {
    expectedComposite: "71.2",
    modelLabel: "Qwen3 32B",
    runId: "qwen3-32b__demo-qwen3-32b-q4-k-m",
    screenshotName: "run-qwen3-32b__demo-qwen3-32b-q4-k-m",
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
    await expect(axisSection.getByText("Knowledge")).toBeVisible();
    await expect(axisSection.getByText("Instruction")).toBeVisible();
    await expect(axisSection.getByText("Agentic")).toBeVisible();
    await expect(axisSection.getByText("Math")).toBeVisible();
    await expect(axisSection.locator("div.relative.mt-3.h-7")).toHaveCount(4);
    await expect(axisSection).toContainText(/±\d+\.\d/);

    const manifestSection = page.locator("section").filter({ hasText: "Manifest" });
    await expect(manifestSection.getByText("model")).toBeVisible();
    await expect(manifestSection.getByText("lane")).toBeVisible();
    await expect(manifestSection.getByText("hardware")).toBeVisible();
    await expect(manifestSection).toContainText(/NVIDIA GeForce RTX 5090|API|SYNTHETIC DEMO/);

    const provenance = page.locator("footer").filter({ hasText: "Provenance" });
    await expect(provenance).toContainText(/knowledge\.jsonl|synthetic-demo/);
    await expect(provenance).toContainText(/instruction\.jsonl|synthetic-demo/);
    await expect(provenance).toContainText(/agentic\.jsonl|synthetic-demo/);
    await expect(provenance).toContainText(/math.*\.jsonl|synthetic-demo/);
    await expect(provenance).toContainText(/[a-f0-9]{64}|SYNTHETIC-DEMO-NOT-A-MEASUREMENT/);

    await capturePage(page, runCase.screenshotName);
  });
}
