import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "@/components/ui/Button";

describe("Button Primitive", () => {
  it("renders with default props and text content", () => {
    render(<Button>Click me</Button>);
    const button = screen.getByRole("button", { name: /click me/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass("bg-brand-teal");
  });

  it("applies variant classes correctly", () => {
    const { rerender } = render(<Button variant="accent">Accent</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-brand-coral");

    rerender(<Button variant="secondary">Secondary</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-soft-peach");
    expect(screen.getByRole("button")).toHaveClass("hover:text-brand-teal");

    rerender(<Button variant="outline">Outline</Button>);
    expect(screen.getByRole("button")).toHaveClass("border-2");
    expect(screen.getByRole("button")).toHaveClass("hover:bg-brand-mint/40");

    rerender(<Button variant="ghost">Ghost</Button>);
    expect(screen.getByRole("button")).toHaveClass("text-text-primary");
    expect(screen.getByRole("button")).toHaveClass("hover:bg-brand-peach/60");

    rerender(<Button variant="destructive">Destructive</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-status-error");
    expect(screen.getByRole("button")).toHaveClass("hover:bg-red-700");
  });

  it("enforces premium hover, active, and elevation interaction classes", () => {
    render(<Button variant="primary">Hover Elevation</Button>);
    const button = screen.getByRole("button");
    // Elevation, scale, active feedback, and smooth 200ms transition
    expect(button.className).toContain("hover:-translate-y-0.5");
    expect(button.className).toContain("hover:scale-[1.02]");
    expect(button.className).toContain("active:scale-[0.98]");
    expect(button.className).toContain("duration-200");
    expect(button.className).toContain("will-change-transform");
  });

  it("enforces minimum touch-target size requirement (>= 44px min-h)", () => {
    render(<Button>Touch target</Button>);
    const button = screen.getByRole("button");
    expect(button.className).toMatch(/h-11|touch-target/);
  });

  it("handles click events", () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Submit</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("disables button and shows spinner when isLoading is true", () => {
    const handleClick = vi.fn();
    render(<Button isLoading onClick={handleClick}>Loading</Button>);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    expect(button).toHaveClass("disabled:transform-none");
    expect(button).toHaveClass("disabled:pointer-events-none");
    fireEvent.click(button);
    expect(handleClick).not.toHaveBeenCalled();
    expect(button.querySelector("svg")).toBeInTheDocument();
  });
});
