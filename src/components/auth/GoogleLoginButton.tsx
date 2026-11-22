"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { authApi } from "@/lib/api/auth";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/hooks/useAuth";
import { useAuthStore } from "@/lib/store/authStore";
import { parseApiError } from "@/lib/api/errors";
import { GoogleCredentialResponse, PromptMomentNotification } from "@/types/google";
import { getSafeRedirectUrl } from "@/lib/security/redirect";

interface GoogleLoginButtonProps {
  redirectUrl?: string;
}

const GSI_SCRIPT_URL = "https://accounts.google.com/gsi/client";
const GSI_SCRIPT_ID = "google-gsi-client";

/**
 * Dynamically loads the official Google Identity Services client script.
 */
function loadGoogleIdentityScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined") {
      resolve();
      return;
    }

    if (window.google?.accounts?.id) {
      resolve();
      return;
    }

    const existingScript = document.getElementById(GSI_SCRIPT_ID) as HTMLScriptElement | null;
    if (existingScript) {
      if (window.google?.accounts?.id) {
        resolve();
      } else {
        existingScript.addEventListener("load", () => resolve(), { once: true });
        existingScript.addEventListener("error", () => reject(new Error("Failed to load Google Identity Services")), {
          once: true,
        });
      }
      return;
    }

    const script = document.createElement("script");
    script.id = GSI_SCRIPT_ID;
    script.src = GSI_SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Identity Services script from Google CDN"));
    document.head.appendChild(script);
  });
}

export const GoogleLoginButton: React.FC<GoogleLoginButtonProps> = ({
  redirectUrl = "/app",
}) => {
  const router = useRouter();
  const { refetchUser } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [isOverlayOpen, setIsOverlayOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Connecting securely…");
  const isInitializedRef = useRef(false);
  const isProcessingRef = useRef(false);
  const popupTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const redirectUrlRef = useRef(redirectUrl);
  const googleButtonContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    redirectUrlRef.current = redirectUrl;
  }, [redirectUrl]);

  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  /**
   * Handle credential response from Google Identity Services OIDC popup / One Tap.
   */
  const handleCredentialResponse = useCallback(
    async (response: GoogleCredentialResponse) => {
      // Clear popup click timeout if active
      if (popupTimeoutRef.current) {
        clearTimeout(popupTimeoutRef.current);
        popupTimeoutRef.current = null;
      }

      // Prevent concurrent duplicate executions
      if (isProcessingRef.current) {
        return;
      }
      isProcessingRef.current = true;

      if (!response?.credential) {
        toast.error("Google authentication failed: No ID token returned from Google.");
        setIsLoading(false);
        setIsOverlayOpen(false);
        isProcessingRef.current = false;
        return;
      }

      // Step 1: Credential callback begins
      setIsLoading(true);
      setIsOverlayOpen(true);
      setStatusMessage("Connecting securely…");

      try {
        // Step 2: Exchanging ID token with backend
        setStatusMessage("Verifying your credentials…");
        const loginRes = await authApi.loginWithGoogle({ id_token: response.credential });

        if (loginRes?.user) {
          useAuthStore.getState().setUser(loginRes.user);
        }

        // Step 3: Session establishment & user-state synchronization
        setStatusMessage("Establishing your session…");
        await refetchUser();
        toast.success("Successfully signed in with Google.");

        // Step 4: Dashboard preparation & transition
        setStatusMessage("Preparing your dashboard…");
        const safeUrl = getSafeRedirectUrl(redirectUrlRef.current, "/app");
        let targetUrl = safeUrl;
        if (!targetUrl || targetUrl === "/app") {
          const roles = loginRes?.user?.roles || [];
          if (
            roles.includes("SUPER_ADMIN") ||
            roles.includes("ADMIN") ||
            roles.includes("INSTRUCTOR")
          ) {
            targetUrl = "/admin";
          } else {
            targetUrl = "/app";
          }
        }
        targetUrl = getSafeRedirectUrl(targetUrl, "/app");

        router.push(targetUrl);
        router.refresh();
      } catch (err: unknown) {
        const apiErr = parseApiError(err);
        toast.error(apiErr.message || "Google authentication failed.");
      } finally {
        // CRITICAL: Ensure overlay and loading state are ALWAYS dismissed in every terminal state
        setIsLoading(false);
        setIsOverlayOpen(false);
        isProcessingRef.current = false;
      }
    },
    [refetchUser, router]
  );

  /**
   * Initialize Google Identity Services if Client ID is configured.
   */
  const initGsi = useCallback(async () => {
    if (!clientId || typeof window === "undefined") return;

    try {
      await loadGoogleIdentityScript();
      if (window.google?.accounts?.id) {
        if (!isInitializedRef.current) {
          // Plain HTTP over non-loopback LAN IPs is NOT a secure context and causes FedCM to abort.
          // Disable FedCM on insecure origins so Google Identity Services uses standard popup.
          const isSecure = typeof window !== "undefined" && window.isSecureContext === true;

          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: handleCredentialResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
            use_fedcm_for_prompt: isSecure,
          });
          isInitializedRef.current = true;
        }

        // Render official button in invisible overlay if renderButton is supported and container exists
        if (
          typeof window.google.accounts.id.renderButton === "function" &&
          googleButtonContainerRef.current
        ) {
          googleButtonContainerRef.current.innerHTML = "";
          window.google.accounts.id.renderButton(googleButtonContainerRef.current, {
            type: "standard",
            theme: "outline",
            size: "large",
            text: "continue_with",
            shape: "rectangular",
            width: "360",
            click_listener: () => {
              setIsLoading(true);
              // Reset loading if user cancels popup without completing
              if (popupTimeoutRef.current) clearTimeout(popupTimeoutRef.current);
              popupTimeoutRef.current = setTimeout(() => {
                setIsLoading(false);
              }, 20000);
            },
          });
        }
      }
    } catch {
      // Non-fatal on background preload; user click will retry
    }
  }, [clientId, handleCredentialResponse]);

  useEffect(() => {
    if (clientId) {
      initGsi();
    }
    return () => {
      if (popupTimeoutRef.current) {
        clearTimeout(popupTimeoutRef.current);
        popupTimeoutRef.current = null;
      }
      setIsLoading(false);
      setIsOverlayOpen(false);
      isProcessingRef.current = false;
      try {
        window.google?.accounts?.id?.cancel();
      } catch {
        // Clean unmount
      }
    };
  }, [clientId, initGsi]);

  const handleGoogleClick = async () => {
    if (!clientId) {
      toast.info(
        "Google Sign-In is configured on the backend. Provide NEXT_PUBLIC_GOOGLE_CLIENT_ID for live OIDC popup."
      );
      return;
    }

    setIsLoading(true);
    try {
      await loadGoogleIdentityScript();

      if (!window.google?.accounts?.id) {
        throw new Error("Google Identity Services is unavailable.");
      }

      // Initialize only if not already initialized
      if (!isInitializedRef.current) {
        const isSecure = typeof window !== "undefined" && window.isSecureContext === true;
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: handleCredentialResponse,
          auto_select: false,
          cancel_on_tap_outside: true,
          use_fedcm_for_prompt: isSecure,
        });
        isInitializedRef.current = true;
      }

      // Trigger the prompt (One Tap / Credential chooser)
      window.google.accounts.id.prompt((notification: PromptMomentNotification) => {
        if (notification.isNotDisplayed()) {
          setIsLoading(false);
          const reason = notification.getNotDisplayedReason?.() || "popup_blocked";
          if (reason === "opt_out_or_no_session") {
            toast.error("No active Google session found. Please sign in to Google first or use email/password.");
          } else {
            toast.error(
              "Google Sign-In prompt could not be displayed. Please check your browser popup/cookie settings."
            );
          }
        } else if (notification.isSkippedMoment() || notification.isDismissedMoment()) {
          setIsLoading(false);
        }
      });
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      toast.error(apiErr.message || "Failed to initialize Google Sign-In.");
      setIsLoading(false);
    }
  };

  return (
    <div className="relative w-full">
      <Button
        type="button"
        variant="outline"
        onClick={handleGoogleClick}
        disabled={isLoading || isOverlayOpen}
        isLoading={isLoading && !isOverlayOpen}
        className="w-full border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-sm font-medium min-h-[44px]"
      >
        <svg className="mr-2.5 h-4 w-4" viewBox="0 0 24 24">
          <path
            fill="#4285F4"
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
          />
          <path
            fill="#34A853"
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          />
          <path
            fill="#FBBC05"
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
          />
          <path
            fill="#EA4335"
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
          />
        </svg>
        Continue with Google
      </Button>

      {/* Invisible Google official iframe overlay for genuine popup authentication on non-FedCM contexts */}
      {clientId && (
        <div
          ref={googleButtonContainerRef}
          className="absolute inset-0 opacity-0 overflow-hidden z-10 flex items-center justify-center pointer-events-auto [&>div]:!w-full [&>div]:!h-full [&_iframe]:!w-full [&_iframe]:!h-full [&_iframe]:!cursor-pointer"
          style={{ width: "100%", height: "100%" }}
        />
      )}

      <AuthLoadingOverlay
        isOpen={isOverlayOpen}
        statusMessage={statusMessage}
        subMessage="Google Identity Services"
      />
    </div>
  );
};
