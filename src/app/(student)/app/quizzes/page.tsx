"use client";

import React from "react";
import Link from "next/link";
import { HelpCircle, CheckCircle, XCircle, Clock, ArrowRight, ArrowLeft, Award, BookOpen } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { quizzesApi } from "@/lib/api/quizzes";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export default function StudentQuizHistoryPage() {
  const {
    data: attemptsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["student-quiz-attempts"],
    queryFn: () => quizzesApi.listOwnAttempts({ page: 1, size: 50 }),
  });

  const attempts = attemptsData?.items ?? [];

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
            Quiz Assessments & Results
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Review your interactive quiz attempt history, automated scores, and passing records.
          </p>
        </div>
      </div>

      {/* Discovery vs Attempt History Informational Card */}
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-4">
        <span>
          <strong>How assessments work:</strong> Quizzes are integrated into each course lesson. To take an unattempted quiz, launch your enrolled course curriculum.
        </span>
        <Link
          href="/app/courses"
          className="text-primary-teal font-semibold hover:underline shrink-0 flex items-center gap-1"
        >
          <BookOpen className="h-3.5 w-3.5" />
          <span>Go to Courses</span>
        </Link>
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
          title="Could not load quiz history"
          message={error?.message || "Failed to retrieve quiz attempts."}
          onRetry={() => refetch()}
        />
      ) : attempts.length === 0 ? (
        <EmptyState
          icon={<HelpCircle className="h-8 w-8 text-primary-teal" />}
          title="No Quiz Attempts Recorded"
          description="You haven't attempted any curriculum quizzes yet. Complete course modules to take timed knowledge checks."
          actionLabel="View My Courses"
          onAction={() => {
            window.location.href = "/app/courses";
          }}
        />
      ) : (
        <div className="divide-y divide-slate-200 rounded-[12px] border border-slate-200 bg-white shadow-card overflow-hidden">
          {attempts.map((attempt) => {
            const isPassed = attempt.is_passed === true;

            return (
              <div
                key={attempt.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-5 gap-4 hover:bg-slate-50/50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-full shrink-0 ${
                      isPassed
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-rose-100 text-rose-700"
                    }`}
                  >
                    {isPassed ? (
                      <CheckCircle className="h-5 w-5" />
                    ) : (
                      <XCircle className="h-5 w-5" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-heading text-base font-bold text-slate-900">
                        Quiz Attempt #{attempt.attempt_no}
                      </h3>
                      <Badge
                        variant={isPassed ? "mint" : "error"}
                        size="sm"
                      >
                        {isPassed ? "PASSED" : "FAILED"}
                      </Badge>
                      <span className="font-mono text-xs text-slate-400">
                        ({attempt.status})
                      </span>
                    </div>

                    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-slate-500">
                      <span>Score: {attempt.score ?? 0}%</span>
                      <span>Passing Threshold: {attempt.pass_percentage}%</span>
                      <span>
                        Date: {new Date(attempt.started_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="shrink-0 flex items-center gap-2">
                  <Link href={`/app/quizzes/${attempt.quiz_id}?attempt_id=${attempt.id}`}>
                    <Button variant="outline" size="sm" className="min-h-[36px] text-xs">
                      Review Breakdown
                      <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                    </Button>
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
