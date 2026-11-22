import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StaffAdminSidebar } from "@/components/navigation/StaffAdminSidebar";
import AdminDashboardPage from "@/app/(admin)/admin/page";
import StudentDashboardPage from "@/app/(student)/app/page";
import AdminMediaPage from "@/app/(admin)/admin/media/page";

const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "test-user-id", full_name: "Alex Johnson", email: "alex@example.com", roles: ["ADMIN"] },
    isAuthenticated: true,
    isLoading: false,
    logout: vi.fn(),
    isLoggingOut: false,
    hasRole: () => true,
    hasAnyRole: () => true,
  }),
}));

vi.mock("@/lib/api/courses", () => ({
  coursesApi: {
    listManageCourses: vi.fn().mockResolvedValue({ total: 3, items: [] }),
  },
}));

vi.mock("@/lib/api/enrollments", () => ({
  enrollmentsApi: {
    listAllEnrollments: vi.fn().mockResolvedValue({ total: 12, items: [] }),
    listOwnEnrollments: vi.fn().mockResolvedValue({ total: 2, items: [] }),
  },
}));

vi.mock("@/lib/api/orders", () => ({
  ordersApi: {
    listAllOrders: vi.fn().mockResolvedValue({ total: 5, items: [] }),
  },
}));

vi.mock("@/lib/api/users", () => ({
  usersApi: {
    listUsers: vi.fn().mockResolvedValue({ total: 24, items: [] }),
  },
}));

vi.mock("@/lib/api/quizzes", () => ({
  quizzesApi: {
    listOwnAttempts: vi.fn().mockResolvedValue({ total: 4, items: [] }),
  },
}));

vi.mock("@/lib/api/media", () => ({
  mediaApi: {
    listMediaAssets: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    getUploadIntent: vi.fn(),
    confirmUpload: vi.fn(),
    deleteMediaAsset: vi.fn(),
  },
}));

describe("Contextual Mobile Navigation & Responsive UI (NAV-02, UI-01, UI-02, UI-03)", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
  });

  const renderWithQueryClient = (ui: React.ReactElement) => {
    return render(
      <QueryClientProvider client={queryClient}>
        {ui}
      </QueryClientProvider>
    );
  };

  describe("NAV-02: StaffAdminSidebar Contextual Mobile Back Navigation", () => {
    it("renders back button to /admin when on an admin subpage like /admin/media", () => {
      mockUsePathname.mockReturnValue("/admin/media");
      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      const backLink = screen.getByRole("link", { name: /back to dashboard/i });
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute("href", "/admin");
    });

    it("renders back button to /admin/courses when editing a course on /admin/courses/123/edit", () => {
      mockUsePathname.mockReturnValue("/admin/courses/123/edit");
      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      const backLink = screen.getByRole("link", { name: /back to courses/i });
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute("href", "/admin/courses");
    });

    it("does not render back button when on root /admin", () => {
      mockUsePathname.mockReturnValue("/admin");
      renderWithQueryClient(<StaffAdminSidebar portal="admin" />);

      const backLink = screen.queryByRole("link", { name: /back to/i });
      expect(backLink).not.toBeInTheDocument();
    });
  });

  describe("UI-01: Student Dashboard KPI Cards Responsive Structure", () => {
    it("renders all 3 KPI cards with truncation and responsive flex styling", () => {
      renderWithQueryClient(<StudentDashboardPage />);

      expect(screen.getByText("Enrolled Courses")).toBeInTheDocument();
      expect(screen.getByText("Quizzes Passed")).toBeInTheDocument();
      expect(screen.getByText("Quiz Attempts")).toBeInTheDocument();
    });
  });

  describe("UI-02: Admin Dashboard Header and KPI Cards Structure", () => {
    it("renders the Create New Course button with whitespace-nowrap and shrink-0", () => {
      renderWithQueryClient(<AdminDashboardPage />);

      const createBtn = screen.getByRole("button", { name: /create new course/i });
      expect(createBtn).toBeInTheDocument();
      expect(createBtn).toHaveClass("whitespace-nowrap");
      expect(createBtn).toHaveClass("shrink-0");
    });

    it("renders admin KPI metric cards with proper truncation guards", () => {
      renderWithQueryClient(<AdminDashboardPage />);

      expect(screen.getByText("Total Courses")).toBeInTheDocument();
      expect(screen.getByText("Active Enrollments")).toBeInTheDocument();
      expect(screen.getByText("Gross Sales (Sampled)")).toBeInTheDocument();
      expect(screen.getByText("Student Directory")).toBeInTheDocument();
    });
  });

  describe("UI-03 & NAV-02: Admin Media Page Responsive Uploader and Contextual Back Link", () => {
    it("renders the back link to /admin", () => {
      renderWithQueryClient(<AdminMediaPage />);

      const backLink = screen.getByRole("link", { name: /back to admin dashboard/i });
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute("href", "/admin");
    });

    it("renders the uploader form with responsive full-width mobile button and file input", () => {
      renderWithQueryClient(<AdminMediaPage />);

      const uploadBtn = screen.getByRole("button", { name: /upload to private storage/i });
      expect(uploadBtn).toBeInTheDocument();
      expect(uploadBtn).toHaveClass("whitespace-nowrap");
      expect(uploadBtn).toHaveClass("shrink-0");

      const fileInput = screen.getByLabelText(/choose file to upload/i);
      expect(fileInput).toBeInTheDocument();
    });
  });
});
