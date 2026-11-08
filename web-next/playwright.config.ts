import { defineConfig } from "@playwright/test";

/**
 * 冒烟 e2e：跑构建产物 + 本地服务。
 * 本机默认用 Edge（channel: "msedge"），无需下载浏览器；
 * CI 里设 PLAYWRIGHT_CHANNEL=bundled 使用 `npx playwright install chromium` 的浏览器。
 */
const bundled = process.env.PLAYWRIGHT_CHANNEL === "bundled";
const channel = (process.env.PLAYWRIGHT_CHANNEL ?? "msedge") as
  | "msedge"
  | "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:8011",
    headless: true,
    trace: "retain-on-failure",
    ...(bundled ? {} : { channel }),
  },
  webServer: {
    command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8011",
    cwd: "..",
    url: "http://127.0.0.1:8011/api/health",
    reuseExistingServer: true,
    timeout: 60_000,
    env: {
      LIRA_LLM: "off",
      LIRA_SCHEDULER: "off",
      LIRA_AUTH: "off",
    },
  },
});
