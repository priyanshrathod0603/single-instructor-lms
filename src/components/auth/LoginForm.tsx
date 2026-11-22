"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Lock, Mail, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { authApi } from "@/lib/api/auth";
import { useAuth } from "@/lib/hooks/useAuth";
import { parseApiError } from "@/lib/api/errors";
import { getSafeRedirectUrl } from "@/lib/security/redirect";

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email address is required")
    .email("Please enter a valid email address")
    .max(255),
  password: z
    .string()
    .min(1, "Password is required")
    .max(128),
});

type LoginFormData = z.infer<typeof loginSchema>;

export const LoginForm: React.FC = () => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectUrl = getSafeRedirectUrl(searchParams.get("redirect"), "/app");
  const { refetchUser } = useAuth();

  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<{ message: string; code?: string; requestId?: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Verifying your credentials…");

  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null);
    setIsLoading(true);
    setStatusMessage("Verifying your credentials…");

    try {
      await authApi.login({
        email: data.email.trim().toLowerCase(),
        password: data.password,
      });

      setStatusMessage("Establishing your session…");
      // Refetch user profile to populate auth context
      await refetchUser();

      setStatusMessage("Preparing your dashboard…");
      // Navigate to destination
      router.push(redirectUrl);
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      // Preserve form values; do NOT reset the form!
      setServerError({
        message: apiErr.message,
        code: apiErr.code,
        requestId: apiErr.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="w-full shadow-lg border-slate-200">
      <CardHeader className="space-y-1 text-center">
        <CardTitle className="font-heading text-2xl font-bold tracking-tight text-slate-900">
          Welcome back
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          Sign in to your learning dashboard
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {serverError && (
          <div className="space-y-2">
            <ErrorAlert
              title="Authentication Failed"
              message={serverError.message}
              requestId={serverError.requestId}
            />
            {serverError.code === "EMAIL_NOT_VERIFIED" && (
              <div className="text-center pt-1">
                <Link
                  href={`/verify-email?email=${encodeURIComponent(getValues("email").trim().toLowerCase())}`}
                  className="text-sm font-semibold text-brand-teal hover:underline inline-flex items-center gap-1"
                >
                  Verify your email address or request a new link
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            )}
          </div>
        )}

        <GoogleLoginButton redirectUrl={redirectUrl} />

        <div className="relative flex items-center justify-center">
          <div className="w-full border-t border-slate-200" />
          <span className="absolute bg-white px-3 font-sans text-xs text-slate-400 uppercase tracking-wider">
            or sign in with email
          </span>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-1">
            <Input
              label="Email Address"
              type="email"
              placeholder="name@example.com"
              autoComplete="email"
              error={errors.email?.message}
              {...register("email")}
            />
          </div>

          <div className="space-y-1 relative">
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor="password"
                className="font-sans text-sm font-medium text-slate-700"
              >
                Password
              </label>
              <Link
                href="/forgot-password"
                className="font-sans text-xs font-semibold text-primary-teal hover:underline"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••••••"
                autoComplete="current-password"
                error={errors.password?.message}
                {...register("password")}
                className="pr-12"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-0 top-0 h-11 w-11 flex items-center justify-center text-slate-400 hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-teal rounded-r-[10px]"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            disabled={isLoading || isSubmitting}
            isLoading={isLoading || isSubmitting}
            className="w-full mt-2"
          >
            Sign In
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </form>

        <AuthLoadingOverlay
          isOpen={isLoading}
          statusMessage={statusMessage}
          subMessage="Authenticating your account"
        />

        <p className="text-center font-sans text-sm text-slate-600">
          Don&apos;t have an account?{" "}
          <Link
            href="/signup"
            className="font-semibold text-primary-teal hover:underline"
          >
            Create student account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
};
