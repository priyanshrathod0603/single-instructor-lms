"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Sparkles } from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { CourseCard } from "@/components/courses/CourseCard";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";

export const FeaturedCoursesSection: React.FC = () => {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["featuredCourses"],
    queryFn: () => coursesApi.listCourses({ per_page: 3 }),
  });

  const courses = data?.items || [];

  return (
    <section id="courses" className="py-16 sm:py-24 bg-white border-t border-soft-peach/60">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-12">
          <div className="space-y-3">
            <Badge variant="mint" size="sm">
              Verified Curriculum
            </Badge>
            <h2 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl text-balance">
              Featured Masterclasses
            </h2>
            <p className="max-w-2xl font-sans text-sm sm:text-base text-slate-600">
              End-to-end courses built to bridge the gap between intermediate coder and principal systems architect.
            </p>
          </div>

          <Link href="/courses" className="shrink-0">
            <Button variant="outline" size="sm">
              Browse All Courses
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          </Link>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 sm:gap-8">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="flex flex-col rounded-xl border border-soft-peach bg-white p-4 space-y-4"
              >
                <Skeleton className="aspect-video w-full rounded-lg" />
                <Skeleton className="h-6 w-3/4 rounded" />
                <Skeleton className="h-4 w-full rounded" />
                <div className="pt-4 border-t border-slate-100 flex justify-between items-center">
                  <Skeleton className="h-6 w-20" />
                  <Skeleton className="h-9 w-24 rounded-lg" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {isError && (
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-6 text-center space-y-3">
            <ErrorAlert
              title="Failed to Load Featured Courses"
              message={
                error instanceof Error
                  ? error.message
                  : "Unable to retrieve course data from the server."
              }
            />
            <Button variant="primary" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}

        {/* Empty State (Zero Fake Data) */}
        {!isLoading && !isError && courses.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-warm-cream/40 p-8 sm:p-12 text-center max-w-2xl mx-auto space-y-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-mint/60 text-primary-teal mx-auto">
              <BookOpen className="h-7 w-7" />
            </div>
            <h3 className="font-heading text-xl font-bold text-slate-900">
              New Masterclasses In Preparation
            </h3>
            <p className="font-sans text-sm text-slate-600 leading-relaxed">
              Every course on this platform is personally designed, engineered, and evaluated
              by the lead architect. New curriculum revisions and course tracks will appear here once published.
            </p>
            <div className="pt-2 flex justify-center gap-3">
              <Link href="/courses">
                <Button variant="outline" size="sm">
                  View Course Catalog
                </Button>
              </Link>
            </div>
          </div>
        )}

        {/* Real Backend Data Grid */}
        {!isLoading && !isError && courses.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 sm:gap-8">
            {courses.slice(0, 3).map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
