import { describe, it, expect } from "vitest";
import { getSafeRedirectUrl } from "@/lib/security/redirect";

describe("P0-01: Safe Redirect Security Validation (Anti-XSS & Open Redirect)", () => {
  it("allows valid internal routes", () => {
    expect(getSafeRedirectUrl("/app")).toBe("/app");
    expect(getSafeRedirectUrl("/admin")).toBe("/admin");
    expect(getSafeRedirectUrl("/courses")).toBe("/courses");
  });

  it("allows valid nested internal routes with query params and hashes", () => {
    expect(getSafeRedirectUrl("/app/courses/course-123")).toBe("/app/courses/course-123");
    expect(getSafeRedirectUrl("/learn/c1/l1?tab=notes&speed=1.5#section-2")).toBe(
      "/learn/c1/l1?tab=notes&speed=1.5#section-2"
    );
    expect(getSafeRedirectUrl("/control/users?page=2&status=ACTIVE")).toBe(
      "/control/users?page=2&status=ACTIVE"
    );
  });

  it("rejects external HTTP and HTTPS URLs", () => {
    expect(getSafeRedirectUrl("http://evil.com")).toBe("/app");
    expect(getSafeRedirectUrl("https://evil.com/phishing")).toBe("/app");
    expect(getSafeRedirectUrl("http://localhost:3000/app")).toBe("/app");
    expect(getSafeRedirectUrl("https://google.com")).toBe("/app");
  });

  it("rejects protocol-relative URLs", () => {
    expect(getSafeRedirectUrl("//evil.com")).toBe("/app");
    expect(getSafeRedirectUrl("//evil.com/path")).toBe("/app");
    expect(getSafeRedirectUrl("///evil.com")).toBe("/app");
  });

  it("rejects javascript: schemes (XSS)", () => {
    expect(getSafeRedirectUrl("javascript:alert(1)")).toBe("/app");
    expect(getSafeRedirectUrl("JAVASCRIPT:alert(document.cookie)")).toBe("/app");
    expect(getSafeRedirectUrl("/javascript:alert(1)")).toBe("/app");
    expect(getSafeRedirectUrl("javascript://test%0Aalert(1)")).toBe("/app");
  });

  it("rejects data: and vbscript: schemes", () => {
    expect(getSafeRedirectUrl("data:text/html,<script>alert(1)</script>")).toBe("/app");
    expect(getSafeRedirectUrl("DATA:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==")).toBe(
      "/app"
    );
    expect(getSafeRedirectUrl("vbscript:msgbox(1)")).toBe("/app");
    expect(getSafeRedirectUrl("blob:https://evil.com/uuid")).toBe("/app");
    expect(getSafeRedirectUrl("file:///etc/passwd")).toBe("/app");
  });

  it("rejects Windows backslash and path traversal tricks", () => {
    expect(getSafeRedirectUrl("/\\evil.com")).toBe("/app");
    expect(getSafeRedirectUrl("\\evil.com")).toBe("/app");
    expect(getSafeRedirectUrl("/evil.com\\path")).toBe("/app");
  });

  it("rejects CRLF, control characters, and null bytes", () => {
    expect(getSafeRedirectUrl("/app\r\nSet-Cookie: evil=1")).toBe("/app");
    expect(getSafeRedirectUrl("/app\x00evil")).toBe("/app");
    expect(getSafeRedirectUrl("/app\t/evil")).toBe("/app");
  });

  it("falls back to default route on empty, null, or malformed input", () => {
    expect(getSafeRedirectUrl("")).toBe("/app");
    expect(getSafeRedirectUrl("   ")).toBe("/app");
    expect(getSafeRedirectUrl(null)).toBe("/app");
    expect(getSafeRedirectUrl(undefined)).toBe("/app");
    expect(getSafeRedirectUrl("not-a-path")).toBe("/app");
  });

  it("honors custom fallback route when provided", () => {
    expect(getSafeRedirectUrl("https://evil.com", "/dashboard")).toBe("/dashboard");
    expect(getSafeRedirectUrl("javascript:void(0)", "/login")).toBe("/login");
  });
});
