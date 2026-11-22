import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OverviewMetricsGrid } from "@/components/control/OverviewMetricsGrid";
import { AnalyticsTrendsSection } from "@/components/control/AnalyticsTrendsSection";
import { RecentActivityLedger } from "@/components/control/RecentActivityLedger";
import { SecurityStatusCard } from "@/components/control/SecurityStatusCard";
import { QuickActionsGrid } from "@/components/control/QuickActionsGrid";
import ControlGovernancePage from "@/app/(control)/control/page";
import { controlApi } from "@/lib/api/control";
import { ControlOverviewData } from "@/types/control";

const mockOverviewData: ControlOverviewData = {
  user_metrics: {
    total_students: 150,
    total_admins: 2,
    total_staff: 5,
    total_super_admins: 1,
    active_users: 140,
  },
  course_metrics: {
    total_courses: 6,
    published_courses: 4,
    draft_courses: 1,
    archived_courses: 1,
  },
  enrollment_metrics: {
    total_enrollments: 85,
    active_enrollments: 80,
  },
  financial_metrics: {
    verified_revenue_paise: 4990000,
    verified_revenue_inr: 49900.0,
    successful_transactions: 10,
    refunded_amount_paise: 49900,
    refunded_amount_inr: 499.0,
    net_revenue_paise: 4940100,
    net_revenue_inr: 49401.0,
    currency: "INR",
  },
  security_metrics: {
    total_audit_events: 320,
    security_events_count: 18,
    active_staff_count: 5,
    security_model: "Tier 1 Hardened: Single Active Session & Signed JWTs",
  },
  registration_trends: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-11-${String(i + 1).padStart(2, "0")}`,
    count: i % 3 === 0 ? 4 : 1,
  })),
  enrollment_trends: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-11-${String(i + 1).padStart(2, "0")}`,
    count: i % 4 === 0 ? 3 : 0,
  })),
  recent_activity: [
    {
      id: "audit-101",
      actor_type: "SUPER_ADMIN",
      action: "USER_ROLE_ASSIGNED",
      resource_type: "user",
      resource_id: "usr-abc",
      created_at: "2026-11-16T12:00:00Z",
      ip_address: "192.168.1.100",
    },
    {
      id: "audit-102",
      actor_type: "STUDENT",
      action: "AUTH_LOGIN",
      resource_type: "session",
      resource_id: "sess-xyz",
      created_at: "2026-11-16T11:45:00Z",
      ip_address: "10.0.0.1",
    },
  ],
  generated_at: "2026-11-16T12:30:00Z",
};

describe("SA-01: Super Admin Dashboard Components", () => {
  describe("OverviewMetricsGrid", () => {
    it("renders financial, user, course, and enrollment metrics accurately", () => {
      render(
        <OverviewMetricsGrid
          userMetrics={mockOverviewData.user_metrics}
          courseMetrics={mockOverviewData.course_metrics}
          enrollmentMetrics={mockOverviewData.enrollment_metrics}
          financialMetrics={mockOverviewData.financial_metrics}
        />
      );

      // Financials
      expect(screen.getByText(/verified revenue/i)).toBeInTheDocument();
      // Total students
      expect(screen.getByText("150")).toBeInTheDocument();
      // Total courses
      expect(screen.getByText("6")).toBeInTheDocument();
      // Total enrollments
      expect(screen.getByText("85")).toBeInTheDocument();
      // Active enrollments
      expect(screen.getByText("80")).toBeInTheDocument();
      // Net revenue display with deduction
      expect(screen.getByText(/net after refunds/i)).toBeInTheDocument();
      expect(screen.getByText(/refunded amount/i)).toBeInTheDocument();
    });
  });

  describe("AnalyticsTrendsSection", () => {
    it("renders daily registration and enrollment charts with totals", () => {
      render(
        <AnalyticsTrendsSection
          registrationTrends={mockOverviewData.registration_trends}
          enrollmentTrends={mockOverviewData.enrollment_trends}
        />
      );

      expect(screen.getByText("Daily Registrations")).toBeInTheDocument();
      expect(screen.getByText("Daily Enrollments")).toBeInTheDocument();
      expect(screen.getAllByText("14-Day Total").length).toBe(2);
    });

    it("handles zero activity cleanly without crashing", () => {
      const zeroTrends = Array.from({ length: 14 }, (_, i) => ({
        date: `2026-11-${String(i + 1).padStart(2, "0")}`,
        count: 0,
      }));

      render(
        <AnalyticsTrendsSection
          registrationTrends={zeroTrends}
          enrollmentTrends={zeroTrends}
        />
      );

      const totals = screen.getAllByText("0");
      expect(totals.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("RecentActivityLedger", () => {
    it("renders audit ledger with action badges and links to audit explorer", () => {
      render(<RecentActivityLedger activity={mockOverviewData.recent_activity} />);

      expect(screen.getByText("Recent Platform Activity")).toBeInTheDocument();
      expect(screen.getByText("USER_ROLE_ASSIGNED")).toBeInTheDocument();
      expect(screen.getByText("AUTH_LOGIN")).toBeInTheDocument();
      expect(screen.getByText("192.168.1.100")).toBeInTheDocument();

      const auditLink = screen.getByRole("link", { name: /full audit explorer/i });
      expect(auditLink).toHaveAttribute("href", "/control/audit");
    });

    it("renders empty state message when activity list is empty", () => {
      render(<RecentActivityLedger activity={[]} />);

      expect(screen.getByText("No recent activity recorded")).toBeInTheDocument();
    });
  });

  describe("SecurityStatusCard", () => {
    it("renders security posture metrics correctly", () => {
      render(
        <SecurityStatusCard securityMetrics={mockOverviewData.security_metrics} />
      );

      expect(screen.getByText("320")).toBeInTheDocument(); // total audit
      expect(screen.getByText("18")).toBeInTheDocument(); // security events
      expect(screen.getByText("5")).toBeInTheDocument(); // active staff
      expect(screen.getByText("Strict single active session")).toBeInTheDocument();
    });
  });

  describe("QuickActionsGrid", () => {
    it("renders 8 live operational modules with correct links", () => {
      render(<QuickActionsGrid />);

      const studentLink = screen.getByRole("link", { name: /manage students/i });
      expect(studentLink).toHaveAttribute("href", "/admin/students");

      const staffLink = screen.getByRole("link", { name: /staff & ta onboarding/i });
      expect(staffLink).toHaveAttribute("href", "/control/staff");

      const courseLink = screen.getByRole("link", { name: /course catalog/i });
      expect(courseLink).toHaveAttribute("href", "/admin/courses");

      const orderLink = screen.getByRole("link", { name: /orders & financials/i });
      expect(orderLink).toHaveAttribute("href", "/admin/orders");

      const enrollLink = screen.getByRole("link", { name: /course enrollments/i });
      expect(enrollLink).toHaveAttribute("href", "/admin/enrollments");

      const mediaLink = screen.getByRole("link", { name: /media library/i });
      expect(mediaLink).toHaveAttribute("href", "/admin/media");

      const permLink = screen.getByRole("link", { name: /permissions matrix/i });
      expect(permLink).toHaveAttribute("href", "/control/permissions");

      const auditLink = screen.getByRole("link", { name: /audit trail explorer/i });
      expect(auditLink).toHaveAttribute("href", "/control/audit");
    });

    it("renders planned modules with phase badges and no broken navigation", () => {
      render(<QuickActionsGrid />);

      expect(screen.getByText("Secondary Admin Roster")).toBeInTheDocument();
      expect(screen.getByText("Blog & Content Hub")).toBeInTheDocument();
      expect(screen.getByText("Course Notes & Downloads")).toBeInTheDocument();
      expect(screen.getByText("Promotions & Discounts")).toBeInTheDocument();

      expect(screen.getByText("Phase 3 Planned")).toBeInTheDocument();
      expect(screen.getByText("Phase 4 Planned")).toBeInTheDocument();
      expect(screen.getAllByText("Phase 5 Planned").length).toBe(2);
    });
  });

  describe("ControlGovernancePage Lifecycle", () => {
    let queryClient: QueryClient;

    beforeEach(() => {
      queryClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
      });
      vi.restoreAllMocks();
    });

    afterEach(() => {
      queryClient.clear();
    });

    it("renders loading skeleton while query is pending", () => {
      vi.spyOn(controlApi, "getOverview").mockImplementation(
        () => new Promise(() => {}) // never resolves
      );

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ControlGovernancePage />
        </QueryClientProvider>
      );

      expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });

    it("renders error state with retry button when query fails", async () => {
      vi.spyOn(controlApi, "getOverview").mockRejectedValue(
        new Error("Backend service unreachable")
      );

      render(
        <QueryClientProvider client={queryClient}>
          <ControlGovernancePage />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(
          screen.getByText("Unable to Load Platform Metrics")
        ).toBeInTheDocument();
      });

      expect(screen.getByText("Backend service unreachable")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry connection/i })).toBeInTheDocument();
    });

    it("renders full dashboard on successful data resolution", async () => {
      vi.spyOn(controlApi, "getOverview").mockResolvedValue(mockOverviewData);

      render(
        <QueryClientProvider client={queryClient}>
          <ControlGovernancePage />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Super Administrator Governance/i)).toBeInTheDocument();
      });

      expect(screen.getByText("Super Admin")).toBeInTheDocument();
      expect(screen.getByText("150")).toBeInTheDocument(); // total students
      expect(screen.getByText("USER_ROLE_ASSIGNED")).toBeInTheDocument();
    });
  });
});
