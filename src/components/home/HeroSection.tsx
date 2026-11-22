"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Award,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { TypewriterText } from "./TypewriterText";

export const HeroSection: React.FC = () => {
  return (
    <section className="relative overflow-hidden border-b border-soft-peach/60 bg-gradient-to-b from-warm-cream via-white to-warm-cream/40 py-12 sm:py-20 lg:py-24">
      {/* Background radial accent glow */}
      <div
        className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 h-[450px] w-[750px] rounded-full bg-gradient-to-br from-accent-mint/40 via-accent-peach/20 to-transparent blur-3xl"
        aria-hidden="true"
      />

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          {/* Top category badge */}
          <div className="mb-6 flex justify-center">
            <Badge variant="mint" size="md" className="shadow-subtle py-1 px-3.5 border border-primary-teal/20 text-slate-800">
              <Sparkles className="mr-1.5 h-3.5 w-3.5 text-primary-teal" />
              <span className="font-semibold text-slate-800">
                Single-Instructor Direct Learning Platform
              </span>
            </Badge>
          </div>

          {/* Fluid Responsive Heading with Zero-Layout-Shift Typewriter */}
          <h1 className="font-heading font-extrabold tracking-tight text-slate-900 text-center leading-[1.2] text-[clamp(1.75rem,3.2vw+0.75rem,3.25rem)] text-balance">
            <span className="block text-slate-900">Master</span>
            <span className="block text-primary-teal font-extrabold min-h-[1.25em] my-1">
              <TypewriterText />
            </span>
            <span className="block text-slate-900">Directly from an Expert.</span>
          </h1>

          {/* High-contrast subtitle */}
          <p className="mt-6 font-sans text-base sm:text-lg lg:text-xl text-slate-800 max-w-2xl mx-auto leading-relaxed text-balance">
            Rigorous masterclasses, real-world codebase walkthroughs, and personal rubric
            evaluations designed to turn practicing engineers into technical architects.
          </p>

          {/* Action CTAs */}
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/courses" className="w-full sm:w-auto">
              <Button
                variant="primary"
                size="lg"
                className="w-full sm:w-auto shadow-elevated"
              >
                Browse All Masterclasses
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </Link>
            <Link href="/signup" className="w-full sm:w-auto">
              <Button
                variant="outline"
                size="lg"
                className="w-full sm:w-auto"
              >
                Create Student Account
              </Button>
            </Link>
          </div>

          {/* Verified Architectural Hallmarks (Zero Fake Data) */}
          <div className="mt-12 pt-8 border-t border-soft-peach/80 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs sm:text-sm font-sans text-slate-800">
            <div className="flex items-center justify-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-primary-teal shrink-0" />
              <span className="font-semibold text-slate-800">Direct Rubric Evaluations</span>
            </div>
            <div className="flex items-center justify-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary-teal shrink-0" />
              <span className="font-semibold text-slate-800">Production Architecture</span>
            </div>
            <div className="flex items-center justify-center gap-2">
              <Award className="h-4 w-4 text-accent-coral shrink-0" />
              <span className="font-semibold text-slate-800">Cryptographic Certificates</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
