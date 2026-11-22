"use client";

import React from "react";
import Link from "next/link";
import {
  Users,
  BookMarked,
  CreditCard,
  GraduationCap,
  Image,
  Key,
  FileText,
  UserPlus,
  ArrowRight,
  Shield,
  FileCode,
  Tag,
  BookOpen,
  Sparkles,
} from "lucide-react";

interface ActionItem {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  badge?: string;
  badgeColor?: string;
}

interface PlannedItem {
  title: string;
  description: string;
  phase: string;
  icon: React.ReactNode;
}

const ACTIVE_ACTIONS: ActionItem[] = [
  {
    title: "Manage Students",
    description: "Inspect registered students, view enrollment progress, and manage learner access.",
    href: "/admin/students",
    icon: <Users className="h-5 w-5" />,
    iconBg: "bg-blue-50",
    iconColor: "text-blue-600",
  },
  {
    title: "Staff & TA Onboarding",
    description: "Generate secure onboarding invitation tokens for teaching assistants and staff.",
    href: "/control/staff",
    icon: <UserPlus className="h-5 w-5" />,
    iconBg: "bg-teal-50",
    iconColor: "text-primary-teal",
  },
  {
    title: "Course Catalog",
    description: "Review course drafts, publish revisions, and inspect lesson curriculum structure.",
    href: "/admin/courses",
    icon: <BookMarked className="h-5 w-5" />,
    iconBg: "bg-purple-50",
    iconColor: "text-purple-600",
  },
  {
    title: "Orders & Financials",
    description: "Inspect verified payment transactions, payment gateway payloads, and issue refunds.",
    href: "/admin/orders",
    icon: <CreditCard className="h-5 w-5" />,
    iconBg: "bg-emerald-50",
    iconColor: "text-emerald-600",
  },
  {
    title: "Course Enrollments",
    description: "Inspect lifetime enrollment grants, status, and webhook-verified access tokens.",
    href: "/admin/enrollments",
    icon: <GraduationCap className="h-5 w-5" />,
    iconBg: "bg-amber-50",
    iconColor: "text-amber-600",
  },
  {
    title: "Media Library",
    description: "Upload and manage course thumbnails, promotional videos, and lesson attachments.",
    href: "/admin/media",
    icon: <Image className="h-5 w-5" />,
    iconBg: "bg-rose-50",
    iconColor: "text-rose-600",
  },
  {
    title: "Permissions Matrix",
    description: "Inspect canonical role-permission mappings across all 10 architecture domains.",
    href: "/control/permissions",
    icon: <Key className="h-5 w-5" />,
    iconBg: "bg-indigo-50",
    iconColor: "text-indigo-600",
  },
  {
    title: "Audit Trail Explorer",
    description: "Search append-only audit entries, inspect before/after diffs, and filter by actor.",
    href: "/control/audit",
    icon: <FileText className="h-5 w-5" />,
    iconBg: "bg-teal-50",
    iconColor: "text-teal-700",
  },
];

const PLANNED_MODULES: PlannedItem[] = [
  {
    title: "Secondary Admin Roster",
    description: "Multi-admin privilege delegation and secondary administrator account management.",
    phase: "Phase 3 Planned",
    icon: <Shield className="h-4 w-4 text-slate-400" />,
  },
  {
    title: "Blog & Content Hub",
    description: "Authoritative technical articles, public SEO guides, and instructor editorial posts.",
    phase: "Phase 4 Planned",
    icon: <BookOpen className="h-4 w-4 text-slate-400" />,
  },
  {
    title: "Course Notes & Downloads",
    description: "Downloadable PDF summaries, reference cheatsheets, and student source archives.",
    phase: "Phase 5 Planned",
    icon: <FileCode className="h-4 w-4 text-slate-400" />,
  },
  {
    title: "Promotions & Discounts",
    description: "Campaign discount coupons, early-bird vouchers, and localized pricing tiers.",
    phase: "Phase 5 Planned",
    icon: <Tag className="h-4 w-4 text-slate-400" />,
  },
];

export const QuickActionsGrid: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Active Actions */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-heading text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
              Operational Management Portals
            </h2>
            <p className="text-xs sm:text-sm text-slate-500">
              Direct access to platform operations, student management, and security controls.
            </p>
          </div>
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-100">
            8 Live Modules
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {ACTIVE_ACTIONS.map((action) => (
            <Link
              key={action.href}
              href={action.href}
              className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-300 hover:shadow-md transition-all flex flex-col justify-between group"
            >
              <div>
                <div className={`p-2.5 rounded-[12px] ${action.iconBg} ${action.iconColor} w-fit mb-3`}>
                  {action.icon}
                </div>
                <h3 className="font-heading text-sm font-bold text-slate-900 group-hover:text-primary-teal transition-colors">
                  {action.title}
                </h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  {action.description}
                </p>
              </div>
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-primary-teal group-hover:translate-x-0.5 transition-transform">
                <span>Access Portal</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Planned Modules */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-500" />
            <h3 className="font-heading text-sm font-bold text-slate-700">
              Upcoming Architecture Modules
            </h3>
          </div>
          <span className="text-[11px] font-medium text-slate-600">
            Roadmap Sequence
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {PLANNED_MODULES.map((item) => (
            <div
              key={item.title}
              className="rounded-[12px] border border-dashed border-slate-200 bg-slate-50/70 p-3.5 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="p-1.5 rounded-lg bg-white border border-slate-200">
                    {item.icon}
                  </div>
                  <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                    {item.phase}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-slate-700">{item.title}</h4>
                <p className="text-[11px] text-slate-600 mt-1 line-clamp-2 leading-relaxed">
                  {item.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
