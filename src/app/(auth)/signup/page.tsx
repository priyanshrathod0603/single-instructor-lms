import React, { Suspense } from "react";
import { Metadata } from "next";
import { SignupForm } from "@/components/auth/SignupForm";

export const metadata: Metadata = {
  title: "Create Student Account | Single-Instructor LMS",
  description: "Register to begin learning directly from the expert instructor.",
};

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-teal border-t-transparent" />
        </div>
      }
    >
      <SignupForm />
    </Suspense>
  );
}
