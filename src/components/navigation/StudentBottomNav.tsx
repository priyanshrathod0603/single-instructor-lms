"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  FileCheck,
  MoreHorizontal,
  X,
  HelpCircle,
  Award,
  CreditCard,
  User as UserIcon,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const primaryDestinations = [
  { label: "Overview", href: "/app", icon: LayoutDashboard },
  { label: "Courses", href: "/app/courses", icon: BookOpen },
  { label: "Tasks", href: "/app/assignments", icon: FileCheck },
];

const secondaryDestinations = [
  {
    label: "Quizzes",
    href: "/app/quizzes",
    icon: HelpCircle,
    description: "Assessments & scores",
  },
  {
    label: "Certificates",
    href: "/app/certificates",
    icon: Award,
    description: "Verified credentials",
  },
  {
    label: "Orders & Invoices",
    href: "/app/orders",
    icon: CreditCard,
    description: "Purchases & receipts",
  },
  {
    label: "Profile Settings",
    href: "/app/profile",
    icon: UserIcon,
    description: "Account & security",
  },
];

export const StudentBottomNav: React.FC = () => {
  const pathname = usePathname();
  const [isMoreOpen, setIsMoreOpen] = useState(false);

  const isSecondaryActive = secondaryDestinations.some(
    (item) =>
      pathname === item.href ||
      (item.href !== "/app" && pathname.startsWith(item.href))
  );

  // Close sheet on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isMoreOpen) {
        setIsMoreOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMoreOpen]);

  // Close sheet on route change
  useEffect(() => {
    setIsMoreOpen(false);
  }, [pathname]);

  const handleClose = useCallback(() => {
    setIsMoreOpen(false);
  }, []);

  return (
    <>
      {/* Secondary Destinations Slide-up Drawer */}
      {isMoreOpen && (
        <div
          className="md:hidden fixed inset-0 z-50 flex flex-col justify-end bg-slate-900/60 backdrop-blur-xs transition-opacity"
          onClick={handleClose}
          role="presentation"
        >
          <div
            className="w-full rounded-t-2xl border-t border-slate-200 bg-white p-5 pb-8 shadow-2xl animate-in slide-in-from-bottom duration-200"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Additional Navigation Menu"
          >
            {/* Sheet Handle & Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
              <div className="flex items-center gap-2">
                <span className="font-heading text-base font-bold text-slate-900">
                  More Options
                </span>
                <span className="text-xs font-mono text-slate-400">
                  Student Portal
                </span>
              </div>
              <button
                type="button"
                onClick={handleClose}
                aria-label="Close navigation menu"
                className="flex h-9 w-9 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 min-h-[44px] min-w-[44px]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Links List */}
            <div className="space-y-1.5" role="menu">
              {secondaryDestinations.map((item) => {
                const Icon = item.icon;
                const isActive =
                  pathname === item.href ||
                  (item.href !== "/app" && pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={handleClose}
                    role="menuitem"
                    className={cn(
                      "flex items-center justify-between rounded-xl p-3 min-h-[48px] transition-colors",
                      isActive
                        ? "bg-primary-teal/10 text-primary-teal font-semibold"
                        : "text-slate-700 hover:bg-slate-50"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-lg shrink-0",
                          isActive
                            ? "bg-primary-teal text-white"
                            : "bg-slate-100 text-slate-600"
                        )}
                      >
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{item.label}</div>
                        <div className="text-xs font-normal text-slate-500">
                          {item.description}
                        </div>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" />
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Fixed Bottom Navigation Bar */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-200/80 bg-white/95 backdrop-blur-md pb-safe shadow-lg"
        aria-label="Mobile Bottom Navigation"
      >
        <div className="flex h-16 items-center justify-around px-2">
          {primaryDestinations.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href ||
              (item.href !== "/app" && pathname.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex flex-1 flex-col items-center justify-center py-1 min-h-[48px] min-w-[48px] transition-colors rounded-lg",
                  isActive
                    ? "text-primary-teal font-semibold"
                    : "text-slate-500 hover:text-slate-800"
                )}
              >
                <Icon
                  className={cn(
                    "h-5 w-5 mb-1 transition-transform",
                    isActive ? "text-primary-teal scale-110" : "text-slate-400"
                  )}
                />
                <span className="font-sans text-[11px] leading-tight">
                  {item.label}
                </span>
              </Link>
            );
          })}

          {/* 4th Action: "More" Menu Toggle Button */}
          <button
            type="button"
            onClick={() => setIsMoreOpen(!isMoreOpen)}
            aria-expanded={isMoreOpen}
            aria-haspopup="dialog"
            aria-label="Open more navigation options"
            className={cn(
              "flex flex-1 flex-col items-center justify-center py-1 min-h-[48px] min-w-[48px] transition-colors rounded-lg",
              isSecondaryActive || isMoreOpen
                ? "text-primary-teal font-semibold"
                : "text-slate-500 hover:text-slate-800"
            )}
          >
            <MoreHorizontal
              className={cn(
                "h-5 w-5 mb-1 transition-transform",
                isSecondaryActive || isMoreOpen
                  ? "text-primary-teal scale-110"
                  : "text-slate-400"
              )}
            />
            <span className="font-sans text-[11px] leading-tight">
              More
            </span>
          </button>
        </div>
      </nav>
    </>
  );
};
