import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Input } from "@/components/ui/Input";

describe("Input Primitive", () => {
  it("renders with label and placeholder", () => {
    render(<Input label="Email Address" placeholder="Enter your email" />);
    expect(screen.getByLabelText("Email Address")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter your email")).toBeInTheDocument();
  });

  it("renders error state with aria-invalid and error message", () => {
    render(
      <Input
        label="Password"
        error="Password must be at least 12 characters"
      />
    );
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Password must be at least 12 characters"
    );
  });

  it("handles user typing and value change", () => {
    const handleChange = vi.fn();
    render(<Input label="Name" onChange={handleChange} />);
    const input = screen.getByLabelText("Name");
    fireEvent.change(input, { target: { value: "John Doe" } });
    expect(handleChange).toHaveBeenCalled();
  });

  it("enforces minimum touch-target size (>= 44px min-h)", () => {
    render(<Input label="Email" />);
    const input = screen.getByLabelText("Email");
    expect(input.className).toMatch(/h-11|touch-target/);
  });
});
