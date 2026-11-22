import React from "react";
import { BookOpen, Code2, CheckCircle2, Award } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

interface ProcessStep {
  number: string;
  title: string;
  description: string;
  icon: React.ElementType;
}

const STEPS: ProcessStep[] = [
  {
    number: "01",
    title: "Rigorous Mental Models",
    description: "Understand architectural principles first. Learn why systems are engineered a specific way, not just how to copy code.",
    icon: BookOpen,
  },
  {
    number: "02",
    title: "Production-Grade Labs",
    description: "Build full-fledged, battle-tested services with database transactions, test suites, and strict type safety.",
    icon: Code2,
  },
  {
    number: "03",
    title: "Direct Rubric Evaluation",
    description: "Submit your solution for comprehensive rubric grading and personalized instructor feedback on code quality.",
    icon: CheckCircle2,
  },
  {
    number: "04",
    title: "Cryptographic Credential",
    description: "Earn a verified, immutable certificate signed by the platform with a dedicated public verification URL.",
    icon: Award,
  },
];

export const LearningProcessSection: React.FC = () => {
  return (
    <section className="border-t border-soft-peach/60 bg-warm-cream/30 py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-16 space-y-3">
          <div className="flex justify-center">
            <Badge variant="coral" size="sm">
              Pedagogical Methodology
            </Badge>
          </div>
          <h2 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl text-balance">
            How You Master the Material
          </h2>
          <p className="font-sans text-sm sm:text-base text-slate-700">
            A structured four-phase trajectory built specifically for working engineers who want to reach staff and principal levels.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step) => {
            const Icon = step.icon;
            return (
              <div
                key={step.number}
                className="relative flex flex-col rounded-2xl border border-soft-peach bg-white p-6 shadow-subtle hover:shadow-card hover:-translate-y-1 transition-all duration-200"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-mint/60 text-primary-teal">
                    <Icon className="h-6 w-6" />
                  </div>
                  <span className="font-heading text-2xl font-black text-slate-300">
                    {step.number}
                  </span>
                </div>

                <h3 className="font-heading text-lg font-bold text-slate-900 mb-2">
                  {step.title}
                </h3>
                <p className="font-sans text-xs sm:text-sm text-slate-700 leading-relaxed">
                  {step.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
