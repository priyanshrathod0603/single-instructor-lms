import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usersApi } from "@/lib/api/users";
import UserDirectoryPage from "@/app/(control)/control/users/page";
import UserProfileDetailPage from "@/app/(control)/control/users/[id]/page";
import ControlAdminsPage from "@/app/(control)/control/admins/page";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "user-123" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/control/users/user-123",
}));

describe("SA-02: Complete User, Admin & Staff Management Unit Tests", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
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

  describe("usersApi Client Integration", () => {
    it("listUsers passes role, search, is_active, is_verified, and dynamic sorting", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: [],
          total: 0,
          page: 1,
          per_page: 15,
          total_pages: 0,
        }),
      });
      global.fetch = mockFetch;

      await usersApi.listUsers({
        page: 2,
        per_page: 15,
        role: "ADMIN",
        search: "Alice",
        is_active: true,
        is_verified: true,
        sort_by: "full_name",
        sort_order: "asc",
      });

      const url = new URL(mockFetch.mock.calls[0][0]);
      expect(url.pathname).toBe("/api/v1/users");
      expect(url.searchParams.get("page")).toBe("2");
      expect(url.searchParams.get("per_page")).toBe("15");
      expect(url.searchParams.get("role")).toBe("ADMIN");
      expect(url.searchParams.get("search")).toBe("Alice");
      expect(url.searchParams.get("is_active")).toBe("true");
      expect(url.searchParams.get("is_verified")).toBe("true");
      expect(url.searchParams.get("sort_by")).toBe("full_name");
      expect(url.searchParams.get("sort_order")).toBe("asc");
    });

    it("manageRole sends PATCH /users/{id}/roles with { role_id, action }", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          id: "u1",
          email: "student@example.com",
          full_name: "Student One",
          roles: ["STUDENT", "STAFF"],
        }),
      });
      global.fetch = mockFetch;

      await usersApi.manageRole("u1", { role_id: "STAFF", action: "ASSIGN" });

      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/users/u1/roles");
      expect(opts.method).toBe("PATCH");
      expect(JSON.parse(opts.body)).toEqual({ role_id: "STAFF", action: "ASSIGN" });
    });

    it("updateStatus sends PATCH /users/{id}/status with { is_active, reason }", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          id: "u1",
          email: "student@example.com",
          full_name: "Student One",
          is_active: false,
        }),
      });
      global.fetch = mockFetch;

      await usersApi.updateStatus("u1", { is_active: false, reason: "Disciplinary hold" });

      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/users/u1/status");
      expect(opts.method).toBe("PATCH");
      expect(JSON.parse(opts.body)).toEqual({ is_active: false, reason: "Disciplinary hold" });
    });

    it("getStudentLearningRecords queries GET /users/{id}/learning-records", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          user: { id: "u1", email: "student@example.com", full_name: "Student One", roles: ["STUDENT"] },
          enrollments: [],
          quiz_attempts: [],
          assignment_submissions: [],
          certificates: [],
          audit_logs: [],
        }),
      });
      global.fetch = mockFetch;

      await usersApi.getStudentLearningRecords("u1");

      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/users/u1/learning-records");
      expect(opts.method).toBe("GET");
    });
  });

  describe("User Directory Page Component", () => {
    it("renders directory table with user records and role tabs", async () => {
      vi.spyOn(usersApi, "listUsers").mockResolvedValue({
        items: [
          {
            id: "user-1",
            email: "alice@example.com",
            full_name: "Alice Walker",
            is_active: true,
            is_verified: true,
            roles: ["STUDENT"],
            created_at: "2026-11-10T12:00:00Z",
          },
          {
            id: "user-2",
            email: "bob@example.com",
            full_name: "Bob Admin",
            is_active: true,
            is_verified: true,
            roles: ["ADMIN"],
            created_at: "2026-11-08T12:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        per_page: 15,
        total_pages: 1,
      });

      renderWithQueryClient(<UserDirectoryPage />);

      expect(screen.getByRole("heading", { name: "User Management" })).toBeInTheDocument();
      expect(screen.getByText("All Users")).toBeInTheDocument();
      expect(screen.getByText("Students")).toBeInTheDocument();
      expect(screen.getByText("Admins")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText("Alice Walker")).toBeInTheDocument();
        expect(screen.getByText("bob@example.com")).toBeInTheDocument();
      });
    });
  });

  describe("Student Profile & Learning History Page Component", () => {
    it("renders student academic summary, enrollments, quizzes, assignments, and certificates", async () => {
      vi.spyOn(usersApi, "getStudentLearningRecords").mockResolvedValue({
        user: {
          id: "user-123",
          email: "jane@example.com",
          full_name: "Jane Student",
          is_active: true,
          is_verified: true,
          roles: ["STUDENT"],
          permissions: [],
          created_at: "2026-11-01T08:00:00Z",
          updated_at: "2026-11-01T08:00:00Z",
        },
        enrollments: [
          {
            id: "enr-1",
            course_id: "crs-1",
            course_title: "High-Performance Next.js Architecture",
            status: "ACTIVE",
            granted_at: "2026-11-01T08:00:00Z",
            progress_percentage: 75.0,
            completed_lessons_count: 15,
            total_lessons_count: 20,
          },
        ],
        quiz_attempts: [
          {
            id: "quiz-att-1",
            quiz_id: "q-1",
            quiz_title: "React Server Components Quiz",
            attempt_no: 1,
            status: "SUBMITTED",
            score: 95.0,
            is_passed: true,
            started_at: "2026-11-05T10:00:00Z",
            completed_at: "2026-11-05T10:25:00Z",
          },
        ],
        assignment_submissions: [
          {
            id: "sub-1",
            assignment_id: "asg-1",
            assignment_title: "Server Actions Milestone Project",
            attempt_no: 1,
            status: "GRADED",
            final_score: 98.0,
            max_score: 100.0,
            pass_score: 60.0,
            file_url: "https://storage.example.com/sub1.zip",
            submitted_at: "2026-11-06T14:00:00Z",
            graded_at: "2026-11-07T09:00:00Z",
            feedback: "Outstanding separation of concerns.",
          },
        ],
        certificates: [
          {
            id: "cert-1",
            certificate_no: "CERT-202611-9988",
            course_id: "crs-1",
            course_title: "High-Performance Next.js Architecture",
            issued_at: "2026-11-08T16:00:00Z",
            verification_hash: "hash1234567890",
            pdf_url: "https://storage.example.com/cert.pdf",
            is_revoked: false,
          },
        ],
        audit_logs: [
          {
            id: "audit-1",
            action: "ENROLLMENT_GRANTED",
            actor_type: "ADMIN",
            resource_type: "enrollment",
            created_at: "2026-11-01T08:00:00Z",
          },
        ],
      });

      renderWithQueryClient(<UserProfileDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Jane Student")).toBeInTheDocument();
        expect(screen.getByText("jane@example.com")).toBeInTheDocument();
        expect(screen.getByText("High-Performance Next.js Architecture")).toBeInTheDocument();
        expect(screen.getByText("75%")).toBeInTheDocument();
      });

      // Switch to Quizzes tab
      const quizzesTab = screen.getByRole("button", { name: /Quiz Assessments/i });
      fireEvent.click(quizzesTab);
      await waitFor(() => {
        expect(screen.getByText("React Server Components Quiz")).toBeInTheDocument();
        expect(screen.getByText("95%")).toBeInTheDocument();
      });

      // Switch to Assignments tab
      const assignmentsTab = screen.getByRole("button", { name: /Assignment Deliverables/i });
      fireEvent.click(assignmentsTab);
      await waitFor(() => {
        expect(screen.getByText("Server Actions Milestone Project")).toBeInTheDocument();
        expect(screen.getByText(/Outstanding separation of concerns/i)).toBeInTheDocument();
      });

      // Switch to Certificates tab
      const certsTab = screen.getByRole("button", { name: /Certificates/i });
      fireEvent.click(certsTab);
      await waitFor(() => {
        expect(screen.getByText("CERT-202611-9988")).toBeInTheDocument();
      });
    });
  });

  describe("Administrator Hub Page Component", () => {
    it("renders administrators roster and invite modal", async () => {
      vi.spyOn(usersApi, "listUsers").mockImplementation(async (params) => {
        if (params?.role === "SUPER_ADMIN") {
          return {
            items: [
              {
                id: "super-1",
                email: "owner@example.com",
                full_name: "Instructor Owner",
                is_active: true,
                is_verified: true,
                roles: ["SUPER_ADMIN"],
                created_at: "2026-10-01T00:00:00Z",
              },
            ],
            total: 1,
            page: 1,
            per_page: 50,
            total_pages: 1,
          };
        }
        return {
          items: [
            {
              id: "admin-1",
              email: "ops@example.com",
              full_name: "Operations Manager",
              is_active: true,
              is_verified: true,
              roles: ["ADMIN"],
              created_at: "2026-10-15T00:00:00Z",
            },
          ],
          total: 1,
          page: 1,
          per_page: 50,
          total_pages: 1,
        };
      });

      renderWithQueryClient(<ControlAdminsPage />);

      expect(screen.getByText("Administrator Management Hub")).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText("Instructor Owner")).toBeInTheDocument();
        expect(screen.getByText("Operations Manager")).toBeInTheDocument();
      });

      // Click Invite Administrator
      const inviteBtn = screen.getByRole("button", { name: /Invite Administrator/i });
      fireEvent.click(inviteBtn);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Invite Administrator" })).toBeInTheDocument();
        expect(screen.getByPlaceholderText("e.g. Eleanor Vance")).toBeInTheDocument();
      });
    });
  });
});
