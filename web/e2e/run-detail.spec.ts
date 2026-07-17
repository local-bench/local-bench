import { rankedCurrentModels, readIndexData, readRunData, retiredDiagnosticModels, type IndexModel, type RunData } from "./data";
import { capturePage, expect, type Page, test, visitRoute } from "./fixtures";

test("renders a current ranked run detail as a comparable index receipt", async ({ page }) => {
  const runCase = await rankedRunCase();
  const run = await readRunData(runCase.best_run_id);

  await visitRoute(page, `/run/${run.run_id}/`);

  await expect(page.getByRole("heading", { name: run.model_label, exact: true })).toBeVisible();
  await expect(page.getByText(run.run_id)).toBeVisible();
  const header = page.locator("main header");
  await expect(header).toContainText("Local Intelligence Index");
  await expect(header).toContainText(formatScore(run.composite));
  await expect(header).not.toContainText("Previous-index diagnostics");
  await expect(header).not.toContainText("Diagnostic score (retired lane)");

  await expectAxisBreakdown(page, run);
  await expectManifestAndProvenance(page, run);
  await capturePage(page, `run-${run.run_id}`);
});

test("renders a retired-lane run detail as previous-index diagnostics", async ({ page }) => {
  const runCase = await retiredRunCase();
  const run = await readRunData(runCase.best_run_id);

  await visitRoute(page, `/run/${run.run_id}/`);

  await expect(page.getByRole("heading", { name: run.model_label, exact: true })).toBeVisible();
  await expect(page.getByText(run.run_id)).toBeVisible();
  expect(run.composite).toBeNull();
  expect(run.diagnostic_composite, `${run.run_id} diagnostic composite`).not.toBeNull();

  const header = page.locator("main header");
  await expect(header).toContainText("Previous-index diagnostics");
  await expect(header).toContainText("Diagnostic score (retired lane)");
  await expect(header).toContainText(run.lane ?? "previous index");
  await expect(header).toContainText(formatScore(run.diagnostic_composite ?? null));

  await expectAxisBreakdown(page, run);
  await expectManifestAndProvenance(page, run);
  await capturePage(page, `run-${run.run_id}`);
});

async function rankedRunCase(): Promise<IndexModel & { readonly best_run_id: string }> {
  const index = await readIndexData();
  return requireBestRun(rankedCurrentModels(index.models), "current ranked run");
}

async function retiredRunCase(): Promise<IndexModel & { readonly best_run_id: string }> {
  const index = await readIndexData();
  return requireBestRun(retiredDiagnosticModels(index.models), "retired diagnostic run");
}

function requireBestRun(rows: readonly IndexModel[], label: string): IndexModel & { readonly best_run_id: string } {
  const row = rows.find((candidate) => candidate.best_run_id !== null);
  expect(row, `Expected at least one ${label}`).toBeDefined();
  expect(row?.best_run_id, `Expected ${label} to have a best_run_id`).not.toBeNull();
  if (row === undefined || row.best_run_id === null) {
    throw new Error(`Missing ${label}`);
  }
  return { ...row, best_run_id: row.best_run_id };
}

async function expectAxisBreakdown(page: Page, run: RunData): Promise<void> {
  const axisSection = page.locator("section").filter({ hasText: "Axis breakdown" });
  const axisLabels = Object.keys(run.axes).map(axisLabel);

  for (const label of axisLabels) {
    await expect(axisSection.getByText(label)).toBeVisible();
  }
  await expect(axisSection.locator("div.relative.mt-3.h-7")).toHaveCount(axisLabels.length);
  await expect(axisSection).toContainText(/±\d+\.\d/);
}

async function expectManifestAndProvenance(page: Page, run: RunData): Promise<void> {
  const manifestSection = page.locator("section").filter({ hasText: "Manifest" });
  await expect(manifestSection.getByText("model")).toBeVisible();
  await expect(manifestSection.getByText("lane")).toBeVisible();
  await expect(manifestSection.getByText("hardware")).toBeVisible();
  await expect(manifestSection).toContainText(run.lane ?? "n/a");

  const provenance = page.locator("footer").filter({ hasText: "Provenance" });
  await expect(provenance).toContainText(run.run_id.includes("synthetic") ? "synthetic-demo" : /[a-f0-9]{64}/);
}

function formatScore(score: RunData["composite"]): string {
  return score === null ? "n/a" : score.point.toFixed(1);
}

function axisLabel(axis: string): string {
  switch (axis) {
    case "agentic":
      return "Agentic";
    case "coding":
      return "Coding";
    case "instruction":
      return "Instruction";
    case "knowledge":
      return "Knowledge";
    case "math":
      return "Math";
    case "tool_calling":
      return "Tool calling";
    case "tool_use":
      // Season-2 macro-axis: the structural key stays "tool_use", the display label became
      // "Agentic" with the index-v4.1 rename (c59a970; see axisLabel in web/lib/axis-config.ts).
      return "Agentic";
    default:
      return axis;
  }
}
