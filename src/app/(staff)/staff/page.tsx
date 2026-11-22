"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileText,
  Clock,
  ArrowRight,
  ShieldCheck,
  BookMarked,
  UserCheck,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export default function StaffDashboardPage() {
  const { data: coursesData, isLoading } = useQuery({
    queryKey: ["manage-courses"],
    queryFn: () => coursesApi.listManageCourses({ per_page: 10 }),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Teaching Assistant & Staff Workspace
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Review assignment submissions, evaluate student projects against rubrics, and provide feedback.
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Active Courses
            </span>
            <div className="p-2 rounded-lg bg-teal-50 text-primary-teal">
              <BookMarked className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2">
            {isLoading ? "..." : coursesData?.total ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-2">Under curriculum administration</p>
        </div>

        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Grading SLA
            </span>
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
              <Clock className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2">&lt; 48 Hours</p>
          <p className="text-xs text-slate-500 mt-2">Target feedback turnaround</p>
        </div>

        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Rubric Evaluation
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2">Standardized</p>
          <p className="text-xs text-slate-500 mt-2">Multi-criterion grading active</p>
        </div>
      </div>

      {/* Quick Launch Card */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-6 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div>
          <h2 className="font-heading text-lg font-bold text-slate-900">
            Student Submission Grading Queue
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Access student project files, evaluate code submissions, and record rubric scores.
          </p>
        </div>
        <Link href="/staff/grading">
          <Button variant="primary" size="default">
            <FileText className="h-4 w-4 mr-2" />
            Open Grading Queue
          </Button>
        </Link>
      </div>
    </div>
  );
}
