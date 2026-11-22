"use client";

import React, { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { Eye, EyeOff, ShieldCheck, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { PasswordStrengthMeter } from "@/components/auth/PasswordStrengthMeter";
import { authApi } from "@/lib/api/auth";
import { parseApiError } from "@/lib/api/errors";
import { useAuth } from "@/lib/hooks/useAuth";

const claimSchema = z.object({
  full_name: z
    .string()
    .min(2, "Full name must be at least 2 characters")
    .max(128, "Full name cannot exceed 128 characters"),
  password: z
    .string()
    .min(12, "Password must be at least 12 characters long")
    .max(128, "Password cannot exceed 128 characters"),
});

type ClaimFormData = z.infer<typeof claimSchema>;

function ClaimStaffForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const { refetchUser } = useAuth();

  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<{ message: string; requestId?: string } | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ClaimFormData>({
    resolver: zodResolver(claimSchema),
    defaultValues: { full_name: "", password: "" },
  });

  const passwordValue = watch("password");

  const onSubmit = async (data: ClaimFormData) => {
    if (!token) {
      setServerError({ message: "Missing invitation token in URL query." });
      return;
    }

    setServerError(null);
    try {
      await authApi.claimStaffInvitation({
        token,
        full_name: data.full_name.trim(),
        password: data.password,
      });

      await refetchUser();
      router.push("/staff");
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      setServerError({
        message: apiErr.message,
        requestId: apiErr.requestId,
      });
    }
  };

  if (!token) {
    return (
      <Card className="w-full shadow-lg border-slate-200">
        <CardContent className="pt-8 pb-8 px-6 text-center space-y-4">
          <ErrorAlert
            title="Invalid Invitation Link"
            message="No staff invitation token was provided. Please check the onboarding link received from your administrator."
          />
          <div className="pt-4">
            <Link href="/login">
              <Button variant="primary" className="w-full">
                Go to Sign In
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
        <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-accent-mint text-primary-teal">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <CardTitle className="font-heading text-2xl font-bold tracking-tight text-slate-900">
          Claim Staff Invitation
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          Set up your staff profile and credentials to join the teaching team
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {serverError && (
          <ErrorAlert
            title="Invitation Claim Failed"
            message={serverError.message}
            requestId={serverError.requestId}
          />
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Input
            label="Full Name"
            type="text"
            placeholder="Dr. Alex Rivera"
            autoComplete="name"
            error={errors.full_name?.message}
            {...register("full_name")}
          />

          <div className="space-y-1.5 relative">
            <div className="relative">
              <Input
                label="Create Staff Password (min 12 characters)"
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

          <Button
            type="submit"
            variant="primary"
            isLoading={isSubmitting}
            className="w-full mt-2"
          >
            Activate Staff Account
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ClaimStaffPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-teal border-t-transparent" />
        </div>
      }
    >
      <ClaimStaffForm />
    </Suspense>
  );
}
