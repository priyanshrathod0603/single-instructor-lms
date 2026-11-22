import { test, expect } from "@playwright/test";

test.describe("Admin & Instructor Experience (Part 5)", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept client-side API requests to prevent unhandled localhost:8000 hangs in CI/E2E
    await page.route("**/api/v1/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          per_page: 20,
          size: 20,
          total_pages: 0,
        }),
      });
    });
  });

  // ---------------------------------------------------------------------------
  // 1. Authorization & Route Guards
  // ---------------------------------------------------------------------------
  test("Unauthenticated user is redirected to login when accessing /admin", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login\?redirect=%2Fadmin/);
  });

  test("Unauthenticated user is redirected to login when accessing /staff", async ({ page }) => {
    await page.goto("/staff");
    await expect(page).toHaveURL(/\/login\?redirect=%2Fstaff/);
  });

  test("Unauthenticated user is redirected to login when accessing /control", async ({ page }) => {
    await page.goto("/control");
    await expect(page).toHaveURL(/\/login\?redirect=%2Fcontrol/);
  });

  test("Unauthorized student is blocked with error=forbidden when accessing /admin", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_student_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/admin");
    await expect(page).toHaveURL(/\/app\?error=forbidden/);
  });

  // ---------------------------------------------------------------------------
  // 2. Staff Portal Experience
  // ---------------------------------------------------------------------------
  test("Staff user accesses /staff and renders Staff Workspace and Queue", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_staff_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/staff");
    await expect(
      page.getByRole("heading", { name: /Teaching Assistant & Staff Workspace/i })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Open Grading Queue/i })).toBeVisible();

    // Navigate to Grading Queue
    await page.getByRole("button", { name: /Open Grading Queue/i }).click();
    await expect(page).toHaveURL("/staff/grading");
    await expect(page.getByRole("heading", { name: /Staff Grading Queue/i })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. Admin Portal Experience & Operations Console
  // ---------------------------------------------------------------------------
  test("Admin user accesses /admin and renders Operations Console with metrics", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_admin_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: /Instructor Operations Console/i })
    ).toBeVisible();
    await expect(page.getByText(/Total Courses/i)).toBeVisible();
    await expect(page.getByText(/Active Enrollments/i)).toBeVisible();
    await expect(page.getByText(/Gross Sales/i)).toBeVisible();
  });

  test("Admin user navigates to Course Management and New Course flow", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_admin_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/admin/courses");
    await expect(
      page.getByRole("heading", { name: /Course Management Directory/i })
    ).toBeVisible();

    // Click Create New Course
    await page.getByRole("button", { name: /Create New Course/i }).click();
    await expect(page).toHaveURL("/admin/courses/new");
    await expect(
      page.getByRole("heading", { name: /Create Course Entity/i })
    ).toBeVisible();
    await expect(page.getByPlaceholder(/Master Class: Modern Scalable Architecture/i)).toBeVisible();
  });

  test("Admin user accesses Media Library and Roster pages", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_admin_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    // Media Library
    await page.goto("/admin/media");
    await expect(
      page.getByRole("heading", { name: /Media & Storage Management/i })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Upload to Private Storage/i })).toBeVisible();

    // Student Roster
    await page.goto("/admin/students");
    await expect(
      page.getByRole("heading", { name: /Student Roster & User Governance/i })
    ).toBeVisible();

    // Enrollment Grants
    await page.goto("/admin/enrollments");
    await expect(
      page.getByRole("heading", { name: /Student Enrollment Governance/i })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Grant Manual Enrollment/i })).toBeVisible();

    // Financial Ledger
    await page.goto("/admin/orders");
    await expect(
      page.getByRole("heading", { name: /Commercial Financial Ledger/i })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. Super Admin Control Portal Experience
  // ---------------------------------------------------------------------------
  test("Super Admin user accesses /control and views security governance", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_super_admin_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/control");
    await expect(
      page.getByRole("heading", { name: /Super Administrator Governance/i })
    ).toBeVisible();
    await expect(page.getByText(/Audit Events Recorded/i)).toBeVisible();

    // Permissions Matrix
    await page.goto("/control/permissions");
    await expect(
      page.getByRole("heading", { name: /Role-Based Access Control \(RBAC\) Matrix/i })
    ).toBeVisible();
    await expect(page.getByText(/course:view_public/i)).toBeVisible();

    // Audit Logs
    await page.goto("/control/audit");
    await expect(
      page.getByRole("heading", { name: /Immutable Security Audit Trail/i })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Responsive Verification (Mobile Drawers & Layouts)
  // ---------------------------------------------------------------------------
  test("Mobile viewport (375x667): renders top header, toggle navigation, and zero overflow", async ({
    context,
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    await context.addCookies([
      {
        name: "lms_session",
        value: "e2e_admin_session",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        secure: false,
      },
    ]);

    await page.goto("/admin");

    // Check top mobile bar
    await expect(page.getByText(/Admin Console/i).first()).toBeVisible();
    const menuBtn = page.getByRole("button", { name: /Open navigation/i });
    await expect(menuBtn).toBeVisible();

    // Open mobile menu
    await menuBtn.click();
    await expect(page.getByRole("link", { name: /Course Management/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Financial Ledger/i })).toBeVisible();

    // Verify zero horizontal scroll overflow
    const hasHorizontalOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(hasHorizontalOverflow).toBe(false);
  });
});
