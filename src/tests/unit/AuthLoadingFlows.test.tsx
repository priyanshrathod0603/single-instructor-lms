import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LoginForm } from "@/components/auth/LoginForm";
import { SignupForm } from "@/components/auth/SignupForm";
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton";
import { DisplacedSessionModal } from "@/components/feedback/DisplacedSessionModal";
import { authApi } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/store/authStore";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/errors";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock next/navigation
const mockPush = vi.fn();
const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
  useSearchParams: () => ({
    get: (param: string) => (param === "redirect" ? "/app" : null),
  }),
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
const mockLogout = vi.fn().mockResolvedValue({});
const mockDismissDisplacement = vi.fn();
vi.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({
    user: useAuthStore.getState().user,
    isAuthenticated: !!useAuthStore.getState().user,
    isLoading: false,
    isDisplacedSession: useAuthStore.getState().isDisplacedSession,
    displacementReason: useAuthStore.getState().displacementReason,
    dismissDisplacement: () => {
      mockDismissDisplacement();
      useAuthStore.getState().setDisplacedSession(false, null);
    },
    logout: mockLogout,
    isLoggingOut: false,
    refetchUser: mockRefetchUser,
  }),
}));

// Mock authApi
vi.mock("@/lib/api/auth", () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
    verifyEmail: vi.fn(),
    requestPasswordReset: vi.fn(),
    confirmPasswordReset: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("Authentication Loading & Session Recovery Flows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().reset();
  });

  describe("1. Email/Password Login Flow", () => {
    it("progresses through loading states and redirects on success", async () => {
      let resolveLogin: (value: any) => void = () => {};
      (authApi.login as any).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveLogin = resolve;
          })
      );

      render(<LoginForm />, { wrapper: createWrapper() });

      const emailInput = screen.getByLabelText(/email address/i);
      const passwordInput = screen.getByLabelText(/^password$/i);
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: "student@example.com" } });
      fireEvent.change(passwordInput, { target: { value: "password12345" } });

      fireEvent.click(submitButton);

      // Verify loading state is displayed with credentials status
      await waitFor(() => {
        expect(screen.getByRole("status")).toBeInTheDocument();
        expect(screen.getByText("Verifying your credentials…")).toBeInTheDocument();
      });

      // Verify button duplicate submission prevention
      expect(submitButton).toBeDisabled();

      // Resolve login API
      resolveLogin({ user: { id: "u-1", email: "student@example.com" } });

      await waitFor(() => {
        expect(mockRefetchUser).toHaveBeenCalled();
        expect(mockPush).toHaveBeenCalledWith("/app");
      });
    });

    it("recovers cleanly on authentication failure and preserves form values", async () => {
      (authApi.login as any).mockRejectedValueOnce(
        new ApiError("Invalid email or password", 401, "INVALID_CREDENTIALS", undefined, "req-123")
      );

      render(<LoginForm />, { wrapper: createWrapper() });

      const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement;
      const passwordInput = screen.getByLabelText(/^password$/i) as HTMLInputElement;
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: "wrong@example.com" } });
      fireEvent.change(passwordInput, { target: { value: "wrongpass123" } });

      fireEvent.click(submitButton);

      // Wait for error alert to appear
      await waitFor(() => {
        expect(screen.getByText("Invalid email or password")).toBeInTheDocument();
      });

      // Loading overlay must be dismissed
      expect(screen.queryByRole("status")).not.toBeInTheDocument();

      // Form inputs must be preserved (not cleared!)
      expect(emailInput.value).toBe("wrong@example.com");
      expect(passwordInput.value).toBe("wrongpass123");

      // Submit button must be re-enabled for user retry
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe("2. Google OAuth Loading & Transition Flow", () => {
    it("displays appropriate status progression during credential exchange and redirects", async () => {
      process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id.apps.googleusercontent.com";

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
        user: { id: "g-1", email: "google.student@gmail.com", roles: ["STUDENT"] },
        access_token: "jwt-token",
      });

      render(<GoogleLoginButton redirectUrl="/app" />, { wrapper: createWrapper() });
      const googleButton = screen.getByRole("button", { name: /continue with google/i });
      fireEvent.click(googleButton);

      await waitFor(() => {
        expect(capturedCallback).toBeDefined();
      });

      // Credential callback arrives
      await act(async () => {
        await capturedCallback({ credential: "mock_google_id_token" });
      });

      expect(authApi.loginWithGoogle).toHaveBeenCalledWith({
        id_token: "mock_google_id_token",
      });
      expect(useAuthStore.getState().user?.email).toBe("google.student@gmail.com");
      expect(mockRefetchUser).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith("Successfully signed in with Google.");
      expect(mockPush).toHaveBeenCalledWith("/app");
    });

    it("dismisses loading overlay and shows recoverable toast on Google authentication failure", async () => {
      process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID = "mock-client-id.apps.googleusercontent.com";

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
        new ApiError("Google ID token key lookup failed.", 401, "INVALID_OAUTH_TOKEN")
      );

      render(<GoogleLoginButton redirectUrl="/app" />, { wrapper: createWrapper() });
      fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

      await waitFor(() => {
        expect(capturedCallback).toBeDefined();
      });

      await act(async () => {
        await capturedCallback({ credential: "bad_token" });
      });

      // Overlay should be dismissed
      await waitFor(() => {
        expect(screen.queryByRole("status")).not.toBeInTheDocument();
      });
      expect(toast.error).toHaveBeenCalledWith("Google ID token key lookup failed.");

      // Button should be interactive again
      await waitFor(() => {
        const googleButton = screen.getByRole("button", { name: /continue with google/i });
        expect(googleButton).not.toBeDisabled();
      });
    });
  });

  describe("3. Student Registration Loading Flow", () => {
    it("handles registration loading and displays success screen", async () => {
      (authApi.register as any).mockResolvedValueOnce({
        user: { id: "new-1", email: "newstudent@example.com" },
      });

      render(<SignupForm />, { wrapper: createWrapper() });

      fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "New Student" } });
      fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "newstudent@example.com" } });
      fireEvent.change(screen.getByPlaceholderText("••••••••••••"), { target: { value: "supersecret1234" } });

      const createBtn = screen.getByRole("button", { name: /create account/i });
      fireEvent.click(createBtn);

      await waitFor(() => {
        expect(authApi.register).toHaveBeenCalledWith({
          full_name: "New Student",
          email: "newstudent@example.com",
          password: "supersecret1234",
        });
      });

      // Verify success card is rendered
      await waitFor(() => {
        expect(screen.getByText("Account Created")).toBeInTheDocument();
        expect(screen.getByText("newstudent@example.com")).toBeInTheDocument();
      });

      // Overlay is cleanly removed
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  describe("4. SESSION_REVOKED & Session Recovery Modal", () => {
    it("displays modal on session displacement, disables duplicate Sign In Again clicks, and navigates to /login", async () => {
      // Simulate session displacement state
      useAuthStore.getState().setDisplacedSession(true, "Signed in on another browser.");

      render(<DisplacedSessionModal />, { wrapper: createWrapper() });

      // Modal must be visible
      expect(screen.getByText("You signed in on another device")).toBeInTheDocument();
      expect(screen.getByText("Signed in on another browser.")).toBeInTheDocument();

      const signInAgainBtn = screen.getByRole("button", { name: /sign in again/i });
      expect(signInAgainBtn).toBeInTheDocument();
      expect(signInAgainBtn).not.toBeDisabled();

      // Click "Sign In Again"
      fireEvent.click(signInAgainBtn);
      // Duplicate click
      fireEvent.click(signInAgainBtn);

      // Dismissal was called once and navigated to /login
      expect(mockDismissDisplacement).toHaveBeenCalledTimes(1);
      expect(mockPush).toHaveBeenCalledTimes(1);
      expect(mockPush).toHaveBeenCalledWith("/login");
      expect(useAuthStore.getState().isDisplacedSession).toBe(false);
    });
  });
});
