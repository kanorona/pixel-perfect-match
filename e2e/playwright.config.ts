import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["line"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8100",
    trace: process.env.CI ? "off" : "retain-on-failure",
    screenshot: process.env.CI ? "off" : "only-on-failure",
    video: process.env.CI ? "off" : "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
