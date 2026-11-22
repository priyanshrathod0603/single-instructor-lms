"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, CheckCircle2, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { GoogleLoginButton } from "@/components/auth/GoogleLoginButton";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";
import { PasswordStrengthMeter } from "@/components/auth/PasswordStrengthMeter";
import { authApi } from "@/lib/api/auth";
import { parseApiError } from "@/lib/api/errors";

const signupSchema = z.object({
  full_name: z
    .string()
    .min(2, "Full name must be at least 2 characters")
    .max(128, "Full name cannot exceed 128 characters"),
  email: z
    .string()
    .min(1, "Email address is required")
    .email("Please enter a valid email address")
    .max(255),
  password: z
    .string()
    .min(12, "Password must be at least 12 characters long")
    .max(128, "Password cannot exceed 128 characters"),
});

type SignupFormData = z.infer<typeof signupSchema>;

export const SignupForm: React.FC = () => {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<{ message: string; requestId?: string } | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Creating your student account…");

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      full_name: "",
      email: "",
      password: "",
    },
  });

  const passwordValue = watch("password");

  const onSubmit = async (data: SignupFormData) => {
    setServerError(null);
    setIsLoading(true);
    setStatusMessage("Creating your student account…");

    try {
      await authApi.register({
        full_name: data.full_name.trim(),
        email: data.email.trim().toLowerCase(),
        password: data.password,
      });

      setRegisteredEmail(data.email.trim().toLowerCase());
      setIsSuccess(true);
      router.push(`/verify-email?email=${encodeURIComponent(data.email.trim().toLowerCase())}`);
    } catch (err: unknown) {
      const apiErr = parseApiError(err);
      // Retain form inputs!
      setServerError({
        message: apiErr.message,
        requestId: apiErr.requestId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (isSuccess) {
    return (
      <Card className="w-full shadow-lg border-slate-200">
        <CardContent className="pt-8 pb-8 px-6 text-center space-y-4">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <CheckCircle2 className="h-8 w-8" />
          </div>
          <h2 className="font-heading text-2xl font-bold text-slate-900">
            Account Created
          </h2>
          <p className="font-sans text-sm text-slate-600 leading-relaxed max-w-sm mx-auto">
            We sent a verification link to{" "}
            <span className="font-semibold text-slate-900">{registeredEmail}</span>.
            Please verify your email address to activate all learning features.
          </p>
          <div className="pt-4">
            <Link href="/login">
              <Button variant="primary" className="w-full">
                Continue to Sign In
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
          Create student account
        </CardTitle>
        <CardDescription className="text-sm text-slate-600">
          Enroll in courses and learn directly from the instructor
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {serverError && (
          <ErrorAlert
            title="Registration Failed"
            message={serverError.message}
            requestId={serverError.requestId}
          />
        )}

        <GoogleLoginButton redirectUrl="/app" />

        <div className="relative flex items-center justify-center">
          <div className="w-full border-t border-slate-200" />
          <span className="absolute bg-white px-3 font-sans text-xs text-slate-400 uppercase tracking-wider">
            or register with email
          </span>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <Input
            label="Full Name"
            type="text"
            placeholder="Jane Doe"
            autoComplete="name"
            error={errors.full_name?.message}
            {...register("full_name")}
          />

          <Input
            label="Email Address"
            type="email"
            placeholder="jane@example.com"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />

          <div className="space-y-1.5 relative">
            <div className="relative">
              <Input
                label="Password (min 12 characters)"
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
            disabled={isLoading || isSubmitting}
            isLoading={isLoading || isSubmitting}
            className="w-full mt-2"
          >
            Create Account
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </form>

        <AuthLoadingOverlay
          isOpen={isLoading}
          statusMessage={statusMessage}
          subMessage="Provisioning student credentials"
        />

        <p className="text-center font-sans text-sm text-slate-600">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-semibold text-primary-teal hover:underline"
          >
            Sign in instead
          </Link>
        </p>
      </CardContent>
    </Card>
  );
};
