import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [
    ["list"],
    ["json", { outputFile: "../artifacts/browser/results.json" }],
    ["html", { outputFolder: "../artifacts/browser/report", open: "never" }],
  ],
  outputDir: "../artifacts/browser/test-output",
  use: {
    actionTimeout: 15000,
    navigationTimeout: 30000,
    baseURL: process.env.QA_BASE_URL || "http://localhost:3010",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: "mobile",
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        deviceScaleFactor: 1,
      },
    },
  ],
});
