import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CourseGovernancePage from "@/app/(control)/control/courses/page";
import { controlApi } from "@/lib/api/control";
import { CourseGovernanceListResponse } from "@/types/content";

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockCoursesList: CourseGovernanceListResponse = {
  items: [
    {
      id: "course-1",
      slug: "full-stack-python",
      title: "Full-Stack Python Bootcamp",
      headline: "Master Python and FastAPI",
      description: "Comprehensive backend course.",
      thumbnail_url: "https://example.com/thumb.jpg",
      status: "PUBLISHED",
      price_inr: 499900,
      is_free: false,
      tags: ["Python", "FastAPI"],
      live_revision_id: "rev-live-1",
      total_sections: 4,
      total_lessons: 24,
      total_duration_seconds: 7200, // 2h
      has_quiz: true,
      has_assignment: true,
      enrolled_students_count: 55,
      created_at: "2026-11-01T10:00:00Z",
      updated_at: "2026-11-10T10:00:00Z",
    },
    {
      id: "course-2",
      slug: "react-19-deep-dive",
      title: "React 19 Deep Dive",
      headline: "Learn React Server Components",
      description: "Advanced frontend course.",
      thumbnail_url: null,
      status: "DRAFT",
      price_inr: 0,
      is_free: true,
      tags: ["React", "Frontend"],
      live_revision_id: null,
      total_sections: 2,
      total_lessons: 10,
      total_duration_seconds: 2400, // 40m
      has_quiz: false,
      has_assignment: false,
      enrolled_students_count: 0,
      created_at: "2026-11-05T10:00:00Z",
      updated_at: "2026-11-12T10:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  per_page: 10,
  pages: 1,
};

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <CourseGovernancePage />
    </QueryClientProvider>
  );
}

describe("Course Governance Page (SA-04.1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "listGovernedCourses").mockResolvedValue(mockCoursesList);
  });

  it("renders page header and KPI metrics cards accurately", async () => {
    renderComponent();

    expect(
      screen.getByText("Course Governance & Curriculum Overview")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Total Courses")).toBeInTheDocument();
      expect(screen.getByText("Drafts")).toBeInTheDocument();
      expect(screen.getAllByText("Archived").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Enrollments")).toBeInTheDocument();
      expect(screen.getAllByText("55").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders governed courses table with curriculum statistics", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Full-Stack Python Bootcamp")).toBeInTheDocument();
      expect(screen.getByText("/full-stack-python")).toBeInTheDocument();
      expect(screen.getByText("React 19 Deep Dive")).toBeInTheDocument();
    });

    // Check status badges
    expect(screen.getAllByText("Published").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Draft").length).toBeGreaterThanOrEqual(1);

    // Check curriculum stats for course 1
    expect(screen.getByText("2h")).toBeInTheDocument();

    // Check price or Free badge
    expect(screen.getByText("Free")).toBeInTheDocument();
  });

  it("opens inspection modal on clicking Inspect button", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Full-Stack Python Bootcamp")).toBeInTheDocument();
    });

    const inspectButtons = screen.getAllByRole("button", { name: /inspect/i });
    fireEvent.click(inspectButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Course Governance Inspection")).toBeInTheDocument();
      expect(screen.getByText("Comprehensive backend course.")).toBeInTheDocument();
      expect(screen.getByText("Yes (Interactive Quizzes)")).toBeInTheDocument();
    });
  });

  it("opens status change modal and executes status transition", async () => {
    const updateSpy = vi.spyOn(controlApi, "updateCourseStatus").mockResolvedValue({
      ...mockCoursesList.items[1],
      status: "PUBLISHED",
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("React 19 Deep Dive")).toBeInTheDocument();
    });

    const statusButtons = screen.getAllByRole("button", { name: /status/i });
    fireEvent.click(statusButtons[1]); // course 2 (DRAFT)

    await waitFor(() => {
      expect(screen.getByText("Change Course Lifecycle Status")).toBeInTheDocument();
    });

    const confirmBtn = screen.getByRole("button", { name: /confirm change/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith("course-2", expect.objectContaining({
        status: "PUBLISHED",
      }));
    });
  });
});
