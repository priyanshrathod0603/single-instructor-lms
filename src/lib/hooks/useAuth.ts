"use client";

import { useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/lib/store/authStore";
import { authApi } from "@/lib/api/auth";
import { User, UserRole } from "@/types/auth";
import { ApiError, parseApiError } from "@/lib/api/errors";
import { toast } from "sonner";

const ROLE_HIERARCHY: Record<string, number> = {
  SUPER_ADMIN: 100,
  ADMIN: 80,
  INSTRUCTOR: 60,
  TEACHING_ASSISTANT: 40,
  STUDENT: 20,
};

export function useAuth() {
  const queryClient = useQueryClient();
  const {
    user,
    isInitialized,
    isDisplacedSession,
    displacementReason,
    setUser,
    setDisplacedSession,
    logout: clearStore,
  } = useAuthStore();

  const {
    data: fetchedUser,
    isLoading,
    error,
    refetch,
  } = useQuery<User, ApiError>({
    queryKey: ["auth", "me"],
    queryFn: authApi.getMe,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: (failureCount, error) => {
      // Never retry on 401 or 403
      if (error?.status === 401 || error?.status === 403) return false;
      return failureCount < 2;
    },
    // Don't auto-fetch if session was displaced
    enabled: !isDisplacedSession,
  });

  const router = useRouter();

  useEffect(() => {
    if (fetchedUser) {
      setUser(fetchedUser);
    } else if (error && error.status === 401) {
      setUser(null);
    }
  }, [fetchedUser, error, setUser]);

  // Clean stale query cache when session displacement occurs
  useEffect(() => {
    if (isDisplacedSession) {
      queryClient.cancelQueries({ queryKey: ["auth"] });
      queryClient.setQueryData(["auth", "me"], null);
    }
  }, [isDisplacedSession, queryClient]);

  const logoutMutation = useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      // Disable Google Identity Services auto-select to prevent auto-login dead loop upon landing on /login
      if (typeof window !== "undefined" && (window as any).google?.accounts?.id) {
        try {
          (window as any).google.accounts.id.disableAutoSelect();
          (window as any).google.accounts.id.cancel();
        } catch {
          // ignore GSI cleanup errors
        }
      }
      clearStore();
      queryClient.clear();
      queryClient.setQueryData(["auth", "me"], null);
      router.push("/login");
    },
    onError: (err: unknown) => {
      const apiErr = parseApiError(err);
      // Whether the server returned 401, timed out, or had a network/server failure,
      // the user explicitly requested to sign out: clear client state and redirect to /login.
      if (typeof window !== "undefined" && (window as any).google?.accounts?.id) {
        try {
          (window as any).google.accounts.id.disableAutoSelect();
          (window as any).google.accounts.id.cancel();
        } catch {
          // ignore GSI cleanup errors
        }
      }
      clearStore();
      queryClient.clear();
      queryClient.setQueryData(["auth", "me"], null);
      if (apiErr.status !== 401) {
        toast.info("Signed out locally. Server session expired or unreachable.");
      }
      router.push("/login");
    },
  });

  const hasRole = useCallback(
    (requiredRole: UserRole): boolean => {
      if (!user || !user.roles) return false;
      if (user.roles.includes("SUPER_ADMIN")) return true;
      if (user.roles.includes(requiredRole)) return true;

      const userMaxRank = Math.max(
        ...user.roles.map((r) => ROLE_HIERARCHY[r] || 0)
      );
      const requiredRank = ROLE_HIERARCHY[requiredRole] || 0;
      return userMaxRank >= requiredRank;
    },
    [user]
  );

  const hasAnyRole = useCallback(
    (roles: UserRole[]): boolean => {
      return roles.some((role) => hasRole(role));
    },
    [hasRole]
  );

  const dismissDisplacement = useCallback(() => {
    queryClient.cancelQueries({ queryKey: ["auth"] });
    queryClient.setQueryData(["auth", "me"], null);
    setDisplacedSession(false, null);
    clearStore();
  }, [setDisplacedSession, clearStore, queryClient]);

  return {
    user,
    isAuthenticated: !!user,
    isLoading: !isInitialized && isLoading,
    isDisplacedSession,
    displacementReason,
    hasRole,
    hasAnyRole,
    logout: logoutMutation.mutateAsync,
    isLoggingOut: logoutMutation.isPending,
    refetchUser: refetch,
    dismissDisplacement,
  };
}
