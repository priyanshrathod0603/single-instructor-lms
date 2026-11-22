import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { requireServerAuth } from "@/lib/auth/serverAuth";

const mockRedirect = vi.fn((url: string) => {
  const err = new Error(`NEXT_REDIRECT: ${url}`);
  (err as any).digest = `NEXT_REDIRECT;replace;${url};307;;`;
  throw err;
});

const mockGetCookie = vi.fn();

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: mockGetCookie,
  })),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => mockRedirect(url),
}));

describe("requireServerAuth & Staff Role Guard (FIX-02)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCookie.mockReturnValue({ value: "valid-session-token" });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("redirects to login if session cookie is missing", async () => {
    mockGetCookie.mockReturnValue(undefined);

    await expect(requireServerAuth({ redirectUrl: "/staff" })).rejects.toThrow(
      "NEXT_REDIRECT: /login?redirect=%2Fstaff"
    );
  });

  it("authorizes a user with canonical STAFF role for staff-protected layout", async () => {
    const staffUser = {
      id: "user-staff-1",
      email: "staff@example.com",
      full_name: "Staff Grader",
      is_active: true,
      roles: ["STAFF"],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => staffUser,
    });

    const user = await requireServerAuth({
      requiredRole: "STAFF",
      redirectUrl: "/staff",
    });

    expect(user).toEqual(staffUser);
  });

  it("authorizes an ADMIN accessing the STAFF layout", async () => {
    const adminUser = {
      id: "user-admin-1",
      email: "admin@example.com",
      full_name: "Course Instructor",
      is_active: true,
      roles: ["ADMIN"],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => adminUser,
    });

    const user = await requireServerAuth({
      requiredRole: "STAFF",
      redirectUrl: "/staff",
    });

    expect(user).toEqual(adminUser);
  });

  it("authorizes a SUPER_ADMIN for any required role", async () => {
    const superAdmin = {
      id: "user-root-1",
      email: "root@example.com",
      full_name: "Super Administrator",
      is_active: true,
      roles: ["SUPER_ADMIN"],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => superAdmin,
    });

    const user = await requireServerAuth({
      requiredRole: "STAFF",
      redirectUrl: "/staff",
    });

    expect(user).toEqual(superAdmin);
  });

  it("rejects unauthorized STUDENT attempting to access STAFF portal with forbidden redirect", async () => {
    const studentUser = {
      id: "user-student-1",
      email: "student@example.com",
      full_name: "Enrolled Student",
      is_active: true,
      roles: ["STUDENT"],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => studentUser,
    });

    await expect(
      requireServerAuth({
        requiredRole: "STAFF",
        redirectUrl: "/staff",
      })
    ).rejects.toThrow("NEXT_REDIRECT: /app?error=forbidden");
  });

  it("rejects inactive users even if they hold the STAFF role", async () => {
    const inactiveStaff = {
      id: "user-staff-2",
      email: "banned-staff@example.com",
      full_name: "Deactivated Staff",
      is_active: false,
      roles: ["STAFF"],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => inactiveStaff,
    });

    await expect(
      requireServerAuth({
        requiredRole: "STAFF",
        redirectUrl: "/staff",
      })
    ).rejects.toThrow("NEXT_REDIRECT: /login?redirect=%2Fstaff");
  });

  describe("P0-02: Production E2E Authentication Bypass Prevention", () => {
    const originalEnv = process.env.NODE_ENV;
    const originalEnableE2E = process.env.ENABLE_E2E_AUTH;

    afterEach(() => {
      (process.env as Record<string, string | undefined>).NODE_ENV = originalEnv;
      process.env.ENABLE_E2E_AUTH = originalEnableE2E;
    });

    it("strictly rejects e2e_super cookie in production and falls through to backend verification", async () => {
      (process.env as Record<string, string | undefined>).NODE_ENV = "production";
      delete process.env.ENABLE_E2E_AUTH;
      mockGetCookie.mockReturnValue({ value: "e2e_super_admin_session" });

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: { code: "UNAUTHORIZED", message: "Invalid session" } }),
      });

      await expect(
        requireServerAuth({
          requiredRole: "SUPER_ADMIN",
          redirectUrl: "/control",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /login?redirect=%2Fcontrol");

      // Verify it did NOT grant synthetic identity and instead called the backend
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it("strictly rejects e2e_admin and e2e_student in production", async () => {
      (process.env as Record<string, string | undefined>).NODE_ENV = "production";
      delete process.env.ENABLE_E2E_AUTH;
      mockGetCookie.mockReturnValue({ value: "e2e_admin_session" });

      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: { code: "UNAUTHORIZED" } }),
      });

      await expect(
        requireServerAuth({
          requiredRole: "ADMIN",
          redirectUrl: "/admin",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /login?redirect=%2Fadmin");
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it("allows synthetic E2E identity in isolated test environment", async () => {
      (process.env as Record<string, string | undefined>).NODE_ENV = "test";
      mockGetCookie.mockReturnValue({ value: "e2e_super_admin_session" });
      global.fetch = vi.fn();

      const user = await requireServerAuth({
        requiredRole: "SUPER_ADMIN",
        redirectUrl: "/control",
      });

      expect(user.id).toBe("e2e-user-uuid");
      expect(user.roles).toContain("SUPER_ADMIN");
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });
});
