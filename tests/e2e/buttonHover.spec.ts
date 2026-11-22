import { test, expect } from "@playwright/test";

test.describe("Button Hover Interaction & Premium Motion Verification", () => {
  test("Primary CTA button exhibits hover elevation, subtle scale, and arrow translate", async ({
    page,
    viewport,
  }) => {
    await page.goto("/");

    // Locate primary CTA button on hero
    const primaryCta = page.getByRole("link", { name: /browse all masterclasses/i }).locator("button");
    await expect(primaryCta).toBeVisible();

    // Verify interaction classes for elevation, scale, duration, and arrow slide
    const className = await primaryCta.getAttribute("class");
    expect(className).toContain("hover:-translate-y-0.5");
    expect(className).toContain("hover:scale-[1.02]");
    expect(className).toContain("hover:shadow-card");
    expect(className).toContain("active:scale-[0.98]");
    expect(className).toContain("duration-200");
    expect(className).toContain("will-change-transform");

    // Perform hover
    await primaryCta.hover();
    await expect(primaryCta).toBeVisible();

    // Verify arrow icon inside button
    const arrowIcon = primaryCta.locator("svg");
    await expect(arrowIcon).toBeVisible();
  });

  test("Outline and secondary CTA buttons exhibit border, background, and text transition", async ({
    page,
  }) => {
    await page.goto("/");

    // Locate outline button on hero
    const outlineCta = page.getByRole("link", { name: /create student account/i }).first().locator("button");
    await expect(outlineCta).toBeVisible();

    const className = await outlineCta.getAttribute("class");
    expect(className).toContain("border-2");
    expect(className).toContain("hover:bg-brand-mint/40");
    expect(className).toContain("hover:text-brand-teal-dark");
    expect(className).toContain("hover:-translate-y-0.5");

    await outlineCta.hover();
    await expect(outlineCta).toBeVisible();
  });

  test("Closing section CTAs use shared Button component with premium hover classes", async ({
    page,
  }) => {
    await page.goto("/");

    // Locate closing banner buttons scoped to closing section
    const closingSection = page.locator("section.bg-primary-teal");
    const closingExploreBtn = closingSection.getByRole("link", { name: /explore all courses/i }).locator("button");
    await expect(closingExploreBtn).toBeVisible();
    const exploreClass = await closingExploreBtn.getAttribute("class");
    expect(exploreClass).toContain("hover:-translate-y-0.5");
    expect(exploreClass).toContain("hover:scale-[1.02]");

    const closingAccountBtn = closingSection.getByRole("link", { name: /create student account/i }).locator("button");
    await expect(closingAccountBtn).toBeVisible();
    const accountClass = await closingAccountBtn.getAttribute("class");
    expect(accountClass).toContain("border-2");
    expect(accountClass).toContain("hover:border-white");
  });
});
