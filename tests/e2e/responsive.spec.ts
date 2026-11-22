import { test, expect } from "@playwright/test";

const testRoutes = ["/", "/login", "/signup", "/app", "/courses"];

test.describe("Responsive Viewport Layout & Overflow Invariants", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    // Provide authenticated session cookie for protected route layout rendering
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_valid_student_session",
        url: baseURL || "http://localhost:3000",
      },
    ]);
  });

  for (const route of testRoutes) {
    test(`Route ${route} has zero horizontal overflow`, async ({ page }) => {
      await page.goto(route);

      // Verify no horizontal overflow occurs: documentElement scrollWidth must not exceed innerWidth
      const hasHorizontalScrollbar = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth;
      });

      expect(hasHorizontalScrollbar).toBe(false);
    });
  }

  test("Adapts navigation controls between mobile and desktop viewports on /app", async ({ page, viewport }) => {
    await page.goto("/app");

    if (viewport && viewport.width < 768) {
      // Mobile viewports (< 768px): StudentBottomNav visible, sidebar hidden
      const bottomNav = page.locator('nav[aria-label="Mobile Bottom Navigation"]');
      await expect(bottomNav).toBeVisible();

      const desktopSidebar = page.locator("aside");
      await expect(desktopSidebar).toBeHidden();
    } else {
      // Tablet and Desktop viewports (>= 768px): Sidebar visible, bottom nav hidden
      const desktopSidebar = page.locator("aside");
      await expect(desktopSidebar).toBeVisible();

      const bottomNav = page.locator('nav[aria-label="Mobile Bottom Navigation"]');
      await expect(bottomNav).toBeHidden();
    }
  });

  test("Server-side layout guard redirects unauthenticated visits from /app to /login", async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login\?redirect=%2Fapp/);
  });
});
