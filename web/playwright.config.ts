import { defineConfig } from "@playwright/test";

const PORT = 4321;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./.e2e-artifacts/test-results",
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: ".e2e-artifacts/report" }]],
  use: {
    baseURL: BASE_URL,
    browserName: "chromium",
    screenshot: "on",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npm run build && node e2e/static-server.mjs out ${PORT}`,
    cwd: ".",
    reuseExistingServer: true,
    timeout: 120_000,
    url: BASE_URL,
  },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
      },
    },
  ],
});
