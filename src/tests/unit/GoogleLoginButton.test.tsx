import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/store/authStore";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(),
}));

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock useAuth
const mockRefetchUser = vi.fn().mockResolvedValue({});
vi.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({
    refetchUser: mockRefetchUser,
  }),
}));

// Mock authApi
vi.mock("@/lib/api/auth", () => ({
  authApi: {
    loginWithGoogle: vi.fn(),
  },
}));

describe("GoogleLoginButton Component", () => {
  const originalEnv = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const mockPush = vi.fn();
  const mockRefresh = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().reset();
    (useRouter as any).mockReturnValue({ push: mockPush, refresh: mockRefresh });
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = originalEnv;
    // Clean up window.google
    delete (window as any).google;
    const script = document.getElementById("google-gsi-client");
    if (script) {
      script.remove();
    }
  });

  it("notifies user when NEXT_PUBLIC_GOOGLE_CLIENT_ID is not configured", async () => {
    delete process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

    render(<GoogleLoginButton redirectUrl="/app" />);
    const button = screen.getByRole("button", { name: /continue with google/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);

    expect(toast.info).toHaveBeenCalledWith(
      "Google Sign-In is configured on the backend. Provide NEXT_PUBLIC_GOOGLE_CLIENT_ID for live OIDC popup."
    );
    expect(authApi.loginWithGoogle).not.toHaveBeenCalled();
  });

  it("initializes Google Identity Services and triggers prompt when Client ID is configured", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedConfig: any = null;
    const mockInitialize = vi.fn((config) => {
      capturedConfig = config;
    });
    const mockPrompt = vi.fn();

    (window as any).google = {
      accounts: {
        id: {
          initialize: mockInitialize,
          prompt: mockPrompt,
        },
      },
    };

    render(<GoogleLoginButton redirectUrl="/dashboard" />);
    const button = screen.getByRole("button", { name: /continue with google/i });

    // Initial preload initialization on mount
    await waitFor(() => {
      expect(mockInitialize).toHaveBeenCalled();
    });
    expect(capturedConfig.client_id).toBe("mock-client-id-12345.apps.googleusercontent.com");

    // Clicking button invokes prompt
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockPrompt).toHaveBeenCalled();
    });
  });

  it("handles successful Google ID token credential response and redirects", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedCallback: any = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn((config) => {
            capturedCallback = config.callback;
          }),
          prompt: vi.fn(),
        },
      },
    };

    (authApi.loginWithGoogle as any).mockResolvedValueOnce({
      user: { id: "user-123", email: "student@gmail.com" },
      access_token: "mock-jwt-token",
    });

    render(<GoogleLoginButton redirectUrl="/learn/course-101" />);
    const button = screen.getByRole("button", { name: /continue with google/i });
    fireEvent.click(button);

    // Wait for async initialization and callback capture
    await waitFor(() => {
      expect(capturedCallback).toBeDefined();
    });

    // Simulate Google Identity Services credential response
    await capturedCallback({ credential: "mock_jwt_id_token_from_google" });

    expect(authApi.loginWithGoogle).toHaveBeenCalledWith({
      id_token: "mock_jwt_id_token_from_google",
    });
    expect(useAuthStore.getState().user?.email).toBe("student@gmail.com");
    expect(mockRefetchUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Successfully signed in with Google.");
    expect(mockPush).toHaveBeenCalledWith("/learn/course-101");
    expect(mockRefresh).toHaveBeenCalled();
    // Modal must be cleanly dismissed in terminal success state
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("redirects admin users to /admin when default redirect is requested", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedCallback: any = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn((config) => {
            capturedCallback = config.callback;
          }),
          prompt: vi.fn(),
        },
      },
    };

    (authApi.loginWithGoogle as any).mockResolvedValueOnce({
      user: { id: "admin-123", email: "admin@lms.local", roles: ["ADMIN"] },
      access_token: "mock-jwt-token",
    });

    render(<GoogleLoginButton redirectUrl="/app" />);
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => {
      expect(capturedCallback).toBeDefined();
    });

    await capturedCallback({ credential: "admin_google_token" });

    expect(useAuthStore.getState().user?.roles).toContain("ADMIN");
    expect(mockPush).toHaveBeenCalledWith("/admin");
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("handles Google ID token authentication rejection safely", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedCallback: any = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn((config) => {
            capturedCallback = config.callback;
          }),
          prompt: vi.fn(),
        },
      },
    };

    (authApi.loginWithGoogle as any).mockRejectedValueOnce(
      new Error("Google ID token key lookup failed.")
    );

    render(<GoogleLoginButton redirectUrl="/app" />);
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => {
      expect(capturedCallback).toBeDefined();
    });

    await capturedCallback({ credential: "invalid_expired_token" });

    expect(authApi.loginWithGoogle).toHaveBeenCalledWith({
      id_token: "invalid_expired_token",
    });
    expect(toast.error).toHaveBeenCalledWith("Google ID token key lookup failed.");
    expect(mockPush).not.toHaveBeenCalled();
    // Modal must be cleanly dismissed in terminal failure state
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("prevents concurrent duplicate credential responses when one is in flight", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedCallback: any = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn((config) => {
            capturedCallback = config.callback;
          }),
          prompt: vi.fn(),
        },
      },
    };

    let resolveLogin: (val: any) => void = () => {};
    (authApi.loginWithGoogle as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveLogin = resolve;
        })
    );

    render(<GoogleLoginButton redirectUrl="/app" />);
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => {
      expect(capturedCallback).toBeDefined();
    });

    // Fire first callback
    const p1 = capturedCallback({ credential: "first_token" });

    // Fire second callback concurrently
    const p2 = capturedCallback({ credential: "second_token" });

    // authApi.loginWithGoogle should only be called once
    expect(authApi.loginWithGoogle).toHaveBeenCalledTimes(1);
    expect(authApi.loginWithGoogle).toHaveBeenCalledWith({ id_token: "first_token" });

    resolveLogin({ user: { id: "u1", email: "first@gmail.com" }, access_token: "jwt" });
    await Promise.all([p1, p2]);

    expect(authApi.loginWithGoogle).toHaveBeenCalledTimes(1);
  });

  it("cleans up active timers and cancels Google prompt on component unmount", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    const mockCancel = vi.fn();
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn(),
          prompt: vi.fn(),
          cancel: mockCancel,
        },
      },
    };

    const { unmount } = render(<GoogleLoginButton redirectUrl="/app" />);

    unmount();

    expect(mockCancel).toHaveBeenCalled();
  });

  it("handles prompt not displayed notification gracefully", async () => {
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id-12345.apps.googleusercontent.com";

    let capturedPromptListener: any = null;
    (window as any).google = {
      accounts: {
        id: {
          initialize: vi.fn(),
          prompt: vi.fn((listener) => {
            capturedPromptListener = listener;
          }),
        },
      },
    };

    render(<GoogleLoginButton redirectUrl="/app" />);
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => {
      expect(capturedPromptListener).toBeDefined();
    });

    capturedPromptListener({
      isNotDisplayed: () => true,
      getNotDisplayedReason: () => "suppressed_by_user",
      isSkippedMoment: () => false,
      isDismissedMoment: () => false,
    });

    expect(toast.error).toHaveBeenCalledWith(
      "Google Sign-In prompt could not be displayed. Please check your browser popup/cookie settings."
    );
  });
});
