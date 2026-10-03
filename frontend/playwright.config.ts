import { defineConfig, devices } from "@playwright/test";

const frontendURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";
const backendURL = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI
    ? [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : "list",
  outputDir: "test-results",
  use: {
    baseURL: frontendURL,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "python -m alembic upgrade head && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: `${backendURL}/ready`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: process.env.CI ? "pnpm build && pnpm start" : "pnpm dev",
      url: frontendURL,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
