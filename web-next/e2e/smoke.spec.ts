import { expect, test } from "@playwright/test";

const ROUTES = [
  ["/next", "智能竞价分析"],
  ["/next/agent", "Agent 模型"],
  ["/next/settings", "设置"],
];

test.describe("工作台冒烟", () => {
  for (const [path, heading] of ROUTES) {
    test(`${heading} 可以打开`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator("h1").first()).toContainText(heading, {
        timeout: 15_000,
      });
    });
  }

  test("竞价页有货架、解读和量化指标", async ({ page }) => {
    await page.goto("/next");
    await expect(page.getByRole("heading", { name: "实时货架" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI 市场解读" })).toBeVisible();
    expect(await page.locator(".shelf-product").count()).toBeGreaterThan(0);
    expect(await page.locator(".kpi").count()).toBeGreaterThanOrEqual(6);
    await expect(page.locator(".chart-svg").first()).toBeVisible();
  });

  test("竞价页可以筛选事件并看到研判", async ({ page }) => {
    await page.goto("/next");
    await expect(page.locator(".event-row").first()).toBeVisible({ timeout: 15_000 });
    await page.locator(".event-row").first().click();
    await expect(page.getByRole("heading", { name: "AI 研判" })).toBeVisible();
  });

  test("Agent 页覆盖轨迹、能力、知识、微调", async ({ page }) => {
    await page.goto("/next/agent");
    await expect(page.getByRole("heading", { name: "Agent 模型" })).toBeVisible();
    await page.getByRole("button", { name: /能力矩阵/ }).click();
    await expect(page.getByText("LangGraph", { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: /知识与案例/ }).click();
    await expect(page.getByRole("heading", { name: "知识库" })).toBeVisible();
    await page.getByRole("button", { name: /LoRA \/ SFT/ }).click();
    await expect(page.getByRole("heading", { name: "训练链路" })).toBeVisible();
  });

  test("设置页覆盖接入、模型、账户", async ({ page }) => {
    await page.goto("/next/settings");
    await expect(page.getByRole("heading", { name: "接入模块" })).toBeVisible();
    await expect(page.getByText("建议生产").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "模型路由" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "账号", exact: true })).toBeVisible();
  });

  test("接入服务可以生成令牌并测试推送", async ({ page }) => {
    await page.goto("/next/settings");
    await page.getByPlaceholder("令牌名称").fill("e2e-token");
    await page.getByRole("button", { name: "生成令牌" }).click();
    await expect(page.locator(".token-new code")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "测试推送" }).click();
    await expect(page.locator(".push-result")).toBeVisible({ timeout: 30_000 });
  });

  test("大屏是沉浸模式并可退出", async ({ page }) => {
    await page.goto("/next/screen");
    await expect(page.locator(".screen")).toBeVisible();
    await expect(page.getByRole("button", { name: "返回智能竞价" })).toBeVisible();
    await expect(page.locator(".rail")).toHaveCount(0);
    await expect(page.locator(".shelf")).toBeVisible();
  });

  test("大屏可以触发评测", async ({ page }) => {
    await page.goto("/next/screen");
    await page.getByRole("button", { name: "运行评测" }).click();
    await expect(page.getByRole("button", { name: "运行评测" })).toBeVisible({
      timeout: 60_000,
    });
  });

  test("小窗问答不占主区", async ({ page }) => {
    await page.goto("/next");
    await page.getByRole("button", { name: "辅助问答" }).click();
    await expect(page.locator(".qa-body")).toBeVisible();
  });

  test("登录页可渲染", async ({ page }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "login required" }),
      }),
    );
    await page.goto("/next/login");
    await expect(page.getByRole("heading", { name: "进入竞价控制台" })).toBeVisible();
    await expect(page.getByRole("button", { name: "进入控制台" })).toBeVisible();
    await expect(page.getByPlaceholder("admin")).toBeVisible();
    await expect(page.getByText("演示账号 · 5 个")).toHaveCount(0);
  });
});
