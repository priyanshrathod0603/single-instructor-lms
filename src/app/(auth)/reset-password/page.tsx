"use client";

import React, { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { Eye, EyeOff, CheckCircle2, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { PasswordStrengthMeter } from "@/components/auth/PasswordStrengthMeter";
import { authApi } from "@/lib/api/auth";
import { parseApiError } from "@/lib/api/errors";

const resetPasswordSchema = z
  .object({
    password: z
      .string()
      .min(12, "Password must be at least 12 characters long")
      .max(128, "Password cannot exceed 128 characters"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<{ message: string; requestId?: string } | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });

  const passwordValue = watch("password");

  const onSubmit = async (data: ResetPasswordFormData) => {
    if (!token) {
      setServerError({ message: "Invalid or missing password reset token." });
      return;
    }

    setServerError(null);
    setIsLoading(true);
    try {
      await authApi.confirmPasswordReset({
        token,
        new_password: data.password,
      });
      setIsSuccess(true);
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      setServerError({
        message: apiErr.message,
        requestId: apiErr.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) {
    return (
      <Card className="w-full shadow-lg border-slate-200">
        <CardContent className="pt-8 pb-8 px-6 text-center space-y-4">
          <ErrorAlert
            title="Invalid Link"
            message="No password reset token was provided in the URL. Please request a new reset link."
          />
          <div className="pt-4">
            <Link href="/forgot-password">
              <Button variant="primary" className="w-full">
                Request New Reset Link
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isSuccess) {
    return (
      <Card className="w-full shadow-lg border-slate-200">
        <CardContent className="pt-8 pb-8 px-6 text-center space-y-4">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <CheckCircle2 className="h-8 w-8" />
          </div>
          <h2 className="font-heading text-2xl font-bold text-slate-900">
            Password Reset Complete
          </h2>
          <p className="font-sans text-sm text-slate-600 leading-relaxed max-w-sm mx-auto">
            Your account password has been updated. You can now sign in with your new password.
          </p>
          <div className="pt-4">
            <Link href="/login">
              <Button variant="primary" className="w-full">
                Sign In Now
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full shadow-lg border-slate-200">
      <CardHeader className="space-y-1 text-center">
        <CardTitle className="font-heading text-2xl font-bold tracking-tight text-slate-900">
          Set new password
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          Choose a strong, compliant password with at least 12 characters
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {serverError && (
          <ErrorAlert
            title="Password Reset Failed"
            message={serverError.message}
            requestId={serverError.requestId}
          />
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-1.5 relative">
            <div className="relative">
              <Input
                label="New Password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••••••"
                autoComplete="new-password"
                error={errors.password?.message}
                {...register("password")}
                className="pr-12"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-0 top-7 h-11 w-11 flex items-center justify-center text-slate-400 hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-teal rounded-r-[10px]"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <PasswordStrengthMeter password={passwordValue} />
          </div>

          <Input
            label="Confirm New Password"
            type={showPassword ? "text" : "password"}
            placeholder="••••••••••••"
            autoComplete="new-password"
            error={errors.confirmPassword?.message}
            {...register("confirmPassword")}
          />

          <Button
            type="submit"
            variant="primary"
            disabled={isLoading || isSubmitting}
            isLoading={isLoading || isSubmitting}
            className="w-full mt-2"
          >
            Update Password
          </Button>
        </form>

        <AuthLoadingOverlay
          isOpen={isLoading}
          statusMessage="Resetting your password…"
          subMessage="Updating your credentials securely"
        />
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-teal border-t-transparent" />
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
