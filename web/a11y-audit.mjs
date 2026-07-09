// Transient accessibility audit script (not part of the app; delete after run).
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const PAGES = [
  "/",
  "/leaderboard",
  "/model/qwen3-6-27b",
  "/model/qwopus3-6-27b-v2-mtp",
  "/submit",
  "/methodology",
  "/submission",
];
const BASE = "https://local-bench.ai";

const browser = await chromium.launch();
const context = await browser.newContext();
const summary = [];

for (const path of PAGES) {
  const page = await context.newPage();
  const response = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const bySeverity = {};
  for (const v of results.violations) {
    bySeverity[v.impact] = bySeverity[v.impact] || [];
    bySeverity[v.impact].push({ id: v.id, help: v.help, nodes: v.nodes.length, sample: v.nodes[0]?.target?.join(" ") ?? "" });
  }
  // Keyboard sanity: tab 15 times, record focused element kinds.
  const focused = [];
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press("Tab");
    focused.push(await page.evaluate(() => {
      const el = document.activeElement;
      return el ? `${el.tagName.toLowerCase()}${el.getAttribute("aria-label") ? "[aria-label]" : ""}${el.textContent?.trim().slice(0, 25) ? ":" + el.textContent.trim().slice(0, 25) : ""}` : "none";
    }));
  }
  summary.push({ path, status: response?.status(), violations: bySeverity, tabbed: focused.filter((f) => f !== "none").length, focusSample: focused.slice(0, 6) });
  await page.close();
}

await browser.close();
console.log(JSON.stringify(summary, null, 1));
