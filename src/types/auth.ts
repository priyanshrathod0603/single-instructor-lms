export type UserRole = "STUDENT" | "STAFF" | "TEACHING_ASSISTANT" | "INSTRUCTOR" | "ADMIN" | "SUPER_ADMIN" | string;

export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string | null;
  is_verified: boolean;
  is_active: boolean;
  roles: UserRole[];
  created_at: string;
}

export interface UserResponse extends User {}

export interface LoginResponse {
  user: User;
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
}

export interface PasswordResetPayload {
  email: string;
}

export interface PasswordResetConfirmPayload {
  token: string;
  new_password: string;
}

export interface GoogleOAuthPayload {
  id_token: string;
}

export interface StaffOnboardingClaimPayload {
  token: string;
  password: string;
  full_name: string;
}

export interface AuthSession {
  id: string;
  user_id: string;
  ip_address?: string;
  user_agent?: string;
  status: "ACTIVE" | "REVOKED" | "EXPIRED";
  created_at: string;
  last_activity_at?: string;
}
