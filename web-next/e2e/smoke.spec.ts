import { expect, test } from "@playwright/test";

const ROUTES = [
  ["/next", "总览"],
  ["/next/events", "事件"],
  ["/next/suggestions", "建议"],
  ["/next/eval", "评测"],
  ["/next/observability", "观测"],
  ["/next/targets", "竞品目标"],
  ["/next/mappings", "SKU 对齐"],
  ["/next/reviews", "评论洞察"],
];

test.describe("工作台冒烟", () => {
  for (const [path, heading] of ROUTES) {
    test(`${heading} 可以打开`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator("h1, .page-title").first()).toContainText(heading);
      await expect(page.locator(".boot-screen")).toHaveCount(0);
    });
  }

  test("评测页可以运行冒烟批次", async ({ page }) => {
    await page.goto("/next/eval");
    await page.getByRole("button", { name: "运行评测" }).click();
    await expect(page.getByText("通过率")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("table").first()).toBeVisible();
  });

  test("观测页展示模型与 trace", async ({ page }) => {
    await page.goto("/next/observability");
    await expect(page.getByRole("heading", { name: "按模型" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "链路追踪" })).toBeVisible();
  });
});
