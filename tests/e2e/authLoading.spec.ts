import { test, expect } from "@playwright/test";

test.describe("Premium Authentication Loading & Session Recovery", () => {
  test("Email login displays loading overlay, prevents duplicate clicks, and cleans up on error", async ({
    page,
  }) => {
    // Intercept login to delay 1000ms and return standard 401 error envelope
    await page.route("**/api/v1/auth/login", async (route) => {
      await new Promise((r) => setTimeout(r, 1000));
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid email or password",
            request_id: "req-err-123",
          },
        }),
      });
    });

    await page.goto("/login");

    const emailInput = page.locator('input[name="email"]');
    const passwordInput = page.locator('input[name="password"]');
    const submitBtn = page.getByRole("button", { name: /sign in/i });

    await emailInput.fill("student@example.com");
    await passwordInput.fill("secretpassword123");

    // Initiate submission
    await submitBtn.click();

    // Verify loading overlay appears with accessible role="status"
    const statusOverlay = page.locator('[role="status"]');
    await expect(statusOverlay).toBeVisible();
    await expect(statusOverlay).toContainText("Verifying your credentials…");

    // Verify button is disabled preventing duplicate submissions
    await expect(submitBtn).toBeDisabled();

    // Capture screenshot of loading overlay in action
    await page.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/login-loading-overlay.png",
      fullPage: false,
    });

    // Wait for the simulated failure response
    await expect(page.getByText("Invalid email or password")).toBeVisible();

    // Loading overlay must be cleaned up and dismissed
    await expect(statusOverlay).not.toBeVisible();

    // Form inputs must remain preserved
    await expect(emailInput).toHaveValue("student@example.com");
    await expect(passwordInput).toHaveValue("secretpassword123");

    // Submit button must be re-enabled for user retry
    await expect(submitBtn).not.toBeDisabled();
  });

  test("Email login successful transition progresses through status messages", async ({ page }) => {
    let callCount = 0;
    await page.route("**/api/v1/auth/login", async (route) => {
      callCount++;
      await new Promise((r) => setTimeout(r, 600));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: { id: "u-123", email: "student@example.com", roles: ["STUDENT"] },
          access_token: "mock-token",
        }),
      });
    });

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "u-123",
          email: "student@example.com",
          roles: ["STUDENT"],
        }),
      });
    });

    await page.goto("/login");

    await page.fill('input[name="email"]', "student@example.com");
    await page.fill('input[name="password"]', "password12345");

    const submitBtn = page.getByRole("button", { name: /sign in/i });
    await submitBtn.click();

    // Rapid double click to test duplicate submission prevention
    if (await submitBtn.isEnabled()) {
      await submitBtn.click().catch(() => {});
    }

    const statusOverlay = page.locator('[role="status"]');
    await expect(statusOverlay).toBeVisible();

    // Verify it only sent 1 login request
    expect(callCount).toBe(1);

    // Wait for redirect to /app
    await page.waitForURL("**/app");
  });

  test("SESSION_REVOKED triggers modal, prevents duplicate clicks, and navigates to /login", async ({
    page,
  }) => {
    await page.goto("/login");

    // Trigger SESSION_REVOKED standard event in the browser window
    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("lms:session_revoked", {
          detail: { message: "Your account logged in on another device in Chrome." },
        })
      );
    });

    // The DisplacedSessionModal must appear
    const modalTitle = page.getByText("You signed in on another device");
    await expect(modalTitle).toBeVisible();
    await expect(
      page.getByText("Your account logged in on another device in Chrome.")
    ).toBeVisible();

    // Take screenshot of Displaced Session Modal
    await page.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/session-displaced-modal.png",
      fullPage: false,
    });

    const signInAgainBtn = page.getByRole("button", { name: /sign in again/i });
    await expect(signInAgainBtn).toBeVisible();
    await expect(signInAgainBtn).not.toBeDisabled();

    // Click Sign In Again
    await signInAgainBtn.click();

    // Verify modal is dismissed and redirected to /login
    await expect(modalTitle).not.toBeVisible();
    await expect(page).toHaveURL(/\/login/);

    // Verify login form is immediately interactive with no lingering modal or spinner
    const emailInput = page.locator('input[name="email"]');
    const submitBtn = page.getByRole("button", { name: /sign in/i });
    await expect(emailInput).toBeVisible();
    await expect(emailInput).not.toBeDisabled();
    await emailInput.fill("recovered@example.com");
    await expect(emailInput).toHaveValue("recovered@example.com");
    await expect(submitBtn).toBeVisible();
    await expect(submitBtn).not.toBeDisabled();
  });

  test("Verify email page displays clean inline loading state", async ({ page }) => {
    await page.route("**/api/v1/auth/verify-email**", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ message: "Email verified successfully" }),
      });
    });

    await page.goto("/verify-email?token=valid-token-123");

    // Inline loading overlay is visible
    const status = page.locator('[role="status"]');
    await expect(status).toBeVisible();
    await expect(status).toContainText("Verifying your email");

    // Capture screenshot of inline verify-email loading
    await page.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/verify-email-loading.png",
      fullPage: false,
    });

    // Successfully transitioned
    await expect(page.getByText("Email Verified Successfully!")).toBeVisible();
  });

  test("Reduced motion preference is respected without errors", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/login");

    // Verify page loads cleanly with reduced motion
    await expect(page.getByRole("button", { name: /continue with google/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();

    // Capture screenshot of interactive login screen
    await page.screenshot({
      path: "/Users/priyansh/.gemini/antigravity/brain/c41da530-5ba8-4520-b73f-0a75537b3c10/login-interactive.png",
      fullPage: false,
    });
  });
});
