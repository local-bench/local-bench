import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const captures = [
  ["methodology-desktop.png", "/methodology", { width: 1440, height: 1000 }],
  ["methodology-mobile.png", "/methodology", { width: 390, height: 844 }],
  ["leaderboard-desktop.png", "/leaderboard", { width: 1440, height: 1000 }],
  ["leaderboard-mobile.png", "/leaderboard", { width: 390, height: 844 }],
];

for (const [filename, route, viewport] of captures) {
  const page = await browser.newPage({ viewport });
  await page.goto(`http://localhost:3001${route}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: filename, fullPage: true });
  await page.close();
}

const diagnosticsPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await diagnosticsPage.goto("http://localhost:3001/leaderboard", { waitUntil: "networkidle" });
await diagnosticsPage.locator("table details summary").first().click();
await diagnosticsPage.screenshot({ path: "leaderboard-diagnostics-desktop.png", fullPage: true });
await diagnosticsPage.close();
await browser.close();
