import { test, expect } from "@playwright/test";

test.describe("LAN IP Connectivity & Google Authentication Verification", () => {
  test("Featured Masterclasses loads cleanly via LAN URL without Failed to fetch", async ({
    page,
  }) => {
    // Monitor API requests made by the frontend
    const coursesApiPromise = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/courses") &&
        response.request().method() === "GET",
      { timeout: 10000 }
    );

    // Track console errors
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    // Navigate to the LAN URL
    await page.goto("http://192.168.1.103:3000");

    // Wait for the courses API request to complete and verify 200 OK
    const coursesResponse = await coursesApiPromise;
    expect(coursesResponse.status()).toBe(200);

    const corsHeader = coursesResponse.headers()["access-control-allow-origin"];
    expect(corsHeader).toBe("http://192.168.1.103:3000");

    // Scroll to Featured Masterclasses section
    const featuredHeading = page.getByRole("heading", {
      name: /featured masterclasses/i,
    });
    await expect(featuredHeading).toBeVisible();
    await featuredHeading.scrollIntoViewIfNeeded();

    // Verify error state is NOT displayed
    const failedToLoadAlert = page.getByRole("heading", {
      name: /failed to load featured courses/i,
    });
    await expect(failedToLoadAlert).not.toBeVisible();

    const failedToFetchText = page.getByText(/failed to fetch/i);
    await expect(failedToFetchText).not.toBeVisible();

    // Verify valid content: clean empty state or course cards
    const emptyStateHeading = page.getByRole("heading", {
      name: /new masterclasses in preparation/i,
    });
    const courseCards = page.locator('article, div[class*="rounded-xl"] a[href^="/courses/"]');

    const hasCards = (await courseCards.count()) > 0;
    const hasEmptyState = await emptyStateHeading.isVisible();
    expect(hasCards || hasEmptyState).toBe(true);

    // Capture screenshot evidence of Featured Masterclasses
    const coursesSection = page.locator("#courses");
    await coursesSection.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/lan-featured-courses-verified.png",
    });

    // Verify no CORS or network failure console errors
    const fetchErrors = consoleErrors.filter((err) =>
      err.toLowerCase().includes("failed to fetch") ||
      err.toLowerCase().includes("cors policy")
    );
    expect(fetchErrors).toHaveLength(0);
  });

  test("Login page loads cleanly via LAN URL without FedCM AbortError", async ({
    page,
  }) => {
    const consoleLogs: string[] = [];
    const consoleErrors: string[] = [];

    page.on("console", (msg) => {
      consoleLogs.push(msg.text());
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    // Navigate to login page on LAN URL
    await page.goto("http://192.168.1.103:3000/login");

    // Verify login page elements
    const loginHeading = page.getByRole("heading", { name: /welcome back/i });
    await expect(loginHeading).toBeVisible();

    const signInButton = page.getByRole("button", { name: /^sign in$/i });
    await expect(signInButton).toBeVisible();

    // Verify Google login button
    const googleButton = page.getByRole("button", {
      name: /continue with google/i,
    });
    await expect(googleButton).toBeVisible();
    await expect(googleButton).toBeEnabled();

    // Wait 2 seconds for any async Google Identity Services scripts or prompts
    await page.waitForTimeout(2000);

    // Assert that FedCM AbortError did NOT occur
    const fedcmAbortErrors = consoleLogs.filter((log) =>
      log.includes("FedCM get() rejects with AbortError")
    );
    expect(fedcmAbortErrors).toHaveLength(0);

    // Capture screenshot evidence of Login page
    await page.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/lan-login-google-verified.png",
    });
  });
});
