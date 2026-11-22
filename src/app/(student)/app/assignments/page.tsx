"use client";

import React, { useState } from "react";
import Link from "next/link";
import { CheckSquare, Clock, ArrowRight, ArrowLeft, Award, FileText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export default function StudentAssignmentsDirectoryPage() {
  const [filter, setFilter] = useState<"ALL" | "PENDING" | "SUBMITTED" | "GRADED">("ALL");

  const {
    data: enrollmentsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["student-enrollments", { page: 1, per_page: 50 }],
    queryFn: () => enrollmentsApi.listOwnEnrollments({ page: 1, per_page: 50 }),
  });

  const enrollments = enrollmentsData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/app"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Overview
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Assignments & Projects
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Review your course project briefs, submit work for evaluation, and track rubric feedback.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="p-6 space-y-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-32" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorAlert
          title="Could not load assignments"
          message={error?.message || "Failed to load enrolled course assignments."}
          onRetry={() => refetch()}
        />
      ) : enrollments.length === 0 ? (
        <EmptyState
          icon={<CheckSquare className="h-8 w-8 text-primary-teal" />}
          title="No Enrolled Courses"
          description="Enroll in a course to access project assignments and rubric-graded tasks."
          actionLabel="Browse Courses"
          onAction={() => {
            window.location.href = "/courses";
          }}
        />
      ) : (
        <div className="space-y-4">
          <div className="rounded-[12px] border border-slate-200 bg-white p-5 shadow-xs">
            <h2 className="font-heading text-base font-bold text-slate-900 mb-2">
              Course Projects by Enrolled Course
            </h2>
            <p className="text-xs sm:text-sm text-slate-600 mb-4 font-sans">
              Assignments are configured directly within your enrolled course curriculum modules. Select a course below to view syllabus projects:
            </p>

            <div className="divide-y divide-slate-100">
              {enrollments.map((enr) => (
                <div
                  key={enr.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between py-3.5 gap-2"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-peach/60 text-accent-coral shrink-0">
                      <FileText className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="font-heading text-sm font-bold text-slate-900">
                        {enr.course_title || "Course"}
                      </h3>
                      <p className="font-mono text-xs text-slate-400">
                        Enrolled {new Date(enr.granted_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  <Link href={`/app/courses/${enr.course_id}`}>
                    <Button variant="outline" size="sm" className="min-h-[32px] text-xs">
                      View Syllabus Projects
                      <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                    </Button>
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
