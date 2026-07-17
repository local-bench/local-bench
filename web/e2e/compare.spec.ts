import { readCompareRuns, type CompareRun } from "./data";
import { expect, test, visitRoute } from "./fixtures";

test("compares current and retired configs without mixing index-score deltas", async ({ page }) => {
  const configs = await readCompareRuns();
  const currentConfigs = configs.filter((config) => config.scoreScope === "current-index");
  const previousConfigs = configs.filter((config) => config.scoreScope === "previous-index");
  const [leftConfig, rightConfig] = comparablePair(currentConfigs, previousConfigs);
  test.setTimeout(Math.max(30_000, configs.length * 1_000));

  await visitRoute(page, "/compare");

  await expect(page.getByRole("heading", { name: "Compare model configs" })).toBeVisible();
  const leftSelect = page.getByLabel("Left config");
  const rightSelect = page.getByLabel("Right config");
  await expect(leftSelect).toBeVisible();
  await expect(rightSelect).toBeVisible();
  await expect(page.locator('select#left-config optgroup[label="Current Index"] option')).toHaveCount(currentConfigs.length);
  await expect(page.locator('select#left-config optgroup[label="Previous-index diagnostics"] option')).toHaveCount(previousConfigs.length);

  await leftSelect.selectOption(leftConfig.id);
  await rightSelect.selectOption(rightConfig.id);

  await expect(page.getByText("VRAM delta")).toBeVisible();
  await expect(page.getByText("tok/s delta")).toBeVisible();
  await expect(page.getByRole("heading", { name: leftConfig.modelLabel })).toBeVisible();
  await expect(page.getByRole("heading", { name: rightConfig.modelLabel })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open left model/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open right model/i })).toBeVisible();

  if (leftConfig.scoreScope === "current-index" && rightConfig.scoreScope === "current-index") {
    await expect(page.getByText("Local Intelligence Index delta")).toBeVisible();
    await expect(page.getByText("Index delta withheld")).toHaveCount(0);
  } else {
    await expect(page.getByText("Index delta withheld")).toBeVisible();
    await expect(page.getByText("Diagnostic score (retired lane)")).toBeVisible();
    await expect(page.getByText("Local Intelligence Index delta")).toHaveCount(0);
  }

  const axisDeltas = page.getByTestId("compare-axis-deltas");
  for (const axis of commonAxes(leftConfig, rightConfig).map(axisLabel)) {
    await expect(axisDeltas).toContainText(axis);
  }
  await expect(page.getByTestId("compare-axis-deltas")).toContainText("wins");
});

function comparablePair(
  currentConfigs: readonly CompareRun[],
  previousConfigs: readonly CompareRun[],
): readonly [CompareRun, CompareRun] {
  if (currentConfigs.length >= 2) {
    const first = currentConfigs[0];
    const second = currentConfigs[1];
    if (first !== undefined && second !== undefined) {
      return [first, second];
    }
  }

  const current = currentConfigs[0];
  const previous = previousConfigs[0];
  expect(current, "Expected at least one current-index compare config").toBeDefined();
  expect(previous, "Expected at least one retired diagnostic compare config").toBeDefined();
  if (current === undefined || previous === undefined) {
    throw new Error("Missing compare config pair");
  }
  return [current, previous];
}

function commonAxes(left: CompareRun, right: CompareRun): readonly string[] {
  return Object.keys(left.axes).filter((axis) => right.axes[axis] !== undefined);
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
