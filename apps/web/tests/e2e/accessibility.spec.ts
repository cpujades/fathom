import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { SIGN_IN_EMAIL_TRANSFER_KEY } from "../../app/lib/authEmailTransfer";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectNoAutomaticAccessibilityViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  expect(results.violations).toEqual([]);
}

for (const route of ["/", "/signin", "/signup", "/auth/recovery", "/missing-briefing-route"]) {
  test(`${route} has resilient landmarks and no automatic AA violations`, async ({ page }) => {
    await page.goto(route);

    await expect(page.locator("main#main-content")).toHaveCount(1);
    await expectNoAutomaticAccessibilityViolations(page);
  });
}

test("password recovery without a verified link fails safely", async ({ page }) => {
  await page.goto("/auth/recovery");

  await expect(page.locator("#password-recovery-error")).toContainText("Open the password reset link");
  await expect(page.locator("input#new-password")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/signin");
});

test("skip navigation is the first keyboard stop", async ({ page }) => {
  await page.goto("/signin");
  await page.keyboard.press("Tab");

  const skipLink = page.getByRole("link", { name: "Skip to content" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();

  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
});

test("pricing tabs support keyboard navigation and identify their active panel", async ({ page }) => {
  await page.goto("/#pricing");

  const subscriptionTab = page.getByRole("tab", { name: "Subscription" });
  const packsTab = page.getByRole("tab", { name: "One-time packs" });
  await subscriptionTab.focus();
  await page.keyboard.press("ArrowRight");

  await expect(packsTab).toBeFocused();
  await expect(packsTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel", { name: "One-time packs" })).toHaveAttribute(
    "aria-labelledby",
    "pricing-packs-tab"
  );

  await page.keyboard.press("ArrowLeft");
  await expect(subscriptionTab).toBeFocused();
  await expect(subscriptionTab).toHaveAttribute("aria-selected", "true");
});

test("public pack choices carry the exact catalog plan code into signup", async ({ page }) => {
  await page.goto("/?pricing=packs#pricing");

  await expect(page.getByRole("link", { name: "Select Trial" })).toHaveAttribute("href", /plan=trial_pack/);
  await expect(page.getByRole("link", { name: "Select Creator" })).toHaveAttribute("href", /plan=creator_pack/);
  await expect(page.getByRole("link", { name: "Select Studio" })).toHaveAttribute("href", /plan=studio_pack/);
});

test("auth pages show only trusted paid-plan context", async ({ page }) => {
  await page.goto("/signup?next=%2Fapp%2Fbilling&intent=paid&plan=creator_pack");

  const summary = page.getByRole("region", { name: "Continue with Creator Pack" });
  await expect(summary).toContainText("$15 one-time · 10 hours");
  await expect(summary).toContainText("Payment has not started");

  await page.goto("/signin?next=%2Fapp%2Fbilling&intent=paid&plan=made_up_plan");
  await expect(page.getByRole("region", { name: /^Continue with / })).toHaveCount(0);
});

test("ordinary auth entries remain free of product-selection copy", async ({ page }) => {
  for (const route of ["/signup", "/signin"] as const) {
    await page.goto(route);
    await expect(page.getByRole("region", { name: /^Continue with / })).toHaveCount(0);
    await expect(page.getByText("Payment has not started", { exact: false })).toHaveCount(0);
  }
});

test("duplicate-signup recovery email is consumed without entering the URL or password", async ({ page }) => {
  await page.goto("/signup");
  await page.evaluate(
    ({ key, email }) => window.sessionStorage.setItem(key, email),
    { key: SIGN_IN_EMAIL_TRANSFER_KEY, email: "person@example.com" }
  );

  await page.goto("/signin?next=%2Fapp%2Fbilling&intent=paid&plan=creator_pack");
  await expect(page.locator("input#email")).toHaveValue("person@example.com");
  await expect(page.locator("input#password")).toHaveValue("");
  await expect(page).not.toHaveURL(/person%40example\.com|person@example\.com/);

  await page.reload();
  await expect(page.locator("input#email")).toHaveValue("");
});

test("public routes return baseline browser security headers", async ({ request }) => {
  const response = await request.get("/");
  const headers = response.headers();

  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["content-security-policy"]).not.toContain("connect-src *");
  expect(headers["permissions-policy"]).toContain("camera=()");
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
});

test("core public routes do not hide horizontal overflow on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });

  for (const route of ["/", "/signin", "/signup", "/auth/recovery", "/missing-briefing-route"]) {
    await page.goto(route);
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));

    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  }
});
