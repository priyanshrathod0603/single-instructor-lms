import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { StudentBottomNav } from "@/components/navigation/StudentBottomNav";

const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

describe("StudentBottomNav Component (NAV-01)", () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue("/app");
  });

  it("renders the 3 primary navigation links plus the 'More' button", () => {
    render(<StudentBottomNav />);

    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Courses")).toBeInTheDocument();
    expect(screen.getByText("Tasks")).toBeInTheDocument();
    expect(screen.getByText("More")).toBeInTheDocument();
  });

  it("highlights Overview when pathname is /app", () => {
    mockUsePathname.mockReturnValue("/app");
    render(<StudentBottomNav />);

    const overviewLink = screen.getByRole("link", { name: /overview/i });
    expect(overviewLink).toHaveClass("text-primary-teal");
  });

  it("opens the More drawer when 'More' is clicked", () => {
    render(<StudentBottomNav />);

    // Before clicking, drawer is not open
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const moreBtn = screen.getByRole("button", { name: /open more navigation options/i });
    fireEvent.click(moreBtn);

    // After clicking, drawer is visible
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Quizzes")).toBeInTheDocument();
    expect(screen.getByText("Certificates")).toBeInTheDocument();
    expect(screen.getByText("Orders & Invoices")).toBeInTheDocument();
    expect(screen.getByText("Profile Settings")).toBeInTheDocument();
  });

  it("highlights 'More' when visiting a secondary destination route like /app/quizzes", () => {
    mockUsePathname.mockReturnValue("/app/quizzes");
    render(<StudentBottomNav />);

    const moreBtn = screen.getByRole("button", { name: /open more navigation options/i });
    expect(moreBtn).toHaveClass("text-primary-teal");
  });

  it("closes the drawer when clicking the close button", () => {
    render(<StudentBottomNav />);

    const moreBtn = screen.getByRole("button", { name: /open more navigation options/i });
    fireEvent.click(moreBtn);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /close navigation menu/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the drawer on pressing Escape key", () => {
    render(<StudentBottomNav />);

    const moreBtn = screen.getByRole("button", { name: /open more navigation options/i });
    fireEvent.click(moreBtn);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
