import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.PORT || "3000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL || `http://localhost:${PORT}`,
    trace: "on-first-retry",
    browserName: (process.env.BROWSER as any) || "chromium",
  },
  projects: [
    {
      name: "Mobile Small - 320px",
      use: { viewport: { width: 320, height: 640 } },
    },
    {
      name: "Mobile Standard - 375px",
      use: { viewport: { width: 375, height: 667 } },
    },
    {
      name: "Mobile Modern - 390px",
      use: { viewport: { width: 390, height: 844 } },
    },
    {
      name: "Mobile Max - 430px",
      use: { viewport: { width: 430, height: 932 } },
    },
    {
      name: "Tablet Portrait - 768px",
      use: { viewport: { width: 768, height: 1024 } },
    },
    {
      name: "Tablet Wide - 820px",
      use: { viewport: { width: 820, height: 1180 } },
    },
    {
      name: "Desktop Small - 1024px",
      use: { viewport: { width: 1024, height: 768 } },
    },
    {
      name: "Desktop Standard - 1280px",
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: "Desktop Large - 1366px",
      use: { viewport: { width: 1366, height: 768 } },
    },
    {
      name: "Desktop HD - 1440px",
      use: { viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npm run start -- -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
    env: {
      PLAYWRIGHT_TEST: "1",
      PORT: PORT,
    },
  },
});
