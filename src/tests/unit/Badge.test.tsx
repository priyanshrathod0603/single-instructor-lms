import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Badge } from "@/components/ui/Badge";

describe("Badge Primitive", () => {
  it("renders with variant classes correctly", () => {
    const { rerender } = render(<Badge variant="mint">Completed</Badge>);
    expect(screen.getByText("Completed")).toHaveClass("bg-accent-mint");

    rerender(<Badge variant="coral">Live</Badge>);
    expect(screen.getByText("Live")).toHaveClass("bg-accent-coral");

    rerender(<Badge variant="teal">Enrolled</Badge>);
    expect(screen.getByText("Enrolled")).toHaveClass("bg-primary-teal");

    rerender(<Badge variant="peach">Pending</Badge>);
    expect(screen.getByText("Pending")).toHaveClass("bg-accent-peach");
  });
});
