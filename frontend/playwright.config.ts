import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack loaded with the fictional demo data
 * (`scripts/reset-dev.sh`, or `docker compose --profile demo run --rm demo-seed`).
 *
 *   E2E_BASE_URL=http://localhost:3000 npx playwright test
 *
 * Tests share one database, so they run serially and clean up what they create.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
