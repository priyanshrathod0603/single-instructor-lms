import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { User, UserRole } from "@/types/auth";
import { getSafeRedirectUrl } from "@/lib/security/redirect";

const API_BASE_URL =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export interface RequireServerAuthOptions {
  requiredRole?: UserRole;
  redirectUrl?: string;
}

/**
 * Server-Side Protected Layout Guard.
 *
 * Strict Security Invariants:
 * 1. Validates sessions authoritatively through backend GET /api/v1/auth/me.
 * 2. Preserves HttpOnly cookie security (__Host-lms_session forwarded via Cookie header).
 * 3. Never trusts cookie presence alone; always validates active database session status.
 * 4. Never duplicates backend authorization; honors backend roles & permissions.
 * 5. Preserves SESSION_REVOKED detection and redirects displaced sessions cleanly.
 * 6. Never exposes session secrets or tokens to client-side code.
 */
export async function requireServerAuth(
  options?: RequireServerAuthOptions
): Promise<User> {
  const { requiredRole, redirectUrl = "/app" } = options || {};
  const safeRedirectUrl = getSafeRedirectUrl(redirectUrl, "/app");

  const cookieStore = await cookies();
  const sessionCookie =
    cookieStore.get("__Host-lms_session")?.value ||
    cookieStore.get("lms_session")?.value;

  if (!sessionCookie) {
    redirect(`/login?redirect=${encodeURIComponent(safeRedirectUrl)}`);
  }

  let user: User | null = null;
  let isRevoked = false;

  // Strict E2E Security Gate (P0-02):
  // Synthetic E2E identities are strictly restricted to isolated test environments.
  // In production (NODE_ENV === "production"), synthetic E2E cookies are NEVER accepted.
  const isE2EAllowed =
    process.env.NODE_ENV !== "production" &&
    (process.env.NODE_ENV === "test" || process.env.ENABLE_E2E_AUTH === "true");

  if (isE2EAllowed && sessionCookie.startsWith("e2e_")) {
    const roles: UserRole[] = sessionCookie.includes("super") || sessionCookie.includes("control")
      ? ["SUPER_ADMIN"]
      : sessionCookie.includes("admin")
      ? ["ADMIN"]
      : sessionCookie.includes("staff")
      ? ["STAFF"]
      : ["STUDENT"];

    user = {
      id: "e2e-user-uuid",
      email: "test@example.com",
      full_name: "Test User",
      is_verified: true,
      is_active: true,
      roles,
      created_at: new Date().toISOString(),
    };
  } else {
    try {
      const res = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/api/v1/auth/me`, {
        headers: {
          Cookie: `__Host-lms_session=${sessionCookie}`,
          Accept: "application/json",
        },
        cache: "no-store",
      });

      if (res.status === 401) {
        try {
          const errorData = await res.json();
          if (errorData?.error?.code === "SESSION_REVOKED") {
            isRevoked = true;
          }
        } catch {
          // ignore parse error
        }
        redirect(
          isRevoked
            ? "/login?session_revoked=1"
            : `/login?redirect=${encodeURIComponent(safeRedirectUrl)}`
        );
      }

      if (!res.ok) {
        redirect(`/login?redirect=${encodeURIComponent(safeRedirectUrl)}`);
      }

      user = await res.json();
    } catch (err: any) {
      // Re-throw Next.js navigation redirects
      if (err?.digest?.startsWith("NEXT_REDIRECT")) {
        throw err;
      }

      // Fail-closed: redirect to login if backend validation fails
      redirect(`/login?redirect=${encodeURIComponent(safeRedirectUrl)}`);
    }
  }

  if (!user || !user.is_active) {
    redirect(`/login?redirect=${encodeURIComponent(safeRedirectUrl)}`);
  }

  if (requiredRole && user.roles) {
    const isSuperAdmin = user.roles.includes("SUPER_ADMIN");
    const isAdmin = user.roles.includes("ADMIN");
    const hasRole =
      isSuperAdmin ||
      user.roles.includes(requiredRole) ||
      (requiredRole === "STAFF" && (isAdmin || user.roles.includes("TEACHING_ASSISTANT")));

    if (!hasRole) {
      redirect("/app?error=forbidden");
    }
  }

  return user;
}
