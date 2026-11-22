"use client";

import React, { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { CourseSummary } from "@/types/course";
import { CourseCard } from "@/components/courses/CourseCard";
import {
  CourseFilters,
  CourseFilterValues,
} from "@/components/courses/CourseFilters";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { Button } from "@/components/ui/Button";

function CourseCatalogContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Parse query params from URL
  const search = searchParams.get("search") || "";
  const tag = searchParams.get("tag") || "";
  const pageParam = parseInt(searchParams.get("page") || "1", 10);
  const page = isNaN(pageParam) || pageParam < 1 ? 1 : pageParam;
  const sortBy = (searchParams.get("sort") || "newest") as
    | "newest"
    | "price_asc"
    | "price_desc";

  const perPage = 12;

  // Fetch courses from authoritative backend API
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["courses", { search, tag, page, perPage }],
    queryFn: () =>
      coursesApi.listCourses({
        search: search || undefined,
        tag: tag || undefined,
        page,
        per_page: perPage,
      }),
  });

  const filterValues: CourseFilterValues = {
    search,
    tag,
    sortBy,
  };

  const updateFilters = React.useCallback(
    (newValues: CourseFilterValues) => {
      const params = new URLSearchParams();
      if (newValues.search) params.set("search", newValues.search);
      if (newValues.tag) params.set("tag", newValues.tag);
      if (newValues.sortBy && newValues.sortBy !== "newest") {
        params.set("sort", newValues.sortBy);
      }
      // Reset to page 1 on filter changes
      params.set("page", "1");
      router.push(`/courses?${params.toString()}`);
    },
    [router]
  );

  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(newPage));
    router.push(`/courses?${params.toString()}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Sort retrieved items based on user selection
  const sortedCourses = useMemo(() => {
    if (!data?.items) return [];
    const courses = [...data.items];

    if (sortBy === "price_asc") {
      courses.sort((a, b) => a.price_inr - b.price_inr);
    } else if (sortBy === "price_desc") {
      courses.sort((a, b) => b.price_inr - a.price_inr);
    } else {
      // Newest first (default)
      courses.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    }
    return courses;
  }, [data?.items, sortBy]);

  // Extract all distinct tags present in catalog
  const availableTags = useMemo(() => {
    const set = new Set<string>();
    data?.items?.forEach((c) => c.tags?.forEach((t) => set.add(t)));
    return Array.from(set).slice(0, 8);
  }, [data?.items]);

  const totalPages = data?.total_pages || 1;
  const totalItems = data?.total ?? sortedCourses.length;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
      {/* Header Banner */}
      <div className="mb-8 space-y-3 sm:mb-12">
        <h1 className="font-heading text-[clamp(1.75rem,2.8vw+0.75rem,2.75rem)] font-extrabold tracking-tight text-slate-900 leading-tight">
          Curriculum & Masterclasses
        </h1>
        <p className="max-w-3xl font-sans text-base text-slate-700 sm:text-lg leading-relaxed">
          Explore rigorous, production-grade courses authored and taught directly by
          the instructor. From foundational architectures to high-scale distributed systems.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div className="mb-8 rounded-xl border border-soft-peach bg-white/80 p-4 sm:p-6 shadow-card backdrop-blur-sm">
        <CourseFilters
          initialValues={filterValues}
          availableTags={availableTags.length > 0 ? availableTags : undefined}
          totalResults={isLoading ? undefined : totalItems}
          onFilterChange={updateFilters}
        />
      </div>

      {/* Loading Skeletons */}
      {isLoading && (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 sm:gap-8">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="flex flex-col rounded-xl border border-soft-peach/60 bg-white p-4 shadow-subtle space-y-4"
            >
              <Skeleton className="aspect-video w-full rounded-lg" />
              <div className="space-y-2">
                <Skeleton className="h-4 w-1/4 rounded" />
                <Skeleton className="h-6 w-3/4 rounded" />
                <Skeleton className="h-4 w-full rounded" />
              </div>
              <div className="pt-4 border-t border-slate-100 flex justify-between items-center">
                <Skeleton className="h-6 w-20 rounded" />
                <Skeleton className="h-9 w-24 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error View */}
      {isError && (
        <div className="my-8">
          <ErrorAlert
            title="Failed to Load Course Catalog"
            message={
              error instanceof Error
                ? error.message
                : "Unable to retrieve course catalog. Please check your network connection and try again."
            }
          />
          <div className="mt-4 flex justify-center">
            <Button variant="primary" onClick={() => refetch()}>
              Retry Loading Catalog
            </Button>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !isError && sortedCourses.length === 0 && (
        <div className="my-12">
          <EmptyState
            icon={<BookOpen className="h-8 w-8 text-primary-teal" />}
            title={
              search || tag
                ? "No matching courses found"
                : "No published courses yet"
            }
            description={
              search || tag
                ? `We couldn't find any courses matching your current filter criteria. Try clearing filters or searching for different keywords.`
                : "New masterclasses and curriculum modules are currently in preparation. Please check back soon or sign up for announcements."
            }
            actionLabel={search || tag ? "Clear All Filters" : "Return to Home"}
            onAction={
              search || tag
                ? () =>
                    updateFilters({
                      search: "",
                      tag: "",
                      sortBy: "newest",
                    })
                : () => router.push("/")
            }
          />
        </div>
      )}

      {/* Course Grid */}
      {!isLoading && !isError && sortedCourses.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 sm:gap-8">
            {sortedCourses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="mt-12 flex items-center justify-between border-t border-soft-peach pt-6">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1}
                aria-label="Previous page"
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Previous
              </Button>

              <div className="font-sans text-xs sm:text-sm text-slate-600">
                Page <span className="font-semibold text-slate-900">{page}</span>{" "}
                of{" "}
                <span className="font-semibold text-slate-900">{totalPages}</span>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages}
                aria-label="Next page"
              >
                Next
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function CoursesPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <Skeleton className="h-10 w-64 mb-4" />
          <Skeleton className="h-5 w-96 mb-8" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-video w-full rounded-xl" />
            ))}
          </div>
        </div>
      }
    >
      <CourseCatalogContent />
    </Suspense>
  );
}
