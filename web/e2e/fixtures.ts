import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test as base, type Page } from "@playwright/test";

type BrowserIssue = {
  readonly kind: "console" | "pageerror" | "requestfailed" | "response";
  readonly message: string;
  readonly url: string;
};

const ARTIFACT_DIR = path.join(process.cwd(), ".e2e-artifacts");
const SCREENSHOT_DIR = path.join(ARTIFACT_DIR, "screenshots");

export const test = base.extend({
  page: async ({ page }, use) => {
    const browserIssues: BrowserIssue[] = [];

    page.on("console", (message) => {
      if (message.type() !== "error") {
        return;
      }
      browserIssues.push({
        kind: "console",
        message: message.text(),
        url: message.location().url,
      });
    });

    page.on("pageerror", (error) => {
      browserIssues.push({
        kind: "pageerror",
        message: error.message,
        url: page.url(),
      });
    });

    page.on("requestfailed", (request) => {
      const failureText = request.failure()?.errorText ?? "request failed";
      if (failureText === "net::ERR_ABORTED") {
        return;
      }
      browserIssues.push({
        kind: "requestfailed",
        message: failureText,
        url: request.url(),
      });
    });

    page.on("response", (response) => {
      if (response.status() < 400) {
        return;
      }
      browserIssues.push({
        kind: "response",
        message: `${response.status()} ${response.statusText()}`,
        url: response.url(),
      });
    });

    await use(page);

    expect(browserIssues, formatBrowserIssues(browserIssues)).toEqual([]);
  },
});

export { expect, type Page };

export async function visitRoute(page: Page, route: string): Promise<void> {
  const response = await page.goto(route, { waitUntil: "load" });
  expect(response, `Expected ${route} to return a document response`).not.toBeNull();
  if (response === null) {
    return;
  }

  expect(response.status(), `Expected ${route} to return HTTP 200`).toBe(200);
  await page.waitForLoadState("networkidle");
  await expect(page.locator("main")).toBeVisible();

  const bodyText = await page.locator("body").innerText();
  expect(bodyText.trim().length, `Expected ${route} to render non-empty body content`).toBeGreaterThan(0);
}

export async function capturePage(page: Page, name: string): Promise<string> {
  await mkdir(SCREENSHOT_DIR, { recursive: true });
  const fileName = `${sanitizeFileName(name)}.png`;
  const filePath = path.join(SCREENSHOT_DIR, fileName);
  await page.screenshot({ fullPage: true, path: filePath });
  return fileName;
}

export async function visitAndCapture(page: Page, route: string, screenshotName: string): Promise<void> {
  await visitRoute(page, route);
  await capturePage(page, screenshotName);
}

function sanitizeFileName(name: string): string {
  const normalized = name.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
  return normalized.replace(/^-+|-+$/g, "");
}

function formatBrowserIssues(issues: readonly BrowserIssue[]): string {
  if (issues.length === 0) {
    return "No browser issues recorded.";
  }

  return issues.map((issue) => `${issue.kind}: ${issue.message} (${issue.url})`).join("\n");
}
