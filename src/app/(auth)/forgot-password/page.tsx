"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { ArrowLeft, Mail, CheckCircle2 } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { authApi } from "@/lib/api/auth";
import { parseApiError } from "@/lib/api/errors";

const forgotPasswordSchema = z.object({
  email: z
    .string()
    .min(1, "Email address is required")
    .email("Please enter a valid email address"),
});

type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;

export default function ForgotPasswordPage() {
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [serverError, setServerError] = useState<{ message: string; requestId?: string } | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (data: ForgotPasswordFormData) => {
    setServerError(null);
    setIsLoading(true);
    try {
      await authApi.requestPasswordReset({ email: data.email.trim().toLowerCase() });
      setSubmittedEmail(data.email.trim().toLowerCase());
      setIsSubmitted(true);
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

  return (
    <Card className="w-full shadow-lg border-slate-200">
      <CardHeader className="space-y-1 text-center">
        <CardTitle className="font-heading text-2xl font-bold tracking-tight text-slate-900">
          Reset password
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          Enter your account email to receive a password recovery link
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {isSubmitted ? (
          <div className="space-y-4 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h3 className="font-heading text-lg font-bold text-slate-900">
              Check your inbox
            </h3>
            <p className="font-sans text-sm text-slate-600 leading-relaxed">
              If an account exists for <span className="font-semibold text-slate-900">{submittedEmail}</span>,
              we have sent instructions to reset your password.
            </p>
            <div className="pt-2">
              <Link href="/login">
                <Button variant="outline" className="w-full">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Return to sign in
                </Button>
              </Link>
            </div>
          </div>
        ) : (
          <>
            {serverError && (
              <ErrorAlert
                title="Request Failed"
                message={serverError.message}
                requestId={serverError.requestId}
              />
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <Input
                label="Email Address"
                type="email"
                placeholder="name@example.com"
                autoComplete="email"
                error={errors.email?.message}
                {...register("email")}
              />

              <Button
                type="submit"
                variant="primary"
                disabled={isLoading || isSubmitting}
                isLoading={isLoading || isSubmitting}
                className="w-full"
              >
                Send Reset Link
              </Button>
            </form>

            <AuthLoadingOverlay
              isOpen={isLoading}
              statusMessage="Sending recovery instructions…"
              subMessage="Please wait while we prepare your reset link"
            />

            <div className="text-center">
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 font-sans text-sm text-slate-600 hover:text-slate-900"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to sign in
              </Link>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
