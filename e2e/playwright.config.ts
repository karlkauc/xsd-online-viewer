import { defineConfig, devices } from "@playwright/test";

const port = process.env.E2E_PORT ?? "8080";
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // When E2E_EXTERNAL=1 we assume the user started the server manually
  // (e.g. via `docker run`). Otherwise we boot the Python backend in-place.
  webServer: process.env.E2E_EXTERNAL
    ? undefined
    : {
        command:
          "cd ../backend && STATIC_DIR=../frontend/dist " +
          "uvicorn app.main:app --host 127.0.0.1 --port " + port,
        url: baseURL + "/api/health",
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
});
