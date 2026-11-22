"use client";

import React from "react";
import Link from "next/link";
import {
  ShieldCheck,
  ShieldAlert,
  Users,
  FileText,
  Lock,
  ArrowRight,
  CheckCircle2,
} from "lucide-react";
import { SecurityMetrics } from "@/types/control";

interface SecurityStatusCardProps {
  securityMetrics: SecurityMetrics;
}

export const SecurityStatusCard: React.FC<SecurityStatusCardProps> = ({
  securityMetrics,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
            Security & Governance Posture
          </h2>
          <p className="text-xs sm:text-sm text-slate-500">
            Immutable audit guarantees, RBAC enforcement, and active session integrity.
          </p>
        </div>
        <Link
          href="/control/permissions"
          className="text-xs font-semibold text-primary-teal hover:text-teal-700 flex items-center gap-1"
        >
          <span>Permissions Matrix</span>
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        {/* Metric 1: Total Audit Events */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Audit Events Recorded
            </span>
            <div className="p-2 rounded-lg bg-teal-50 text-primary-teal">
              <FileText className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-2">
            {securityMetrics.total_audit_events}
          </p>
          <p className="text-xs text-slate-500 mt-1">Append-only immutable record</p>
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center gap-1.5 text-xs text-slate-600">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            <span>Zero-deletion compliance</span>
          </div>
        </div>

        {/* Metric 2: Security-Sensitive Actions */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Security Actions
            </span>
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
              <ShieldAlert className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-2">
            {securityMetrics.security_events_count}
          </p>
          <p className="text-xs text-slate-500 mt-1">Auth, roles, & access changes</p>
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center gap-1.5 text-xs text-slate-600">
            <Lock className="h-3.5 w-3.5 text-amber-600" />
            <span>High-privilege oversight</span>
          </div>
        </div>

        {/* Metric 3: Active Staff & TAs */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Active Staff & TAs
            </span>
            <div className="p-2 rounded-lg bg-purple-50 text-purple-600">
              <Users className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-2">
            {securityMetrics.active_staff_count}
          </p>
          <p className="text-xs text-slate-500 mt-1">Teaching & grading personnel</p>
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center gap-1.5 text-xs text-slate-600">
            <CheckCircle2 className="h-3.5 w-3.5 text-purple-600" />
            <span>Least-privilege RBAC</span>
          </div>
        </div>

        {/* Metric 4: Security Invariant Model */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Session Invariant
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
          <p className="text-base font-extrabold text-slate-900 mt-2 truncate">
            {securityMetrics.security_model}
          </p>
          <p className="text-xs text-slate-500 mt-1">Strict single active session</p>
          <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center gap-1.5 text-xs text-slate-600">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
            <span>Atomic Postgres index enforced</span>
          </div>
        </div>
      </div>
    </div>
  );
};
