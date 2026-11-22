import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CourseCard } from "@/components/courses/CourseCard";
import { CourseSummary } from "@/types/course";

const mockCourse: CourseSummary = {
  id: "test-course-123",
  slug: "distributed-systems-mastery",
  title: "Distributed Systems & Resilient Architecture",
  headline: "Master high-scale backend distributed computing with Python and Redis.",
  thumbnail_url: null,
  status: "PUBLISHED",
  price_inr: 499900, // ₹4,999.00
  is_free: false,
  tags: ["Architecture", "Backend", "Python"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("CourseCard Component", () => {
  it("renders course title, headline, formatted price in INR, and tag badge", () => {
    render(<CourseCard course={mockCourse} />);

    expect(screen.getByText("Distributed Systems & Resilient Architecture")).toBeInTheDocument();
    expect(
      screen.getByText("Master high-scale backend distributed computing with Python and Redis.")
    ).toBeInTheDocument();
    expect(screen.getByText("₹4,999.00")).toBeInTheDocument();
    expect(screen.getByText("Architecture")).toBeInTheDocument();
  });

  it("links to the course slug URL", () => {
    render(<CourseCard course={mockCourse} />);

    const link = screen.getByRole("link", {
      name: /view curriculum for distributed systems & resilient architecture/i,
    });
    expect(link).toHaveAttribute("href", "/courses/distributed-systems-mastery");
  });

  it("renders FREE badge when is_free is true", () => {
    const freeCourse: CourseSummary = {
      ...mockCourse,
      id: "free-course-456",
      slug: "foundations-of-zero-trust",
      price_inr: 0,
      is_free: true,
    };

    render(<CourseCard course={freeCourse} />);

    expect(screen.getByText("FREE")).toBeInTheDocument();
    expect(screen.getByText("Free Access")).toBeInTheDocument();
  });
});
