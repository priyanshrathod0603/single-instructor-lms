import { test, expect } from "@playwright/test";

test.describe("Student Learning Experience & Portal Verification (Part 3)", () => {
  test("Public Certificate Verification: renders registry interface", async ({ page }) => {
    await page.goto("/verify/certificate/sample-hash-123");

    // Check heading and registry badge
    await expect(page.getByRole("heading", { name: /Certificate Authenticity/i })).toBeVisible();
    await expect(page.getByText(/Official Credential Verification Registry/i)).toBeVisible();
  });

  test("Public Certificate Verification: handles invalid certificate cleanly without crash", async ({ page }) => {
    // Intercept with 404
    await page.route("**/api/v1/certificates/verify/*", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          success: false,
          error: {
            code: "CERTIFICATE_NOT_FOUND",
            message: "The requested certificate hash does not exist in the registry.",
          },
        }),
      });
    });

    await page.goto("/verify/certificate/non-existent-hash");

    await expect(page.getByRole("heading", { name: /Invalid or Unrecognized Certificate/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Browse Authentic Courses/i })).toBeVisible();
  });

  test("Public Certificate Verification: displays verified credential matrix when valid", async ({ page }) => {
    // Intercept with 200 Valid
    await page.route("**/api/v1/certificates/verify/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          verified: true,
          status: "VALID",
          certificate_no: "LMS-2026-999",
          student_name: "Alex Doe",
          course_title: "Full-Stack Web Architecture",
          issued_at: "2026-01-15T12:00:00Z",
          verification_hash: "hash-valid-999",
        }),
      });
    });

    await page.goto("/verify/certificate/hash-valid-999");

    await expect(page.getByText(/Cryptographically Verified Credential/i)).toBeVisible();
    await expect(page.getByText("Alex Doe")).toBeVisible();
    await expect(page.getByText("Full-Stack Web Architecture")).toBeVisible();
    await expect(page.getByText("#LMS-2026-999")).toBeVisible();
  });

  test("Student Portal Navigation: desktop sidebar and mobile bottom navigation are accessible", async ({
    page,
    viewport,
  }) => {
    // Set e2e session cookie to satisfy requireServerAuth
    await page.context().addCookies([
      {
        name: "lms_session",
        value: "e2e_student_session",
        domain: "localhost",
        path: "/",
      },
    ]);

    // Mock enrolled courses API response
    await page.route("**/api/v1/enrollments*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          size: 20,
        }),
      });
    });

    // Mock quiz attempts API response
    await page.route("**/api/v1/quiz-attempts*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          size: 50,
        }),
      });
    });

    await page.goto("/app");

    const isMobile = (viewport?.width ?? 1024) < 768;

    if (isMobile) {
      // Bottom navigation must be visible on mobile
      const bottomNav = page.locator("nav[aria-label='Mobile Bottom Navigation']");
      await expect(bottomNav).toBeVisible();
      await expect(bottomNav.getByRole("link", { name: /Courses/i })).toBeVisible();
      await expect(bottomNav.getByRole("link", { name: /Tasks/i })).toBeVisible();
      await expect(bottomNav.getByRole("link", { name: /Profile/i })).toBeVisible();
    } else {
      // Sidebar navigation must be visible on tablet and desktop
      const sidebar = page.locator("aside[aria-label='Student Navigation']");
      await expect(sidebar).toBeVisible();
      await expect(sidebar.getByRole("link", { name: /My Courses/i })).toBeVisible();
      await expect(sidebar.getByRole("link", { name: /Assignments/i })).toBeVisible();
      await expect(sidebar.getByRole("link", { name: /Quizzes/i })).toBeVisible();
      await expect(sidebar.getByRole("link", { name: /Certificates/i })).toBeVisible();
    }
  });

  test("Student Portal: Enrolled courses directory renders empty state correctly", async ({
    page,
  }) => {
    await page.context().addCookies([
      {
        name: "lms_session",
        value: "e2e_student_session",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.route("**/api/v1/enrollments*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          size: 20,
        }),
      });
    });

    await page.goto("/app/courses");

    await expect(page.getByRole("heading", { name: /My Enrolled Courses/i })).toBeVisible();
    await expect(page.getByText(/No Enrolled Courses Found/i)).toBeVisible();
  });
});
