"use client";

import React from "react";
import Link from "next/link";
import { BookOpen, CheckSquare, Award, ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/hooks/useAuth";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { quizzesApi } from "@/lib/api/quizzes";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { EnrolledCourseCard } from "@/components/courses/EnrolledCourseCard";

export default function StudentDashboardPage() {
  const { user } = useAuth();

  const {
    data: enrollmentsData,
    isLoading: isEnrollmentsLoading,
    isError: isEnrollmentsError,
    error: enrollmentsError,
    refetch: refetchEnrollments,
  } = useQuery({
    queryKey: ["student-enrollments", { page: 1, per_page: 20 }],
    queryFn: () => enrollmentsApi.listOwnEnrollments({ page: 1, per_page: 20 }),
  });

  const {
    data: attemptsData,
    isLoading: isAttemptsLoading,
    refetch: refetchAttempts,
  } = useQuery({
    queryKey: ["student-quiz-attempts"],
    queryFn: () => quizzesApi.listOwnAttempts({ page: 1, size: 50 }),
  });

  const enrolledCount = enrollmentsData?.total ?? 0;
  const enrollments = enrollmentsData?.items ?? [];

  // Real quiz statistics
  const attempts = attemptsData?.items ?? [];
  const passedQuizzesCount = attempts.filter((a) => a.is_passed === true).length;

  const stats = [
    {
      label: "Enrolled Courses",
      value: isEnrollmentsLoading ? "..." : String(enrolledCount),
      icon: BookOpen,
      color: "text-primary-teal",
      bg: "bg-accent-mint/60",
    },
    {
      label: "Quizzes Passed",
      value: isAttemptsLoading ? "..." : String(passedQuizzesCount),
      icon: CheckSquare,
      color: "text-accent-coral",
      bg: "bg-accent-peach/60",
    },
    {
      label: "Quiz Attempts",
      value: isAttemptsLoading ? "..." : String(attempts.length),
      icon: Award,
      color: "text-amber-600",
      bg: "bg-amber-100",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header Greeting */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Welcome back, {user?.full_name?.split(" ")[0] || "Student"}! 👋
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Pick up where you left off or review your learning roadmap.
          </p>
        </div>
        <div>
          <Link href="/courses">
            <Button variant="primary" size="default">
              <BookOpen className="mr-2 h-4 w-4" />
              Browse Courses
            </Button>
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3 sm:gap-4 lg:gap-6">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="p-4 sm:p-5 flex items-center gap-3.5 min-w-0 shadow-xs">
              <div
                className={`flex h-11 w-11 sm:h-12 sm:w-12 items-center justify-center rounded-[12px] ${stat.bg} ${stat.color} shrink-0`}
              >
                <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-slate-500 truncate">
                  {stat.label}
                </p>
                <p className="font-heading text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-0.5">
                  {stat.value}
                </p>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Enrolled Courses Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-lg font-bold text-slate-900 sm:text-xl">
            My Courses
          </h2>
          {enrolledCount > 0 && (
            <Link
              href="/app/courses"
              className="font-sans text-xs font-semibold text-primary-teal hover:underline flex items-center gap-1"
            >
              View all ({enrolledCount})
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>

        {/* State Handling */}
        {isEnrollmentsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="p-6 space-y-4">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-2 w-full" />
                <Skeleton className="h-8 w-28 ml-auto" />
              </Card>
            ))}
          </div>
        ) : isEnrollmentsError ? (
          <ErrorAlert
            title="Unable to load courses"
            message={enrollmentsError?.message || "Could not retrieve your enrollments."}
            onRetry={() => {
              refetchEnrollments();
              refetchAttempts();
            }}
          />
        ) : enrollments.length === 0 ? (
          <EmptyState
            icon={<BookOpen className="h-8 w-8 text-primary-teal" />}
            title="No Active Courses Yet"
            description="You haven't enrolled in any courses yet. Explore our masterclasses to start learning."
            actionLabel="Explore Course Catalog"
            onAction={() => {
              window.location.href = "/courses";
            }}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {enrollments.map((enrollment) => (
              <EnrolledCourseCard
                key={enrollment.id}
                enrollment={enrollment}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
