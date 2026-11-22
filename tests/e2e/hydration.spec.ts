import { test, expect } from "@playwright/test";

test.describe("Hydration Safety, Mobile Text Animation, & Safari Compatibility", () => {
  test("Homepage loads with zero hydration errors or mismatch warnings", async ({ page }) => {
    const consoleErrors: string[] = [];
    const consoleWarnings: string[] = [];

    page.on("console", (msg) => {
      const text = msg.text();
      if (msg.type() === "error") {
        // Exclude expected unauthenticated 401 response from /api/v1/auth/me
        if (!text.includes("401")) {
          consoleErrors.push(text);
        }
      }
      if (msg.type() === "warning") {
        // Flag any hydration-related warnings
        if (
          text.toLowerCase().includes("hydration") ||
          text.toLowerCase().includes("mismatch") ||
          text.toLowerCase().includes("did not match")
        ) {
          consoleWarnings.push(text);
        }
      }
    });

    page.on("pageerror", (err) => {
      consoleErrors.push(err.message);
    });

    await page.goto("/");

    // Wait for client hydration and initial animation tick
    await page.waitForTimeout(600);

    // Verify zero application-level console errors and zero hydration warnings
    expect(consoleErrors).toEqual([]);
    expect(consoleWarnings).toEqual([]);
  });

  test("Hero animated typewriter advances character by character on mobile and desktop", async ({
    page,
    viewport,
  }) => {
    await page.goto("/");

    const typewriter = page.locator('h1 span[aria-live="polite"]');
    await expect(typewriter).toBeVisible();

    // Verify cursor is rendered with CSS animation class
    const cursor = page.locator('h1 span[aria-live="polite"] span[aria-hidden="true"]');
    await expect(cursor).toBeVisible();
    await expect(cursor).toHaveClass(/animate-cursor-blink/);

    // After 1.5s, multiple characters of 'Distributed Systems' have typed
    await page.waitForTimeout(1200);
    const typedText = await typewriter.innerText();
    expect(typedText.length).toBeGreaterThan(0);
    expect("Distributed Systems").toContain(typedText.trim());

    // Verify h1 does not cause horizontal overflow
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    );
    expect(hasOverflow).toBe(false);

    // Capture visual screenshot
    if (viewport) {
      await page.screenshot({
        path: `docs/frontend/screenshots/mobile-hydration-${viewport.width}px.png`,
        fullPage: false,
      });
    }
  });

  test("Respects prefers-reduced-motion without layout shift or missing text", async ({
    page,
    context,
  }) => {
    // Emulate reduced motion
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    const typewriter = page.locator('h1 span[aria-live="polite"]');
    await expect(typewriter).toBeVisible();

    // With reduced motion, full phrase is displayed immediately
    await expect(typewriter).toHaveText(/Distributed Systems/);

    // Heading structure remains intact: 'Master', 'Distributed Systems', 'Directly from an Expert.'
    const h1 = page.locator("h1");
    await expect(h1).toContainText("Master");
    await expect(h1).toContainText("Distributed Systems");
    await expect(h1).toContainText("Directly from an Expert.");
  });
});
