import React from "react";
import Link from "next/link";
import { ArrowLeft, BookOpen } from "lucide-react";
import { requireServerAuth } from "@/lib/auth/serverAuth";

export default async function LearnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Enforce server-side authenticated session
  await requireServerAuth({ redirectUrl: "/app" });

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Distraction-Free Header */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur-sm">
        <div className="flex h-14 items-center justify-between px-4 sm:px-6 max-w-7xl mx-auto w-full">
          <Link
            href="/app/courses"
            className="flex items-center gap-2 text-xs sm:text-sm font-semibold text-slate-700 hover:text-primary-teal transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Dashboard</span>
          </Link>

          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-teal text-white font-bold text-xs">
              L
            </span>
            <span className="font-heading text-sm font-bold text-slate-900 hidden sm:inline">
              Single-Instructor LMS
            </span>
          </div>
        </div>
      </header>

      {/* Main Focus Learning Canvas */}
      <main className="flex-1 flex flex-col min-w-0">
        {children}
      </main>
    </div>
  );
}
