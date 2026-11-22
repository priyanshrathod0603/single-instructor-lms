import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DisplacedSessionModal } from "@/components/feedback/DisplacedSessionModal";
import { useAuth } from "@/lib/hooks/useAuth";
import { useAuthStore } from "@/lib/store/authStore";
import { authApi } from "@/lib/api/auth";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SESSION_REVOKED_EVENT, dispatchSessionRevokedEvent } from "@/lib/api/errors";
import { renderHook } from "@testing-library/react";

// Mock next/navigation
const mockPush = vi.fn().mockResolvedValue(true);
const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
  usePathname: () => "/app/dashboard",
}));

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock authApi
vi.mock("@/lib/api/auth", () => ({
  authApi: {
    getMe: vi.fn(),
    logout: vi.fn().mockResolvedValue({ success: true, message: "Logged out successfully." }),
  },
}));

describe("Session Recovery and Logout Invariants (Part C)", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().reset();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    (authApi.getMe as any).mockResolvedValue(null);
  });

  const createWrapper = () => {
    return ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };

  it("1. Normal logout clears store, clears queries, caches null for /me, and redirects to /login", async () => {
    const mockUser = { id: "user-1", email: "student@example.com", roles: ["STUDENT" as const] };
    useAuthStore.getState().setUser(mockUser as any);
    queryClient.setQueryData(["auth", "me"], mockUser);
    queryClient.setQueryData(["courses", "enrolled"], [{ id: "c1", title: "Course 1" }]);

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isAuthenticated).toBe(true);

    await act(async () => {
      await result.current.logout();
    });

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
      // Enrolled courses query cleared
      expect(queryClient.getQueryData(["courses", "enrolled"])).toBeUndefined();
      // auth/me cached as null (so it doesn't refetch on login page)
      expect(queryClient.getQueryData(["auth", "me"])).toBeNull();
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("2. DisplacedSessionModal renders on session displacement and closes cleanly on Sign In Again", async () => {
    useAuthStore.getState().setDisplacedSession(true, "Signed in on another browser device.");

    const wrapper = createWrapper();
    render(<DisplacedSessionModal />, { wrapper });

    expect(screen.getByText("You signed in on another device")).toBeInTheDocument();
    expect(screen.getByText("Signed in on another browser device.")).toBeInTheDocument();

    const button = screen.getByRole("button", { name: /sign in again/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();

    // Click Sign In Again
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
      expect(useAuthStore.getState().isDisplacedSession).toBe(false);
      expect(useAuthStore.getState().displacementReason).toBeNull();
      expect(useAuthStore.getState().user).toBeNull();
    });
  });

  it("3. Duplicate clicks on Sign In Again are blocked and loading state cleans up reliably", async () => {
    useAuthStore.getState().setDisplacedSession(true, "Signed in on another browser device.");

    let resolvePush: (val: boolean) => void = () => {};
    mockPush.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePush = resolve;
        })
    );

    const wrapper = createWrapper();
    render(<DisplacedSessionModal />, { wrapper });

    const button = screen.getByRole("button", { name: /sign in again/i });

    // First click initiates navigation
    act(() => {
      fireEvent.click(button);
    });

    // Second click while in flight is ignored
    act(() => {
      fireEvent.click(button);
    });
    expect(mockPush).toHaveBeenCalledTimes(1);

    // Resolve navigation
    await act(async () => {
      resolvePush(true);
    });

    await waitFor(() => {
      expect(useAuthStore.getState().isDisplacedSession).toBe(false);
    });
  });

  it("4. SESSION_REVOKED does not repeatedly trigger displacement when already displaced", () => {
    act(() => {
      dispatchSessionRevokedEvent("First displacement reason");
    });
    expect(useAuthStore.getState().isDisplacedSession).toBe(true);
    expect(useAuthStore.getState().displacementReason).toBe("First displacement reason");

    act(() => {
      dispatchSessionRevokedEvent("Second displacement reason");
    });
    // Reason and state are preserved; does not re-trigger
    expect(useAuthStore.getState().isDisplacedSession).toBe(true);
    expect(useAuthStore.getState().displacementReason).toBe("First displacement reason");
  });

  it("5. dismissDisplacement cancels pending auth queries and prevents refetch loops", async () => {
    const cancelSpy = vi.spyOn(queryClient, "cancelQueries");
    const setQueryDataSpy = vi.spyOn(queryClient, "setQueryData");

    useAuthStore.getState().setDisplacedSession(true, "Revoked");

    const wrapper = createWrapper();
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.dismissDisplacement();
    });

    expect(cancelSpy).toHaveBeenCalledWith({ queryKey: ["auth"] });
    expect(setQueryDataSpy).toHaveBeenCalledWith(["auth", "me"], null);
    expect(useAuthStore.getState().isDisplacedSession).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });
});
