import React from "react";
import Link from "next/link";
import { GraduationCap, CheckCircle2, Star, ShieldCheck } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-warm-cream/40">
      {/* Left Column: Brand Storytelling & Social Proof (Desktop only: lg:flex) */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-primary-teal bg-[#006B60] p-12 text-white relative overflow-hidden">
        {/* Subtle decorative circles */}
        <div className="absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/5 pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 h-96 w-96 rounded-full bg-white/5 pointer-events-none" />

        <div className="relative z-10">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-[12px] bg-white text-primary-teal shadow-md">
              <GraduationCap className="h-6 w-6" />
            </div>
            <span className="font-heading text-2xl font-bold tracking-tight text-white">
              Instructor<span className="text-accent-coral">LMS</span>
            </span>
          </Link>

          <div className="mt-16 max-w-md space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/15 border border-white/20 px-3.5 py-1 text-xs font-semibold text-accent-mint backdrop-blur-sm">
              <Star className="h-3.5 w-3.5 fill-current" />
              <span>Direct Single-Instructor Mentorship</span>
            </div>
            <h1 className="font-heading text-[clamp(1.75rem,2.5vw+0.5rem,2.5rem)] font-extrabold leading-snug tracking-tight text-white">
              Master the craft from real-world practitioners.
            </h1>
            <p className="font-sans text-base text-slate-100 leading-relaxed">
              No generic tutorials. Every lesson is crafted with production-ready
              rigor, hands-on assignments, and personalized evaluations.
            </p>
          </div>
        </div>

        {/* Value Proposition Highlights */}
        <div className="relative z-10 space-y-4 pt-8 border-t border-white/20">
          <div className="flex items-center gap-3 text-sm text-slate-100 font-medium">
            <CheckCircle2 className="h-5 w-5 text-accent-mint shrink-0" />
            <span>Structured modular curriculum with real projects</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-100 font-medium">
            <CheckCircle2 className="h-5 w-5 text-accent-mint shrink-0" />
            <span>Direct instructor feedback on your code & assignments</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-100 font-medium">
            <ShieldCheck className="h-5 w-5 text-accent-mint shrink-0" />
            <span>Cryptographically verifiable completion certificates</span>
          </div>
        </div>

        {/* Footer note */}
        <div className="relative z-10 text-xs text-slate-200">
          © {new Date().getFullYear()} Single-Instructor LMS. All rights reserved.
        </div>
      </div>

      {/* Right Column: Form Container (Mobile: full width, Desktop: 1/2 width) */}
      <div className="flex w-full lg:w-1/2 flex-col justify-center px-4 py-8 sm:px-6 sm:py-12 lg:px-12 bg-warm-cream/50">
        <div className="mx-auto w-full max-w-md">
          {/* Mobile brand header */}
          <div className="mb-8 flex lg:hidden items-center justify-center">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-primary-teal bg-[#006B60] text-white shadow-sm">
                <GraduationCap className="h-6 w-6" />
              </div>
              <span className="font-heading text-xl font-bold tracking-tight text-slate-900">
                Instructor<span className="text-primary-teal">LMS</span>
              </span>
            </Link>
          </div>

          {children}
        </div>
      </div>
    </div>
  );
}
