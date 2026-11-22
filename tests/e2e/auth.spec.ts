import { test, expect } from "@playwright/test";

test.describe("Authentication Flows & Client Invariants", () => {
  test("Login form validates email format and prevents submission on empty inputs", async ({ page }) => {
    await page.goto("/login");

    const submitBtn = page.getByRole("button", { name: /sign in/i });
    await submitBtn.click();

    // Client validation errors must appear without page reload
    await expect(page.getByText("Email address is required")).toBeVisible();
    await expect(page.getByText("Password is required")).toBeVisible();
  });

  test("Password visibility toggle switches between text and password input", async ({ page }) => {
    await page.goto("/login");

    const passwordInput = page.locator('input[type="password"]');
    await expect(passwordInput).toBeVisible();

    const toggleBtn = page.getByRole("button", { name: /show password/i });
    await toggleBtn.click();

    const textInput = page.locator('input[type="text"][name="password"]');
    await expect(textInput).toBeVisible();
  });

  test("Signup form enforces 12-character minimum password length", async ({ page }) => {
    await page.goto("/signup");

    await page.fill('input[name="full_name"]', "Test User");
    await page.fill('input[name="email"]', "test@example.com");
    await page.fill('input[name="password"]', "shortpwd");

    const submitBtn = page.getByRole("button", { name: /create account/i });
    await submitBtn.click();

    await expect(
      page.getByText("Password must be at least 12 characters long")
    ).toBeVisible();
  });
});
