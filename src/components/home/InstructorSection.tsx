import React from "react";
import Link from "next/link";
import {
  GraduationCap,
  Award,
  CheckCircle2,
  Code2,
  Terminal,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export const InstructorSection: React.FC = () => {
  return (
    <section id="about" className="border-t border-soft-peach/60 bg-white py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Instructor Visual / Badge column */}
          <div className="lg:col-span-5">
            <div className="relative mx-auto max-w-md overflow-hidden rounded-2xl border border-soft-peach bg-gradient-to-br from-primary-teal/10 via-accent-mint/30 to-warm-cream p-8 shadow-card text-center sm:text-left">
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-teal text-white shadow-elevated mx-auto sm:mx-0">
                <Terminal className="h-10 w-10" />
              </div>

              <div className="mt-6 space-y-2">
                <Badge variant="mint" size="sm">
                  Lead Architect & Instructor
                </Badge>
                <h3 className="font-heading text-2xl font-bold text-slate-900">
                  Engineering Lead & Systems Architect
                </h3>
                <p className="font-sans text-sm text-slate-700 leading-relaxed">
                  Principal software engineer with over a decade of production architecture experience in distributed backends, robust APIs, and web platforms.
                </p>
              </div>

              <div className="mt-6 pt-6 border-t border-soft-peach/60 space-y-3 font-sans text-xs text-slate-800 font-medium">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-primary-teal shrink-0" />
                  <span>100% of coursework personally designed & evaluated</span>
                </div>
                <div className="flex items-center gap-2">
                  <Code2 className="h-4 w-4 text-primary-teal shrink-0" />
                  <span>Production-grade real-world codebase walkthroughs</span>
                </div>
                <div className="flex items-center gap-2">
                  <Award className="h-4 w-4 text-accent-coral shrink-0" />
                  <span>Cryptographically signed graduation credentials</span>
                </div>
              </div>
            </div>
          </div>

          {/* Instructor Philosophy & Story column */}
          <div className="lg:col-span-7 space-y-6">
            <div className="space-y-3">
              <Badge variant="coral" size="sm">
                Single-Instructor Philosophy
              </Badge>
              <h2 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl text-balance">
                Zero Generic Filler. Just Pure Architectural Mastery.
              </h2>
            </div>

            <p className="font-sans text-base text-slate-700 leading-relaxed">
              Most online learning marketplaces suffer from the same problem: hundreds of fragmented courses taught with conflicting styles, outdated best practices, and zero personal accountability.
            </p>

            <p className="font-sans text-base text-slate-700 leading-relaxed">
              This platform is intentionally built around a single-instructor model. Every masterclass follows the exact same production-grade design principles, clean architecture patterns, and rigorous security standards. When you submit an assignment, your code is graded against uncompromising industry rubrics.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div className="rounded-xl border border-soft-peach/80 bg-warm-cream/50 p-4">
                <h4 className="font-heading text-base font-bold text-slate-900 mb-1">
                  Cohesive Engineering Mental Model
                </h4>
                <p className="font-sans text-xs text-slate-700 leading-normal">
                  Concepts build incrementally across courses without contradictory patterns or shallow toy projects.
                </p>
              </div>

              <div className="rounded-xl border border-soft-peach/80 bg-warm-cream/50 p-4">
                <h4 className="font-heading text-base font-bold text-slate-900 mb-1">
                  Direct Rubric Feedback
                </h4>
                <p className="font-sans text-xs text-slate-700 leading-normal">
                  Submit real code, receive actionable line-by-line feedback, and master how enterprise software is audited.
                </p>
              </div>
            </div>

            <div className="pt-4 flex flex-col sm:flex-row items-stretch sm:items-center gap-4">
              <Link href="/courses">
                <Button variant="primary" size="default">
                  View Published Curriculum
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Link href="/signup">
                <Button variant="outline" size="default">
                  Create Student Account
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
