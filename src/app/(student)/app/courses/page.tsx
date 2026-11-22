"use client";

import React, { useState } from "react";
import Link from "next/link";
import { BookOpen, Search, ArrowRight, ArrowLeft } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { EnrolledCourseCard } from "@/components/courses/EnrolledCourseCard";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export default function EnrolledCoursesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const {
    data: enrollmentsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["student-enrollments", { page, per_page: 20 }],
    queryFn: () => enrollmentsApi.listOwnEnrollments({ page, per_page: 20 }),
  });

  const allItems = enrollmentsData?.items ?? [];
  const filteredItems = search.trim()
    ? allItems.filter((e) =>
        (e.course_title || "")
          .toLowerCase()
          .includes(search.trim().toLowerCase())
      )
    : allItems;

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

      {/* Page Title & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            My Enrolled Courses
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Access your courses, track lesson completion, and download completion certificates.
          </p>
        </div>
        <div className="w-full sm:w-72">
          <Input
            type="search"
            placeholder="Filter courses..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* States */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="p-6 space-y-4">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-8 w-28 ml-auto" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorAlert
          title="Could not load your courses"
          message={error?.message || "Failed to retrieve enrolled courses."}
          onRetry={() => refetch()}
        />
      ) : allItems.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-8 w-8 text-primary-teal" />}
          title="No Enrolled Courses Found"
          description="You are not enrolled in any masterclasses yet. Browse the catalog to start learning."
          actionLabel="Browse Courses"
          onAction={() => {
            window.location.href = "/courses";
          }}
        />
      ) : filteredItems.length === 0 ? (
        <EmptyState
          icon={<Search className="h-8 w-8 text-slate-400" />}
          title="No Matching Courses"
          description={`No courses matched your query "${search}".`}
          actionLabel="Clear Filter"
          onAction={() => setSearch("")}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredItems.map((enrollment) => (
            <EnrolledCourseCard key={enrollment.id} enrollment={enrollment} />
          ))}
        </div>
      )}
    </div>
  );
}
