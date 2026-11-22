import React from "react";
import Link from "next/link";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/Accordion";
import { Badge } from "@/components/ui/Badge";

interface FaqItem {
  id: string;
  question: string;
  answer: string;
}

const FAQS: FaqItem[] = [
  {
    id: "single-instructor-model",
    question: "How does this single-instructor platform differ from open course marketplaces?",
    answer:
      "Open marketplaces allow anyone to publish content, leading to fragmented standards, outdated practices, and no personal accountability. Here, every course, curriculum roadmap, and code repository is authored by one lead architect. This guarantees consistent, battle-tested mental models across every subject.",
  },
  {
    id: "assignment-feedback",
    question: "How do assignment evaluations and code reviews work?",
    answer:
      "Assignments are real-world architectural exercises rather than multiple-choice trivia. When you submit your repository or solution, it is evaluated against comprehensive rubric criteria covering architecture, edge cases, type safety, and test coverage.",
  },
  {
    id: "lifetime-access",
    question: "Do I get lifetime access to course revisions and updates?",
    answer:
      "Yes. Once enrolled in a course, you receive lifetime access to all lessons in that course as well as all future published revisions. When new industry standards or framework updates release, updated curriculum modules are provided at no extra charge.",
  },
  {
    id: "certificates",
    question: "How do cryptographic graduation certificates work?",
    answer:
      "Upon completing all required curriculum modules and passing assignments, the platform issues an immutable, cryptographically verifiable certificate with a unique public URL. You can verify and share this certificate on LinkedIn, resumes, and portfolios.",
  },
  {
    id: "single-session",
    question: "How does the single-active-session security invariant protect my account?",
    answer:
      "For student data security and account integrity, our platform strictly enforces at most one active concurrent session per user account. Logging in from a new browser or device automatically and gracefully revokes the prior active session.",
  },
  {
    id: "mobile-learning",
    question: "Can I access courses and track progress on mobile devices?",
    answer:
      "Yes. The entire platform is built with a mobile-first responsive architecture supporting all screen sizes from 320px smartphones to 4K displays. Touch targets, video players, and navigation controls are optimized for mobile touch interaction.",
  },
];

export const FaqSection: React.FC = () => {
  return (
    <section id="faq" className="border-t border-soft-peach/60 bg-warm-cream/40 py-16 sm:py-24">
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        <div className="text-center space-y-3 mb-12">
          <div className="flex justify-center">
            <Badge variant="mint" size="sm">
              Frequently Asked Questions
            </Badge>
          </div>
          <h2 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl text-balance">
            Everything You Need to Know
          </h2>
          <p className="mx-auto max-w-xl font-sans text-sm sm:text-base text-slate-700">
            Have questions about our single-instructor philosophy, curriculum, or enrollment? Here are the answers.
          </p>
        </div>

        <div className="rounded-2xl border border-soft-peach bg-white p-6 sm:p-8 shadow-card">
          <Accordion type="single" collapsible className="w-full">
            {FAQS.map((faq) => (
              <AccordionItem key={faq.id} value={faq.id}>
                <AccordionTrigger className="text-left font-heading text-base font-bold text-slate-900 hover:text-primary-teal">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="font-sans text-sm text-slate-700 leading-relaxed">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>

        <div className="mt-8 text-center text-xs sm:text-sm text-slate-500 font-sans">
          Still have questions?{" "}
          <Link href="/signup" className="font-semibold text-primary-teal hover:underline">
            Create an account
          </Link>{" "}
          to explore our free preview lessons.
        </div>
      </div>
    </section>
  );
};
