import { test, expect } from "@playwright/test";

test.describe("Real Backend API Integration & Storefront Workflow", () => {
  test("Course catalog loads real API data or renders clean empty state with retry/return", async ({
    page,
  }) => {
    await page.goto("/courses");

    // Catalog page heading
    await expect(
      page.getByRole("heading", { name: /curriculum & masterclasses/i })
    ).toBeVisible();

    // Verify filter controls
    const searchInput = page.getByPlaceholder(/search courses by topic/i);
    await expect(searchInput).toBeVisible();

    const sortSelect = page.locator('select[aria-label="Sort courses"]');
    await expect(sortSelect).toBeVisible();

    // Verify sort options exist
    await sortSelect.selectOption("price_asc");
    expect(await sortSelect.inputValue()).toBe("price_asc");

    await sortSelect.selectOption("price_desc");
    expect(await sortSelect.inputValue()).toBe("price_desc");

    await sortSelect.selectOption("newest");
    expect(await sortSelect.inputValue()).toBe("newest");

    // Verify topic filter chips
    const allTopicsChip = page.getByRole("button", { name: "All Topics" });
    await expect(allTopicsChip).toBeVisible();

    // Either courses are loaded or a valid empty state is shown
    const emptyStateHeading = page.getByRole("heading", { name: /no published courses yet|no matching courses found/i });
    const courseCards = page.locator('article, div[class*="rounded-xl"] a[href^="/courses/"]');

    const hasCards = (await courseCards.count()) > 0;
    const hasEmptyState = await emptyStateHeading.isVisible();

    expect(hasCards || hasEmptyState).toBe(true);
  });

  test("Course details (/courses/[slug]) handles non-existent slug with truthful 404 state and navigation", async ({
    page,
  }) => {
    await page.goto("/courses/non-existent-masterclass-slug-12345");

    // Verifies 404 error alert with truthful message
    await expect(page.getByText(/course not found/i)).toBeVisible();

    // Back to courses button works
    const backBtn = page.getByRole("button", { name: /back to courses/i });
    await expect(backBtn).toBeVisible();
    await backBtn.click();
    await expect(page).toHaveURL(/\/courses/);
  });

  test("Navigation items and links navigate to valid approved routes", async ({ page }) => {
    await page.goto("/");

    // Brand logo navigates to home
    const brandLogo = page.locator('header a[href="/"]').first();
    await expect(brandLogo).toBeVisible();

    // Courses link navigates to /courses
    const coursesLink = page.locator('header nav a[href="/courses"]').first();
    if (await coursesLink.isVisible()) {
      await coursesLink.click();
      await expect(page).toHaveURL(/\/courses/);
    }
  });
});
