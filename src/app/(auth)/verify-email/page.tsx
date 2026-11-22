"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, AlertCircle, ArrowRight, RefreshCw, Mail, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { authApi } from "@/lib/api/auth";
import { parseApiError } from "@/lib/api/errors";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const emailParam = searchParams.get("email");

  const [status, setStatus] = useState<"verifying" | "success" | "pending" | "error">(
    token ? "verifying" : "pending"
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [emailInput, setEmailInput] = useState(emailParam || "");
  const [isResending, setIsResending] = useState(false);
  const [countdown, setCountdown] = useState(0);

  // Countdown timer effect
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((c) => c - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  // Token verification effect
  useEffect(() => {
    if (!token) return;

    let isMounted = true;
    setStatus("verifying");

    authApi
      .verifyEmail(token)
      .then(() => {
        if (isMounted) setStatus("success");
      })
      .catch((err) => {
        if (isMounted) {
          const apiErr = parseApiError(err);
          setStatus("error");
          setErrorMessage(apiErr.message || "Invalid or expired verification token.");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleResend = async () => {
    const targetEmail = (emailInput || emailParam || "").trim().toLowerCase();
    if (!targetEmail) {
      toast.error("Please enter your registered email address.");
      return;
    }

    setIsResending(true);
    try {
      await authApi.resendVerification(targetEmail);
      toast.success("Verification link sent! Please check your inbox.");
      setCountdown(60); // 60s cooldown
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      toast.error(apiErr.message || "Failed to resend verification email.");
    } finally {
      setIsResending(false);
    }
  };

  return (
    <Card className="w-full shadow-lg border-slate-200">
      <CardHeader className="space-y-1 text-center">
        <CardTitle className="font-heading text-2xl font-bold tracking-tight text-slate-900">
          {status === "verifying" && "Verifying Email"}
          {status === "success" && "Email Verified"}
          {status === "pending" && "Check Your Email"}
          {status === "error" && "Verification Failed"}
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          {status === "verifying" && "Confirming your credentials with the server"}
          {status === "success" && "Your learning account is now activated"}
          {status === "pending" && "One click away from activating your account"}
          {status === "error" && "The verification token could not be validated"}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6 pt-2 pb-8 text-center">
        {/* State 1: Verifying active token */}
        {status === "verifying" && (
          <div className="py-4">
            <AuthLoadingOverlay
              isOpen={true}
              isFullScreen={false}
              statusMessage="Verifying your email address…"
              subMessage="Confirming your credentials with the server"
            />
          </div>
        )}

        {/* State 2: Verification Successful */}
        {status === "success" && (
          <div className="space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h3 className="font-heading text-xl font-bold text-slate-900">
              Email Verified Successfully!
            </h3>
            <p className="font-sans text-sm text-slate-600 leading-relaxed max-w-sm mx-auto">
              Your email address has been confirmed. You can now sign in to access your dashboard, courses, and certificates.
            </p>
            <div className="pt-4">
              <Link href="/login" className="w-full inline-block">
                <Button variant="primary" className="w-full">
                  Sign In to Your Account
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* State 3: Pending verification confirmation screen */}
        {status === "pending" && (
          <div className="space-y-5">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-brand-mint text-brand-teal">
              <Mail className="h-8 w-8" />
            </div>
            
            <div className="space-y-2">
              <p className="font-sans text-sm text-slate-600 leading-relaxed max-w-sm mx-auto">
                We sent a verification link to:
              </p>
              {emailParam ? (
                <div className="inline-block px-3 py-1.5 rounded-md bg-slate-100 text-slate-800 font-semibold text-sm break-all">
                  {emailParam}
                </div>
              ) : (
                <div className="max-w-xs mx-auto text-left">
                  <Input
                    type="email"
                    placeholder="you@example.com"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    className="text-center"
                  />
                </div>
              )}
              <p className="font-sans text-xs text-slate-500 max-w-sm mx-auto pt-1">
                Please open the link in your email to verify your account. If you don&apos;t see it, check your spam folder.
              </p>
            </div>

            <div className="pt-2 space-y-3">
              {/* Open Gmail Action */}
              <a
                href="https://mail.google.com"
                target="_blank"
                rel="noopener noreferrer"
                className="w-full inline-block"
              >
                <Button variant="primary" className="w-full">
                  <Mail className="mr-2 h-4 w-4" />
                  Open Gmail
                  <ExternalLink className="ml-2 h-4 w-4 opacity-70" />
                </Button>
              </a>

              {/* Resend Verification Action */}
              <Button
                type="button"
                variant="outline"
                onClick={handleResend}
                disabled={isResending || countdown > 0}
                isLoading={isResending}
                className="w-full"
              >
                <RefreshCw className={cn("mr-2 h-4 w-4", isResending && "animate-spin")} />
                {countdown > 0 ? `Resend email in ${countdown}s` : "Resend verification email"}
              </Button>

              <div className="pt-2">
                <Link href="/login" className="text-sm font-medium text-brand-teal hover:underline">
                  Already verified? Back to Sign In
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* State 4: Error during verification */}
        {status === "error" && (
          <div className="space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-rose-100 text-rose-600">
              <AlertCircle className="h-8 w-8" />
            </div>
            <h3 className="font-heading text-xl font-bold text-slate-900">
              Verification Failed
            </h3>
            <p className="font-sans text-sm text-rose-700 leading-relaxed max-w-sm mx-auto">
              {errorMessage || "The verification link is invalid, expired, or has already been used."}
            </p>

            <div className="pt-3 max-w-xs mx-auto space-y-3">
              <div className="text-left space-y-1.5">
                <label className="text-xs font-semibold text-slate-700">Enter your email to get a new link:</label>
                <Input
                  type="email"
                  placeholder="your.email@example.com"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                />
              </div>

              <Button
                type="button"
                variant="primary"
                onClick={handleResend}
                disabled={isResending || countdown > 0}
                isLoading={isResending}
                className="w-full"
              >
                <RefreshCw className={cn("mr-2 h-4 w-4", isResending && "animate-spin")} />
                {countdown > 0 ? `Resend in ${countdown}s` : "Request New Verification Link"}
              </Button>

              <div className="pt-2">
                <Link href="/login">
                  <Button variant="ghost" className="w-full text-slate-600">
                    Back to Sign In
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-teal border-t-transparent" />
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
