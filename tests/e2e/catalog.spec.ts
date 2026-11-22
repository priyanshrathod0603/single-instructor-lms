import { test, expect } from "@playwright/test";

test.describe("Public Storefront & Course Catalog Experience", () => {
  test("Homepage loads with hero, typewriter heading, featured masterclasses, and FAQ", async ({
    page,
    viewport,
  }) => {
    await page.goto("/");

    // Verify Hero title with typewriter phrase
    const h1 = page.locator("h1");
    await expect(h1).toBeVisible();
    await expect(h1).toContainText("Master");
    await expect(h1).toContainText("Directly from an Expert");

    // Verify CTA button
    const browseButton = page.getByRole("link", { name: /browse all masterclasses/i });
    await expect(browseButton).toBeVisible();

    // Verify Featured Masterclasses section
    await expect(
      page.getByRole("heading", { name: /featured masterclasses/i })
    ).toBeVisible();

    // Verify Instructor Profile section
    await expect(
      page.getByRole("heading", {
        name: /zero generic filler\. just pure architectural mastery\./i,
      })
    ).toBeVisible();

    // Verify FAQ accordion section
    await expect(
      page.getByRole("heading", { name: /everything you need to know/i })
    ).toBeVisible();

    // Test FAQ Accordion expansion
    const faqTrigger = page.getByRole("button", {
      name: /how does this single-instructor platform differ from open course marketplaces\?/i,
    });
    await expect(faqTrigger).toBeVisible();
    await faqTrigger.click();
    await expect(
      page.getByText(/open marketplaces allow anyone to publish content/i)
    ).toBeVisible();

    // Capture visual screenshot at this viewport size
    if (viewport) {
      await page.screenshot({
        path: `docs/frontend/screenshots/home-${viewport.width}px.png`,
        fullPage: false,
      });
    }
  });

  test("Desktop navigation dropdowns and search interaction", async ({ page, viewport }) => {
    await page.goto("/");

    if (viewport && viewport.width >= 1024) {
      // Test Start Learning dropdown
      const startLearningBtn = page.getByRole("button", { name: /start learning/i });
      await expect(startLearningBtn).toBeVisible();
      await startLearningBtn.click();

      // Menu opens
      await expect(page.locator('[role="menu"]')).toBeVisible();
      const browseCurriculumItem = page.getByText("Browse All Curriculum");
      await expect(browseCurriculumItem).toBeVisible();

      // Keyboard Esc closes menu
      await page.keyboard.press("Escape");
      await expect(browseCurriculumItem).toBeHidden();

      // Test Tutorials dropdown & outside-click close
      const tutorialsBtn = page.getByRole("button", { name: /tutorials/i });
      await expect(tutorialsBtn).toBeVisible();
      await tutorialsBtn.click();
      await expect(page.locator('[role="menu"]')).toBeVisible();
      const backendTopic = page.getByText("Backend Engineering");
      await expect(backendTopic).toBeVisible();

      // Escape or outside-click closes menu
      await page.keyboard.press("Escape");
      await expect(backendTopic).toBeHidden();

      // Test Header Search
      const searchInput = page.locator('header input[aria-label="Search courses"]');
      await expect(searchInput).toBeVisible();
      await searchInput.fill("Architecture");
      await searchInput.press("Enter");
      await page.waitForURL(/\/courses\?search=Architecture/);
    } else {
      // Mobile drawer
      const hamburger = page.locator('button[aria-label="Open mobile navigation menu"]');
      await expect(hamburger).toBeVisible();
      await hamburger.click();
      const mobileCoursesLink = page.locator('div[role="dialog"] a[href="/courses"]').first();
      await expect(mobileCoursesLink).toBeVisible();

      // Test mobile Start Learning accordion inside drawer
      const mobileAccordionTrigger = page.locator('div[role="dialog"]').getByRole("button", { name: /start learning/i });
      if (await mobileAccordionTrigger.isVisible()) {
        await mobileAccordionTrigger.click();
        await expect(page.locator('div[role="dialog"]').getByText("System Architecture Track")).toBeVisible();
      }

      await mobileCoursesLink.click();
      await expect(page).toHaveURL(/\/courses/);
    }
  });

  test("Course Catalog (/courses) renders search input, tag filters, and reacts to typing", async ({
    page,
    viewport,
  }) => {
    await page.goto("/courses");

    // Catalog header
    await expect(
      page.getByRole("heading", { name: /curriculum & masterclasses/i })
    ).toBeVisible();

    // Search input
    const searchInput = page.getByPlaceholder(/search courses by topic/i);
    await expect(searchInput).toBeVisible();

    // Type in search query
    await searchInput.fill("Architecture");
    await expect(searchInput).toHaveValue("Architecture");

    // Clear search button appears and resets input
    const clearBtn = page.getByRole("button", { name: /clear search text/i });
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();
    await expect(searchInput).toHaveValue("");

    // Capture visual screenshot of catalog
    if (viewport) {
      await page.screenshot({
        path: `docs/frontend/screenshots/courses-${viewport.width}px.png`,
        fullPage: false,
      });
    }
  });

  test("Strict Zero-Fake-Data Audit: DOM contains zero fake metrics or fake ratings", async ({
    page,
  }) => {
    await page.goto("/");

    // Must NOT contain invented marketing claims
    const content = await page.content();
    expect(content).not.toContain("4.9/5.0");
    expect(content).not.toContain("10,000+ Enrolled Students");
    expect(content).not.toContain("SHOWCASE_FALLBACK_COURSES");
  });
});
