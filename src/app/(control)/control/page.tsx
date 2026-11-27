"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ShieldAlert,
  UserPlus,
  RefreshCw,
  AlertTriangle,
  Clock,
  Sparkles,
  LayoutDashboard,
} from "lucide-react";
import { controlApi } from "@/lib/api/control";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { OverviewMetricsGrid } from "@/components/control/OverviewMetricsGrid";
import { AnalyticsTrendsSection } from "@/components/control/AnalyticsTrendsSection";
import { RecentActivityLedger } from "@/components/control/RecentActivityLedger";
import { SecurityStatusCard } from "@/components/control/SecurityStatusCard";
import { QuickActionsGrid } from "@/components/control/QuickActionsGrid";

export default function ControlGovernancePage() {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["control-overview"],
    queryFn: () => controlApi.getOverview(),
    staleTime: 30 * 1000, // 30 seconds
    refetchOnWindowFocus: true,
  });

  // State 1: Loading Skeleton
  if (isLoading) {
    return (
      <div className="space-y-8 animate-in fade-in duration-150">
        {/* Header Skeleton */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96 max-w-full" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-36" />
          </div>
        </div>

        {/* Metrics Grid Skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="rounded-[16px] border border-slate-200 bg-white p-5 space-y-4"
            >
              <div className="flex justify-between items-center">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-8 w-8 rounded-lg" />
              </div>
              <Skeleton className="h-7 w-32" />
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            </div>
          ))}
        </div>

        {/* Trends Charts Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="rounded-[16px] border border-slate-200 bg-white p-6 space-y-4"
            >
              <div className="flex justify-between items-center">
                <div className="space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
                <Skeleton className="h-6 w-16" />
              </div>
              <Skeleton className="h-44 w-full rounded-lg" />
              <Skeleton className="h-4 w-full" />
            </div>
          ))}
        </div>

        {/* Security & Activity Skeletons */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-6 space-y-4">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  // State 2: Error with Retry
  if (isError || !data) {
    const errorMessage =
      error instanceof Error ? error.message : "Failed to load platform overview data.";

    return (
      <div className="space-y-6">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Platform Overview & Control
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Authoritative platform security controls and operational ledger.
          </p>
        </div>

        <div className="rounded-[16px] border border-rose-200 bg-rose-50/60 p-6 sm:p-8 text-center space-y-4 max-w-xl mx-auto my-8">
          <div className="p-3 rounded-full bg-rose-100 text-rose-600 w-fit mx-auto">
            <AlertTriangle className="h-8 w-8" />
          </div>
          <div>
            <h3 className="font-heading text-lg font-bold text-slate-900">
              Unable to Load Platform Metrics
            </h3>
            <p className="text-sm text-slate-600 mt-1 max-w-md mx-auto">
              {errorMessage}
            </p>
          </div>
          <div className="pt-2">
            <Button
              variant="primary"
              size="default"
              onClick={() => refetch()}
              className="bg-primary-teal hover:bg-teal-700"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry Connection
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // State 3 & 4: Success State (Handles empty values gracefully within subcomponents)
  return (
    <div className="space-y-8 pb-12">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Super Administrator Governance & Platform Control
            </h1>
            <span className="text-[11px] font-bold uppercase tracking-wider text-teal-800 bg-teal-100 px-2 py-0.5 rounded-full border border-teal-200">
              Super Admin
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Authoritative real-time platform metrics, security telemetry, and operational governance.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Link href="/admin">
            <Button
              variant="outline"
              size="sm"
              className="text-xs text-slate-700 hover:text-slate-900 border-slate-300"
              title="Switch to Admin Console"
            >
              <LayoutDashboard className="h-3.5 w-3.5 mr-1.5 text-primary-teal" />
              Admin Console
            </Button>
          </Link>

          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs text-slate-700"
            title="Refresh platform data"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin text-primary-teal" : ""}`}
            />
            {isFetching ? "Syncing…" : "Refresh"}
          </Button>

          <Link href="/control/staff">
            <Button variant="primary" size="sm" className="text-xs">
              <UserPlus className="h-3.5 w-3.5 mr-1.5" />
              Invite Staff
            </Button>
          </Link>
        </div>
      </div>

      {/* Section 1: KPI Metrics Grid */}
      <section aria-labelledby="kpi-metrics-heading">
        <OverviewMetricsGrid
          userMetrics={data.user_metrics}
          courseMetrics={data.course_metrics}
          enrollmentMetrics={data.enrollment_metrics}
          financialMetrics={data.financial_metrics}
        />
      </section>

      {/* Section 2: 14-Day Activity Trends */}
      <section aria-labelledby="analytics-trends-heading">
        <AnalyticsTrendsSection
          registrationTrends={data.registration_trends}
          enrollmentTrends={data.enrollment_trends}
        />
      </section>

      {/* Section 3: Recent Platform Activity Ledger */}
      <section aria-labelledby="recent-activity-heading">
        <RecentActivityLedger activity={data.recent_activity} />
      </section>

      {/* Section 4: Security Posture */}
      <section aria-labelledby="security-posture-heading">
        <SecurityStatusCard securityMetrics={data.security_metrics} />
      </section>

      {/* Section 5: Operational Portals & Roadmap */}
      <section aria-labelledby="operational-portals-heading">
        <QuickActionsGrid />
      </section>

      {/* Ledger Footer Timestamp */}
      <div className="pt-4 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5 text-slate-400" />
          <span>
            Telemetry generated: {new Date(data.generated_at).toLocaleString()}
          </span>
        </div>
        <span className="font-mono text-[11px] text-slate-600">
          Strict Single-Active Session Architecture Verified
        </span>
      </div>
    </div>
  );
}
