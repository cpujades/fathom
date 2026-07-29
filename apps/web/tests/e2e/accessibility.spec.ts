import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoAutomaticAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  expect(results.violations).toEqual([]);
}

for (const route of ["/", "/signin", "/signup", "/missing-briefing-route"]) {
  test(`${route} has resilient landmarks and no automatic AA violations`, async ({ page }) => {
    await page.goto(route);

    await expect(page.locator("main#main-content")).toHaveCount(1);
    await expectNoAutomaticAccessibilityViolations(page);
  });
}

test("skip navigation is the first keyboard stop", async ({ page }) => {
  await page.goto("/signin");
  await page.keyboard.press("Tab");

  const skipLink = page.getByRole("link", { name: "Skip to content" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();

  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
});

test("core public routes do not hide horizontal overflow on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });

  for (const route of ["/", "/signin", "/signup", "/missing-briefing-route"]) {
    await page.goto(route);
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));

    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  }
});
