import React from "react";
import { render, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { TypewriterText } from "@/components/home/TypewriterText";

describe("TypewriterText Component", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Default: reduced motion false
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders with aria-live polite region for screen readers and deterministic initial state", () => {
    const { container } = render(
      <TypewriterText phrases={["Distributed Systems", "Backend Architecture"]} />
    );

    const liveRegion = container.querySelector('[aria-live="polite"]');
    expect(liveRegion).toBeInTheDocument();
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
  });

  it("animates character by character after hydration", () => {
    const { container } = render(
      <TypewriterText
        phrases={["Distributed Systems"]}
        typingSpeed={50}
      />
    );

    // Initial render is empty string (hydration safe)
    expect(container.textContent).toBe("");

    // Advance 1 tick (50ms) -> "D"
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(container.textContent).toBe("D");

    // Advance next tick (50ms) -> "Di"
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(container.textContent).toBe("Di");

    // Advance rest of phrase
    act(() => {
      vi.advanceTimersByTime(50 * 20);
    });
    expect(container.textContent).toBe("Distributed Systems");
  });

  it("honors prefers-reduced-motion without animation", () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { container } = render(
      <TypewriterText phrases={["Distributed Systems", "Backend Architecture"]} />
    );

    // With reduced motion, full phrase is rendered immediately in useEffect
    expect(container.textContent).toBe("Distributed Systems");
  });
});
