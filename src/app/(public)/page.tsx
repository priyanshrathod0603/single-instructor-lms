import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Award,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { HeroSection } from "@/components/home/HeroSection";
import { FeaturedCoursesSection } from "@/components/home/FeaturedCoursesSection";
import { InstructorSection } from "@/components/home/InstructorSection";
import { LearningProcessSection } from "@/components/home/LearningProcessSection";
import { FaqSection } from "@/components/home/FaqSection";

export const metadata = {
  title: "Single-Instructor LMS — Master High-Impact Engineering Skills",
  description:
    "Direct-to-student engineering masterclasses, production-grade architectures, and personal rubric evaluations taught by a principal software architect.",
};

export default function LandingPage() {
  return (
    <div className="flex flex-col">
      {/* Refined Hero Section with Animated Typewriter (FE-201 & Section 4) */}
      <HeroSection />

      {/* Featured Masterclasses Section (Connected to Real Backend API, Zero Fake Data) */}
      <FeaturedCoursesSection />

      {/* Feature Highlights Grid */}
      <section className="border-t border-soft-peach/60 bg-warm-cream/20 py-16 sm:py-24">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16 space-y-3">
            <Badge variant="coral" size="sm">
              The Single-Instructor Advantage
            </Badge>
            <h2 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl text-balance">
              Why Direct-to-Instructor Learning Wins
            </h2>
            <p className="font-sans text-sm sm:text-base text-slate-700">
              No bloated platforms, no third-party filler. Direct mentorship with
              an uncompromising bar for engineering excellence.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
            <Card className="p-6 sm:p-8 space-y-4 hover:shadow-card hover:-translate-y-1 transition-all duration-200">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-mint/60 text-primary-teal">
                <BookOpen className="h-6 w-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-slate-900">
                Rigorous Coursework
              </h3>
              <p className="font-sans text-sm text-slate-700 leading-relaxed">
                Step-by-step masterclasses built on battle-tested engineering
                standards and real production architectures.
              </p>
            </Card>

            <Card className="p-6 sm:p-8 space-y-4 hover:shadow-card hover:-translate-y-1 transition-all duration-200">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-peach/60 text-accent-coral">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-slate-900">
                Direct Grading & Feedback
              </h3>
              <p className="font-sans text-sm text-slate-700 leading-relaxed">
                Receive personalized rubric evaluations and detailed code comments
                from the teaching team on your submitted assignments.
              </p>
            </Card>

            <Card className="p-6 sm:p-8 space-y-4 hover:shadow-card hover:-translate-y-1 transition-all duration-200">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                <Award className="h-6 w-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-slate-900">
                Verified Credentials
              </h3>
              <p className="font-sans text-sm text-slate-700 leading-relaxed">
                Earn cryptographic, publicly verifiable graduation certificates to
                showcase on LinkedIn, resumes, and portfolios.
              </p>
            </Card>
          </div>
        </div>
      </section>

      {/* Instructor Profile Experience (FE-206) */}
      <InstructorSection />

      {/* Learning Process & Methodology */}
      <LearningProcessSection />

      {/* Accessible FAQ Section (FE-207) */}
      <FaqSection />

      {/* Final Direct CTA Banner */}
      <section className="bg-primary-teal bg-[#006B60] py-16 sm:py-20 text-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h2 className="font-heading text-3xl font-extrabold sm:text-4xl lg:text-5xl text-white text-balance">
            Ready to Accelerate Your Career?
          </h2>
          <p className="mx-auto max-w-xl font-sans text-base text-slate-100 leading-relaxed text-balance">
            Join ambitious software engineers learning directly with us. Get
            lifetime access to courses, structured rubrics, and community discussions.
          </p>
          <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/courses">
              <Button
                variant="accent"
                size="lg"
                className="w-full sm:w-auto shadow-elevated hover:shadow-card transition-all"
              >
                Explore All Courses
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </Link>
            <Link href="/signup">
              <Button
                variant="outline"
                size="lg"
                className="w-full sm:w-auto border-2 border-white text-white hover:bg-white/15 hover:border-white hover:text-white"
              >
                Create Student Account
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
