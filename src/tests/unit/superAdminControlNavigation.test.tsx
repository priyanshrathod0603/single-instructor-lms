import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StaffAdminSidebar } from "@/components/navigation/StaffAdminSidebar";
import AdminDashboardPage from "@/app/(admin)/admin/page";
import { useAuth } from "@/lib/hooks/useAuth";
import { requireServerAuth } from "@/lib/auth/serverAuth";

// Mock next/navigation
const mockUsePathname = vi.fn();
const mockRedirect = vi.fn((url: string) => {
  const err = new Error(`NEXT_REDIRECT: ${url}`);
  (err as any).digest = `NEXT_REDIRECT;replace;${url};307;;`;
  throw err;
});

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  redirect: (url: string) => mockRedirect(url),
}));

// Mock useAuth hook
vi.mock("@/lib/hooks/useAuth", () => ({
  useAuth: vi.fn(),
}));

// Mock API clients for AdminDashboardPage
vi.mock("@/lib/api/courses", () => ({
  coursesApi: {
    listManageCourses: vi.fn().mockResolvedValue({ total: 5, items: [{ status: "PUBLISHED" }] }),
  },
}));

vi.mock("@/lib/api/enrollments", () => ({
  enrollmentsApi: {
    listAllEnrollments: vi.fn().mockResolvedValue({ total: 10, items: [] }),
  },
}));

vi.mock("@/lib/api/orders", () => ({
  ordersApi: {
    listAllOrders: vi.fn().mockResolvedValue({ total: 8, items: [] }),
  },
}));

vi.mock("@/lib/api/users", () => ({
  usersApi: {
    listUsers: vi.fn().mockResolvedValue({ total: 20, items: [] }),
  },
}));

const mockGetCookie = vi.fn();
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: mockGetCookie,
  })),
}));

describe("Super Admin Control Portal Access from Admin Console", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePathname.mockReturnValue("/admin");
    mockGetCookie.mockReturnValue({ value: "valid-session-token" });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  function renderWithQueryClient(ui: React.ReactElement) {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
  }

  describe("Sidebar Navigation (StaffAdminSidebar)", () => {
    it("renders 'Super Admin Control' linking to /control when user has SUPER_ADMIN role", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "super-user-1",
          email: "superadmin@example.com",
          full_name: "Super Administrator",
          is_verified: true,
          is_active: true,
          roles: ["SUPER_ADMIN"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => true,
        hasAnyRole: () => true,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      // Verify all desktop and mobile navigation links include 'Super Admin Control'
      const controlLinks = screen.getAllByRole("link", { name: /super admin control/i });
      expect(controlLinks.length).toBeGreaterThanOrEqual(1);
      controlLinks.forEach((link) => {
        expect(link).toHaveAttribute("href", "/control");
      });

      // Verify all existing admin navigation items are preserved
      expect(screen.getAllByRole("link", { name: /dashboard/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /course management/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /media library/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /student roster/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /enrollment grants/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /financial ledger/i }).length).toBeGreaterThanOrEqual(1);
    });

    it("does NOT render 'Super Admin Control' for ordinary ADMIN user", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "admin-user-1",
          email: "admin@example.com",
          full_name: "Operations Admin",
          is_verified: true,
          is_active: true,
          roles: ["ADMIN"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => true,
        hasAnyRole: () => true,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      expect(screen.queryByRole("link", { name: /super admin control/i })).not.toBeInTheDocument();

      // Verify existing admin navigation items still present
      expect(screen.getAllByRole("link", { name: /dashboard/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /course management/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /media library/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /student roster/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /enrollment grants/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole("link", { name: /financial ledger/i }).length).toBeGreaterThanOrEqual(1);
    });

    it("does NOT render 'Super Admin Control' for STAFF user", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "staff-user-1",
          email: "staff@example.com",
          full_name: "Staff Grader",
          is_verified: true,
          is_active: true,
          roles: ["STAFF"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => false,
        hasAnyRole: () => false,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<StaffAdminSidebar portal="staff" />);

      expect(screen.queryByRole("link", { name: /super admin control/i })).not.toBeInTheDocument();
      expect(screen.getAllByRole("link", { name: /grading queue/i }).length).toBeGreaterThanOrEqual(1);
    });

    it("does NOT render 'Super Admin Control' for STUDENT user", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "student-user-1",
          email: "student@example.com",
          full_name: "Enrolled Student",
          is_verified: true,
          is_active: true,
          roles: ["STUDENT"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => false,
        hasAnyRole: () => false,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      expect(screen.queryByRole("link", { name: /super admin control/i })).not.toBeInTheDocument();
    });

    it("does NOT render 'Super Admin Control' when user is unauthenticated", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => false,
        hasAnyRole: () => false,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      expect(screen.queryByRole("link", { name: /super admin control/i })).not.toBeInTheDocument();
    });
  });

  describe("Dashboard Navigation Header (AdminDashboardPage)", () => {
    it("renders 'Super Admin Control' button in header for SUPER_ADMIN", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "super-user-1",
          email: "superadmin@example.com",
          full_name: "Super Administrator",
          is_verified: true,
          is_active: true,
          roles: ["SUPER_ADMIN"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => true,
        hasAnyRole: () => true,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<AdminDashboardPage />);

      const controlLink = screen.getByRole("link", { name: /super admin control/i });
      expect(controlLink).toBeInTheDocument();
      expect(controlLink).toHaveAttribute("href", "/control");

      // Verify Create New Course button remains intact
      expect(screen.getByRole("button", { name: /create new course/i })).toBeInTheDocument();
    });

    it("does NOT render 'Super Admin Control' button on dashboard for ordinary ADMIN", () => {
      vi.mocked(useAuth).mockReturnValue({
        user: {
          id: "admin-user-1",
          email: "admin@example.com",
          full_name: "Operations Admin",
          is_verified: true,
          is_active: true,
          roles: ["ADMIN"],
          created_at: "2026-11-10T12:00:00Z",
        },
        isAuthenticated: true,
        isLoading: false,
        logout: vi.fn(),
        isLoggingOut: false,
        hasRole: () => true,
        hasAnyRole: () => true,
        isDisplacedSession: false,
        displacementReason: null,
        refetchUser: vi.fn(),
        dismissDisplacement: vi.fn(),
      });

      renderWithQueryClient(<AdminDashboardPage />);

      expect(screen.queryByRole("link", { name: /super admin control/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /create new course/i })).toBeInTheDocument();
    });
  });

  describe("Independent Server-Side Authorization Enforcement (requireServerAuth)", () => {
    it("authorizes SUPER_ADMIN accessing /control layout", async () => {
      const superAdminUser = {
        id: "super-1",
        email: "super@example.com",
        full_name: "Super Admin",
        is_active: true,
        roles: ["SUPER_ADMIN"],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => superAdminUser,
      });

      const user = await requireServerAuth({
        requiredRole: "SUPER_ADMIN",
        redirectUrl: "/control",
      });

      expect(user).toEqual(superAdminUser);
    });

    it("rejects ordinary ADMIN attempting to access /control layout with 403 redirect to /app?error=forbidden", async () => {
      const adminUser = {
        id: "admin-1",
        email: "admin@example.com",
        full_name: "Operations Admin",
        is_active: true,
        roles: ["ADMIN"],
      };

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => adminUser,
      });

      await expect(
        requireServerAuth({
          requiredRole: "SUPER_ADMIN",
          redirectUrl: "/control",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /app?error=forbidden");
    });

    it("rejects STAFF user attempting to access /control layout", async () => {
      const staffUser = {
        id: "staff-1",
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

      await expect(
        requireServerAuth({
          requiredRole: "SUPER_ADMIN",
          redirectUrl: "/control",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /app?error=forbidden");
    });

    it("rejects STUDENT user attempting to access /control layout", async () => {
      const studentUser = {
        id: "student-1",
        email: "student@example.com",
        full_name: "Learner",
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
          requiredRole: "SUPER_ADMIN",
          redirectUrl: "/control",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /app?error=forbidden");
    });

    it("redirects unauthenticated user accessing /control to /login", async () => {
      mockGetCookie.mockReturnValue(undefined);

      await expect(
        requireServerAuth({
          requiredRole: "SUPER_ADMIN",
          redirectUrl: "/control",
        })
      ).rejects.toThrow("NEXT_REDIRECT: /login?redirect=%2Fcontrol");
    });
  });
});
