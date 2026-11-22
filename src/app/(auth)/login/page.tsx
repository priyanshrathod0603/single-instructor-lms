import React, { Suspense } from "react";
import { Metadata } from "next";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = {
  title: "Sign In | Single-Instructor LMS",
  description: "Sign in to access your courses, assignments, and curriculum.",
};

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-teal border-t-transparent" />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
