import { expect, test } from "@playwright/test";

const ROUTES = [
  ["/next", "工作区"],
  ["/next/agent", "Agent"],
  ["/next/knowledge", "知识库"],
  ["/next/settings", "设置"],
];

test.describe("工作台冒烟", () => {
  for (const [path, heading] of ROUTES) {
    test(`${heading} 可以打开`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator("h1").first()).toContainText(heading);
    });
  }

  test("工作区是市场对比视图", async ({ page }) => {
    await page.goto("/next");
    await expect(page.getByRole("heading", { name: "市场货架" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "AI 市场解读" })).toBeVisible();
    expect(await page.locator(".shelf-product").count()).toBeGreaterThan(0);
  });

  test("工作区问答返回答案", async ({ page }) => {
    await page.goto("/next");
    await page
      .getByPlaceholder("例如：价格带击穿的判定标准是什么？")
      .fill("价格带击穿的判定标准是什么？");
    await page.getByRole("button", { name: "提问" }).click();
    await expect(page.locator(".chat-answer")).toBeVisible({ timeout: 45_000 });
  });

  test("大屏是沉浸模式并可退出", async ({ page }) => {
    await page.goto("/next/screen");
    await expect(page.locator(".screen.immersive")).toBeVisible();
    await expect(page.getByRole("link", { name: "返回工作区" })).toBeVisible();
    await expect(page.locator(".sidebar")).toHaveCount(0);
  });

  test("大屏可以触发评测", async ({ page }) => {
    await page.goto("/next/screen");
    await page.getByRole("button", { name: "运行评测" }).click();
    await expect(page.getByRole("button", { name: "运行评测" })).toBeVisible({
      timeout: 60_000,
    });
  });

  test("设置页可切换模型来源与数据接入", async ({ page }) => {
    await page.goto("/next/settings");
    await expect(page.getByRole("heading", { name: "模型来源" })).toBeVisible();
    await page.getByRole("button", { name: /云端 API/ }).click();
    await expect(
      page.getByPlaceholder("https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ).toBeVisible();

    await expect(page.getByRole("heading", { name: "数据接入" })).toBeVisible();
    await page.getByRole("button", { name: /影刃八爪鱼/ }).click();
    await expect(page.getByPlaceholder("token")).toBeVisible();
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
    await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible();
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
  });
});
