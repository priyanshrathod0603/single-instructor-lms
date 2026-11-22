import React from "react";
import Link from "next/link";
import { GraduationCap, ShieldCheck } from "lucide-react";

export const PublicFooter: React.FC = () => {
  return (
    <footer className="border-t border-soft-peach/80 bg-warm-cream/50">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-4">
          {/* Brand info */}
          <div className="space-y-4 md:col-span-1">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-primary-teal text-white shadow-sm">
                <GraduationCap className="h-5 w-5" />
              </div>
              <span className="font-heading text-lg font-bold tracking-tight text-slate-900">
                Instructor<span className="text-primary-teal">LMS</span>
              </span>
            </Link>
            <p className="font-sans text-xs sm:text-sm text-slate-600 leading-relaxed">
              Proprietary direct-to-student engineering masterclasses and architecture curriculum taught
              directly by the lead architect.
            </p>
          </div>

          {/* Curriculum Tracks */}
          <div className="space-y-3">
            <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-slate-900">
              Curriculum Tracks
            </h4>
            <ul className="space-y-2 font-sans text-xs sm:text-sm text-slate-600">
              <li>
                <Link href="/courses" className="hover:text-primary-teal transition-colors">
                  All Masterclasses
                </Link>
              </li>
              <li>
                <Link href="/courses?tag=Architecture" className="hover:text-primary-teal transition-colors">
                  System Architecture
                </Link>
              </li>
              <li>
                <Link href="/courses?tag=Security" className="hover:text-primary-teal transition-colors">
                  Enterprise API Security
                </Link>
              </li>
            </ul>
          </div>

          {/* Platform Access */}
          <div className="space-y-3">
            <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-slate-900">
              Student Access
            </h4>
            <ul className="space-y-2 font-sans text-xs sm:text-sm text-slate-600">
              <li>
                <Link href="/login" className="hover:text-primary-teal transition-colors">
                  Sign In to Account
                </Link>
              </li>
              <li>
                <Link href="/signup" className="hover:text-primary-teal transition-colors">
                  Create Student Account
                </Link>
              </li>
              <li>
                <Link href="/app" className="hover:text-primary-teal transition-colors">
                  Student Dashboard
                </Link>
              </li>
            </ul>
          </div>

          {/* About & Invariants */}
          <div className="space-y-3">
            <h4 className="font-heading text-xs font-bold uppercase tracking-wider text-slate-900">
              Platform & Governance
            </h4>
            <ul className="space-y-2 font-sans text-xs sm:text-sm text-slate-600">
              <li>
                <Link href="/#about" className="hover:text-primary-teal transition-colors">
                  Instructor Profile
                </Link>
              </li>
              <li>
                <Link href="/#faq" className="hover:text-primary-teal transition-colors">
                  Frequently Asked Questions
                </Link>
              </li>
              <li className="flex items-center gap-1.5 text-xs text-slate-500 pt-1">
                <ShieldCheck className="h-4 w-4 text-primary-teal" />
                <span>Single-Active-Session Protection</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 border-t border-soft-peach/60 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500 font-sans">
          <p>© {new Date().getFullYear()} Single-Instructor LMS. All rights reserved.</p>
          <p className="flex items-center gap-1 font-medium text-slate-600">
            Engineered for high performance, accessibility, and zero-trust security
          </p>
        </div>
      </div>
    </footer>
  );
};
