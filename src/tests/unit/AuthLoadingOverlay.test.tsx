import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";

// Mock motion/react to verify reduced motion handling
let mockReducedMotion = false;
vi.mock("motion/react", async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    useReducedMotion: () => mockReducedMotion,
  };
});

describe("AuthLoadingOverlay Component", () => {
  beforeEach(() => {
    mockReducedMotion = false;
  });

  it("renders when isOpen is true with default status message", () => {
    render(<AuthLoadingOverlay isOpen={true} />);

    const statusEl = screen.getByRole("status");
    expect(statusEl).toBeInTheDocument();
    expect(statusEl).toHaveAttribute("aria-live", "polite");
    expect(statusEl).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Verifying your credentials…")).toBeInTheDocument();
  });

  it("renders custom statusMessage and subMessage correctly", () => {
    render(
      <AuthLoadingOverlay
        isOpen={true}
        statusMessage="Connecting securely…"
        subMessage="Google Identity Services"
      />
    );

    expect(screen.getByText("Connecting securely…")).toBeInTheDocument();
    expect(screen.getByText("Google Identity Services")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <AuthLoadingOverlay isOpen={false} statusMessage="Hidden" />
    );

    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("respects prefers-reduced-motion without breaking accessibility or layout", () => {
    mockReducedMotion = true;

    render(
      <AuthLoadingOverlay
        isOpen={true}
        statusMessage="Establishing your session…"
      />
    );

    const statusEl = screen.getByRole("status");
    expect(statusEl).toBeInTheDocument();
    expect(screen.getByText("Establishing your session…")).toBeInTheDocument();
  });

  it("supports inline embedded rendering when isFullScreen is false", () => {
    render(
      <AuthLoadingOverlay
        isOpen={true}
        isFullScreen={false}
        statusMessage="Verifying email…"
      />
    );

    const statusEl = screen.getByRole("status");
    expect(statusEl).toBeInTheDocument();
    // In inline mode, the status card is rendered directly without the fixed backdrop wrapper
    expect(statusEl.parentElement?.classList.contains("fixed")).toBe(false);
  });
});
