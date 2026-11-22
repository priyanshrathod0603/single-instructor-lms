import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ArrowRight, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/Button";

describe("Button Interaction System & Premium Hover Effects", () => {
  it("primary variant enforces upward elevation, subtle scale, and shadow transitions", () => {
    render(
      <Button variant="primary">
        Explore Courses
        <ArrowRight className="h-4 w-4" />
      </Button>
    );
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("hover:-translate-y-0.5");
    expect(btn.className).toContain("hover:scale-[1.02]");
    expect(btn.className).toContain("hover:shadow-card");
    expect(btn.className).toContain("hover:bg-brand-teal-dark");
    expect(btn.className).toContain("active:scale-[0.98]");
    expect(btn.className).toContain("duration-200");
    expect(btn.className).toContain("group-hover:[&_svg.lucide-arrow-right]:translate-x-1");
  });

  it("secondary variant enforces background, border, text colour transition, and subtle elevation", () => {
    render(<Button variant="secondary">Secondary CTA</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("border-soft-peach");
    expect(btn.className).toContain("hover:bg-brand-peach/40");
    expect(btn.className).toContain("hover:border-brand-teal/40");
    expect(btn.className).toContain("hover:text-brand-teal");
    expect(btn.className).toContain("hover:-translate-y-0.5");
    expect(btn.className).toContain("hover:scale-[1.02]");
    expect(btn.className).toContain("active:scale-[0.98]");
  });

  it("outline variant enforces background fill, border colour, and text colour transition", () => {
    render(<Button variant="outline">Outline Action</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("border-2");
    expect(btn.className).toContain("border-brand-teal");
    expect(btn.className).toContain("hover:bg-brand-mint/40");
    expect(btn.className).toContain("hover:border-brand-teal-dark");
    expect(btn.className).toContain("hover:text-brand-teal-dark");
    expect(btn.className).toContain("hover:-translate-y-0.5");
  });

  it("ghost variant enforces subtle background highlight and smooth text transition without excess elevation", () => {
    render(<Button variant="ghost">Ghost Nav Item</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("hover:bg-brand-peach/60");
    expect(btn.className).toContain("hover:text-brand-teal");
    expect(btn.className).toContain("active:scale-[0.98]");
  });

  it("destructive variant enforces accessible contrast and active feedback", () => {
    render(<Button variant="destructive">Delete Item</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("bg-status-error");
    expect(btn.className).toContain("hover:bg-red-700");
    expect(btn.className).toContain("hover:-translate-y-0.5");
    expect(btn.className).toContain("active:scale-[0.98]");
  });

  it("disabled and loading buttons strictly suppress interactive hover transforms", () => {
    const { rerender } = render(<Button disabled>Disabled Action</Button>);
    const disabledBtn = screen.getByRole("button");
    expect(disabledBtn.className).toContain("disabled:transform-none");
    expect(disabledBtn.className).toContain("disabled:hover:scale-100");
    expect(disabledBtn.className).toContain("disabled:hover:translate-y-0");
    expect(disabledBtn.className).toContain("disabled:pointer-events-none");

    rerender(<Button isLoading>Loading Action</Button>);
    const loadingBtn = screen.getByRole("button");
    expect(loadingBtn).toBeDisabled();
    expect(loadingBtn).toHaveAttribute("aria-busy", "true");
    expect(loadingBtn.querySelector("svg.animate-spin")).toBeInTheDocument();
  });
});
