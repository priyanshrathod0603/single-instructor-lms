"use client";

import React from "react";
import {
  Users,
  BookMarked,
  GraduationCap,
  CreditCard,
  CheckCircle2,
  AlertCircle,
  FileCheck,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  UserMetrics,
  CourseMetrics,
  EnrollmentMetrics,
  FinancialMetrics,
} from "@/types/control";
import { formatCurrency } from "@/lib/utils";

interface OverviewMetricsGridProps {
  userMetrics: UserMetrics;
  courseMetrics: CourseMetrics;
  enrollmentMetrics: EnrollmentMetrics;
  financialMetrics: FinancialMetrics;
}

export const OverviewMetricsGrid: React.FC<OverviewMetricsGridProps> = ({
  userMetrics,
  courseMetrics,
  enrollmentMetrics,
  financialMetrics,
}) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
          Platform Overview & KPI Ledger
        </h2>
        <span className="text-xs font-medium text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">
          Real Database Sync
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        {/* Card 1: Verified Financial Performance */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Verified Revenue
              </span>
              <div className="p-2 rounded-lg bg-teal-50 text-primary-teal">
                <CreditCard className="h-5 w-5" />
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                {formatCurrency(financialMetrics.verified_revenue_paise)}
              </p>
              <p className="text-xs text-slate-600">
                Gross verified tuition fees
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-700">
            <div className="flex justify-between">
              <span>Net After Refunds:</span>
              <strong className="text-slate-900 font-semibold">
                {formatCurrency(financialMetrics.net_revenue_paise)}
              </strong>
            </div>
            <div className="flex justify-between">
              <span>Paid Orders:</span>
              <strong className="text-slate-900 font-semibold">
                {financialMetrics.successful_transactions}
              </strong>
            </div>
            {financialMetrics.refunded_amount_paise > 0 && (
              <div className="flex justify-between text-rose-600">
                <span>Refunded Amount:</span>
                <span className="font-semibold">
                  -{formatCurrency(financialMetrics.refunded_amount_paise)}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Card 2: User Persona Breakdown */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Student & User Roster
              </span>
              <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
                <Users className="h-5 w-5" />
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                {userMetrics.total_students}
              </p>
              <p className="text-xs text-slate-600">
                Registered student accounts
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-700">
            <div className="flex justify-between">
              <span>Active Accounts:</span>
              <span className="text-emerald-700 font-semibold inline-flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                {userMetrics.active_users}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Staff & TAs:</span>
              <strong className="text-slate-900 font-semibold">{userMetrics.total_staff}</strong>
            </div>
            <div className="flex justify-between">
              <span>Admins / Super:</span>
              <strong className="text-slate-900 font-semibold">
                {userMetrics.total_admins} / {userMetrics.total_super_admins}
              </strong>
            </div>
          </div>
        </div>

        {/* Card 3: Course Catalog Inventory */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Course Inventory
              </span>
              <div className="p-2 rounded-lg bg-purple-50 text-purple-600">
                <BookMarked className="h-5 w-5" />
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                {courseMetrics.total_courses}
              </p>
              <p className="text-xs text-slate-600">
                Total educational offerings
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-700">
            <div className="flex justify-between">
              <span>Published Live:</span>
              <span className="text-primary-teal font-semibold">
                {courseMetrics.published_courses}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Draft Revisions:</span>
              <span className="text-amber-700 font-semibold">
                {courseMetrics.draft_courses}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Archived:</span>
              <span className="text-slate-600 font-semibold">
                {courseMetrics.archived_courses}
              </span>
            </div>
          </div>
        </div>

        {/* Card 4: Enrollment Metrics */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col justify-between hover:shadow-md transition-shadow">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Course Enrollments
              </span>
              <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
                <GraduationCap className="h-5 w-5" />
              </div>
            </div>
            <div className="space-y-1">
              <p className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                {enrollmentMetrics.total_enrollments}
              </p>
              <p className="text-xs text-slate-600">
                Lifetime learning enrollments
              </p>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-700">
            <div className="flex justify-between">
              <span>Active Access:</span>
              <span className="text-emerald-700 font-semibold">
                {enrollmentMetrics.active_enrollments}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Revoked / Inactive:</span>
              <span className="text-slate-600 font-semibold">
                {enrollmentMetrics.total_enrollments - enrollmentMetrics.active_enrollments}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Access Invariant:</span>
              <span className="text-slate-600 font-semibold">Webhook-Verified</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
