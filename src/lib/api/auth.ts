import { apiClient } from "./client";
import {
  GoogleOAuthPayload,
  LoginCredentials,
  LoginResponse,
  PasswordResetConfirmPayload,
  PasswordResetPayload,
  RegisterPayload,
  StaffOnboardingClaimPayload,
  User,
} from "@/types/auth";

export const authApi = {
  /**
   * Authenticate student or staff using email & password.
   * Sets HttpOnly session cookie __Host-lms_session.
   */
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>("/auth/login", credentials);
  },

  /**
   * Register a new student account.
   */
  register: async (payload: RegisterPayload): Promise<User> => {
    return apiClient.post<User>("/auth/register", payload);
  },

  /**
   * Terminate active session and clear cookie.
   */
  logout: async (): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/auth/logout", undefined, { timeoutMs: 5000 });
  },

  /**
   * Fetch currently authenticated user identity and role scopes.
   */
  getMe: async (): Promise<User> => {
    return apiClient.get<User>("/auth/me");
  },

  /**
   * Refresh session or token.
   */
  refreshToken: async (): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>("/auth/refresh");
  },

  /**
   * Verify email address using cryptographic token.
   */
  verifyEmail: async (token: string): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/auth/verify-email", { token });
  },

  /**
   * Resend email verification instructions.
   */
  resendVerification: async (email: string): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/auth/resend-verification", { email });
  },

  /**
   * Request password reset instructions via email.
   */
  requestPasswordReset: async (payload: PasswordResetPayload): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/auth/password-reset/request", payload);
  },

  /**
   * Confirm password reset with new password.
   */
  confirmPasswordReset: async (payload: PasswordResetConfirmPayload): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/auth/password-reset/confirm", payload);
  },

  /**
   * Authenticate via Google Identity OIDC token.
   */
  loginWithGoogle: async (payload: GoogleOAuthPayload): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>("/auth/oauth/google", payload);
  },

  /**
   * Claim staff invitation and set initial password.
   */
  claimStaffInvitation: async (payload: StaffOnboardingClaimPayload): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>("/auth/onboarding/claim", payload);
  },
};
