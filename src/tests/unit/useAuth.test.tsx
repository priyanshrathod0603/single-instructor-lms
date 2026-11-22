import React from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAuth } from "@/lib/hooks/useAuth";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/store/authStore";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/errors";
import { toast } from "sonner";

// Mock next/navigation
const mockPush = vi.fn();
const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
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
    logout: vi.fn(),
  },
}));

describe("useAuth hook - Logout, Displacement, and State Lifecycle", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().reset();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    (authApi.getMe as any).mockResolvedValue(null);
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("handles successful logout by setting isLoggingOut, clearing state & cache, and redirecting to /login", async () => {
    const mockDisableAutoSelect = vi.fn();
    const mockCancel = vi.fn();
    (window as any).google = {
      accounts: {
        id: {
          disableAutoSelect: mockDisableAutoSelect,
          cancel: mockCancel,
        },
      },
    };

    const mockUser = { id: "user-123", email: "student@example.com", roles: ["STUDENT" as const] };
    useAuthStore.getState().setUser(mockUser as any);
    queryClient.setQueryData(["auth", "me"], mockUser);

    let resolveLogout: (val: any) => void = () => {};
    (authApi.logout as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogout = resolve;
        })
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.isLoggingOut).toBe(false);

    let logoutPromise: Promise<any>;
    act(() => {
      logoutPromise = result.current.logout();
    });

    await waitFor(() => {
      expect(result.current.isLoggingOut).toBe(true);
    });

    await act(async () => {
      resolveLogout({ success: true });
      await logoutPromise;
    });

    await waitFor(() => {
      expect(result.current.isLoggingOut).toBe(false);
      expect(result.current.isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
      expect(queryClient.getQueryData(["auth", "me"])).toBeFalsy();
      expect(mockDisableAutoSelect).toHaveBeenCalled();
      expect(mockCancel).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("handles 401 on logout gracefully as session already revoked, clearing state and redirecting", async () => {
    const mockDisableAutoSelect = vi.fn();
    const mockCancel = vi.fn();
    (window as any).google = {
      accounts: {
        id: {
          disableAutoSelect: mockDisableAutoSelect,
          cancel: mockCancel,
        },
      },
    };

    const mockUser = { id: "user-123", email: "student@example.com", roles: ["STUDENT" as const] };
    useAuthStore.getState().setUser(mockUser as any);
    queryClient.setQueryData(["auth", "me"], mockUser);

    (authApi.logout as any).mockRejectedValueOnce(
      new ApiError("Session already expired", 401, "UNAUTHORIZED")
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      try {
        await result.current.logout();
      } catch {
        // mutateAsync throws on rejection; onError handles recovery
      }
    });

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
      expect(queryClient.getQueryData(["auth", "me"])).toBeFalsy();
      expect(mockDisableAutoSelect).toHaveBeenCalled();
      expect(mockCancel).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("handles timeout or server error on logout by safely clearing local state, notifying user, and redirecting to /login", async () => {
    const mockUser = { id: "user-123", email: "student@example.com", roles: ["STUDENT" as const] };
    useAuthStore.getState().setUser(mockUser as any);

    (authApi.logout as any).mockRejectedValueOnce(
      new ApiError("Network request timed out. Please try again.", 408, "TIMEOUT")
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      try {
        await result.current.logout();
      } catch {
        // mutateAsync throws; onError handler runs
      }
    });

    await waitFor(() => {
      expect(result.current.isLoggingOut).toBe(false);
      expect(toast.info).toHaveBeenCalledWith("Signed out locally. Server session expired or unreachable.");
      expect(mockPush).toHaveBeenCalledWith("/login");
      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  it("clears cached auth queries when session displacement occurs and preserves displacement reason", async () => {
    const mockUser = { id: "user-123", email: "student@example.com", roles: ["STUDENT" as const] };
    useAuthStore.getState().setUser(mockUser as any);
    queryClient.setQueryData(["auth", "me"], mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.isDisplacedSession).toBe(false);

    // Trigger displacement
    act(() => {
      useAuthStore.getState().setDisplacedSession(true, "Signed in from a different browser.");
    });

    await waitFor(() => {
      expect(result.current.isDisplacedSession).toBe(true);
      expect(result.current.displacementReason).toBe("Signed in from a different browser.");
      expect(useAuthStore.getState().user).toBeNull();
      expect(queryClient.getQueryData(["auth", "me"])).toBeFalsy();
    });
  });

  it("dismissDisplacement clears displacement state and stale queries", async () => {
    useAuthStore.getState().setDisplacedSession(true, "Signed in from a different browser.");

    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.isDisplacedSession).toBe(true);

    act(() => {
      result.current.dismissDisplacement();
    });

    await waitFor(() => {
      expect(result.current.isDisplacedSession).toBe(false);
      expect(result.current.displacementReason).toBeNull();
      expect(useAuthStore.getState().isDisplacedSession).toBe(false);
    });
  });
});
