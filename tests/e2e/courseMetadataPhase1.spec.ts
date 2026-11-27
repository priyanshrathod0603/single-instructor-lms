import { test, expect } from "@playwright/test";

// Minimal valid 1x1 transparent PNG (with valid IHDR)
const VALID_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
const VALID_PNG_BUFFER = Buffer.from(VALID_PNG_BASE64, "base64");

test.describe("Phase 1 E2E: Course Creation, Metadata Management, Thumbnail & Responsive UI", () => {
  test("Complete create -> thumbnail upload -> edit -> listing -> persistence & responsive check", async ({
    context,
    page,
  }) => {
    const adminCookie = {
      name: "lms_session",
      value: "e2e_admin_session",
      domain: "localhost",
      path: "/",
      httpOnly: true,
      secure: false,
    };
    await context.addCookies([adminCookie]);

    // Stateful in-memory backend store for Playwright route interception
    const courses: any[] = [];
    const mediaAssets: Record<string, any> = {};

    await page.route("**/api/v1/media/**", async (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const path = url.pathname;
      const method = req.method();

      if (method === "POST" && path === "/api/v1/media/upload-intent") {
        const body = req.postDataJSON();
        const mediaId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
        const fileKey = `public-images/admin/${body.filename}`;
        mediaAssets[mediaId] = {
          id: mediaId,
          uploader_id: "admin-1",
          filename: body.filename,
          file_key: fileKey,
          bucket: "lms-media",
          mime_type: body.mime_type,
          file_size_bytes: body.file_size_bytes,
          status: "UPLOADING",
          public_url: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            media_id: mediaId,
            file_key: fileKey,
            bucket: "lms-media",
            presigned_url: `/api/v1/media/storage/upload/${fileKey}`,
            headers: { "Content-Type": body.mime_type },
            expires_in_seconds: 900,
          }),
        });
        return;
      }

      if (method === "PUT" && path.startsWith("/api/v1/media/storage/upload/")) {
        await route.fulfill({ status: 200, body: "" });
        return;
      }

      if (method === "POST" && path.endsWith("/confirm")) {
        const parts = path.split("/");
        const mediaId = parts[parts.length - 2];
        const asset = mediaAssets[mediaId];
        asset.status = "READY";
        asset.public_url = `/api/v1/media/public/${mediaId}`;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(asset),
        });
        return;
      }

      if (method === "GET" && path.startsWith("/api/v1/media/public/")) {
        await route.fulfill({
          status: 200,
          contentType: "image/png",
          headers: { "X-Content-Type-Options": "nosniff" },
          body: VALID_PNG_BUFFER,
        });
        return;
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });

    await page.route("**/api/v1/courses**", async (route) => {
      const req = route.request();
      const url = new URL(req.url());
      const path = url.pathname;
      const method = req.method();

      if (method === "GET" && path === "/api/v1/courses/metadata-options") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            categories: ["Web Development", "System Design", "Backend Engineering", "General"],
            difficulty_levels: [
              { value: "BEGINNER", label: "Beginner" },
              { value: "INTERMEDIATE", label: "Intermediate" },
              { value: "ADVANCED", label: "Advanced" },
              { value: "ALL_LEVELS", label: "All Levels" },
            ],
            languages: ["English", "Hindi", "Hinglish"],
            currencies: ["INR"],
          }),
        });
        return;
      }

      if (method === "GET" && path === "/api/v1/courses/slug-available") {
        const slug = (url.searchParams.get("slug") || "").toLowerCase();
        const excludeId = url.searchParams.get("exclude_course_id");
        const exists = courses.some((c) => c.slug === slug && c.id !== excludeId);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            slug,
            available: !exists,
            reason: exists ? "This URL slug is already used by another course." : null,
          }),
        });
        return;
      }

      if (method === "GET" && path === "/api/v1/courses/manage") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: courses,
            total: courses.length,
            page: 1,
            per_page: 20,
            total_pages: courses.length > 0 ? 1 : 0,
          }),
        });
        return;
      }

      if (method === "POST" && path === "/api/v1/courses") {
        const body = req.postDataJSON();
        const id = "11111111-1111-1111-1111-111111111111";
        const discountPct =
          !body.is_free && body.compare_at_price_inr && body.compare_at_price_inr > body.price_inr
            ? Math.round(
                ((body.compare_at_price_inr - body.price_inr) / body.compare_at_price_inr) * 100,
              )
            : null;
        const created = {
          id,
          slug: body.slug,
          title: body.title,
          headline: body.headline || null,
          description: body.description || null,
          thumbnail_url: body.thumbnail_url || null,
          thumbnail_media_id: body.thumbnail_media_id || null,
          category: body.category || "General",
          difficulty_level: body.difficulty_level || "ALL_LEVELS",
          language: body.language || "English",
          learning_outcomes: body.learning_outcomes || [],
          requirements: body.requirements || [],
          status: "DRAFT",
          price_inr: body.price_inr ?? 0,
          compare_at_price_inr: body.compare_at_price_inr ?? null,
          currency: body.currency || "INR",
          discount_percentage: discountPct,
          is_free: Boolean(body.is_free),
          tags: body.tags || [],
          live_revision_id: null,
          draft_revision_id: "rev-1",
          latest_revision_id: "rev-1",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          curriculum: [],
        };
        courses.push(created);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(created),
        });
        return;
      }

      if (method === "GET" && path.startsWith("/api/v1/courses/")) {
        const segments = path.split("/");
        const id = segments[segments.length - 1];
        if (path.includes("/revisions/")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              id: "rev-1",
              course_id: courses[0]?.id,
              revision_no: 1,
              status: "DRAFT",
              title: "Draft 1",
              price_inr: courses[0]?.price_inr || 0,
              is_free: courses[0]?.is_free || false,
              tags: courses[0]?.tags || [],
              sections: [],
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            }),
          });
          return;
        }
        const found = courses.find((c) => c.id === id || c.slug === id);
        await route.fulfill({
          status: found ? 200 : 404,
          contentType: "application/json",
          body: JSON.stringify(found || { message: "Not found" }),
        });
        return;
      }

      if (method === "PATCH" && path.startsWith("/api/v1/courses/")) {
        const id = path.split("/").pop();
        const found = courses.find((c) => c.id === id);
        const body = req.postDataJSON();
        Object.assign(found, body);
        found.discount_percentage =
          !found.is_free &&
          found.compare_at_price_inr &&
          found.compare_at_price_inr > found.price_inr
            ? Math.round(
                ((found.compare_at_price_inr - found.price_inr) / found.compare_at_price_inr) * 100,
              )
            : null;
        found.updated_at = new Date().toISOString();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(found),
        });
        return;
      }

      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });

    // Step 1-2: Open /admin/courses and navigate to Create New Course
    await page.goto("/admin/courses");
    await expect(page.getByRole("heading", { name: /Course Management Directory/i })).toBeVisible();
    await page.getByRole("button", { name: /Create New Course/i }).click();
    await expect(page).toHaveURL("/admin/courses/new");

    // Step 3-4: Fill basic course details and check auto-slug
    await page.getByLabel(/Course Title/i).fill("Distributed Systems Architecture");
    await expect(page.getByLabel(/Course URL Slug/i)).toHaveValue(
      "distributed-systems-architecture",
    );
    await page
      .getByLabel(/Short Subtitle \/ Headline/i)
      .fill("Build fault-tolerant APIs and event pipelines");
    await page
      .getByLabel(/Full Course Description/i)
      .fill("Deep practical guide to replication, sharding, and queues.");
    await page.getByLabel(/^Category/i).selectOption("System Design");
    await page.getByLabel(/Difficulty Level/i).selectOption("INTERMEDIATE");
    await page.getByLabel(/Primary Instruction Language/i).selectOption("Hinglish");

    // Add tag
    const tagInput = page.getByLabel(/Discovery Tags/i);
    await tagInput.fill("distributed-systems");
    await tagInput.press("Enter");
    await expect(page.getByText("#distributed-systems")).toBeVisible();

    // Step 5: Upload valid PNG thumbnail
    await page.getByLabel("Upload course thumbnail image").setInputFiles({
      name: "course-cover.png",
      mimeType: "image/png",
      buffer: VALID_PNG_BUFFER,
    });
    await expect(page.getByAltText(/thumbnail preview/i)).toBeVisible();

    // Step 6-7: Add learning outcomes & course requirements
    await page.getByLabel("Learning Outcomes").fill("Architect durable queues");
    await page.getByRole("button", { name: /Add Outcome/i }).click();
    await page.getByLabel("Course Requirements").fill("Intermediate Python or Go");
    await page.getByRole("button", { name: /Add Requirement/i }).click();

    // Step 8: Configure regular & discounted INR prices
    await page.getByLabel(/Regular Price \(INR\)/i).fill("7999");
    await page.getByLabel(/Discounted Selling Price/i).fill("2999");
    await expect(page.getByText("63% OFF")).toBeVisible();

    // Step 9: Save course as draft -> navigates to edit screen
    await page.getByRole("button", { name: /Save Draft Course/i }).click();
    await expect(page).toHaveURL(/\/admin\/courses\/11111111-1111-1111-1111-111111111111\/edit/);

    // Step 10: Return to /admin/courses listing and locate created course (works for both desktop table and mobile cards)
    await page.goto("/admin/courses");
    await expect(
      page.getByText("Distributed Systems Architecture").and(page.locator(":visible")).first(),
    ).toBeVisible();
    await expect(page.getByText("₹2,999").and(page.locator(":visible")).first()).toBeVisible();

    // Step 11-13: Open Edit Course -> modify metadata -> Save
    await page.getByRole("link", { name: /Edit Course/i }).and(page.locator(":visible")).first().click();
    await expect(page).toHaveURL(/\/edit\?tab=metadata/);
    await expect(page.getByLabel(/Course Title/i)).toHaveValue("Distributed Systems Architecture");

    await page.getByLabel(/Course Title/i).fill("Distributed Systems Architecture Updated");
    await page.getByRole("button", { name: /Save Course Changes/i }).click();
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();

    // Step 14: Reload and verify persistence
    await page.reload();
    await expect(page.getByLabel(/Course Title/i)).toHaveValue(
      "Distributed Systems Architecture Updated",
    );

    // Responsive check across all required viewports (zero horizontal overflow)
    for (const width of [320, 375, 390, 430, 768, 1024, 1280, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      expect(overflow, `Horizontal overflow detected at ${width}px on edit page`).toBe(false);
    }

    await page.goto("/admin/courses");
    for (const width of [320, 375, 768, 1280]) {
      await page.setViewportSize({ width, height: 800 });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      expect(overflow, `Horizontal overflow detected at ${width}px on /admin/courses`).toBe(false);
    }
  });
});
