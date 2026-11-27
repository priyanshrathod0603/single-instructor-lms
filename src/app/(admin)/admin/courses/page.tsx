"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Edit2,
  ExternalLink,
  GitFork,
  Image as ImageIcon,
  Layers,
  Loader2,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";

import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from "@/components/ui/Modal";
import { resolveApiAssetUrl } from "@/lib/api/client";
import { coursesApi } from "@/lib/api/courses";
import { parseApiError } from "@/lib/api/errors";
import { formatInrFromPaise } from "@/lib/validation/courseForm";
import {
  CourseSummary,
  DEFAULT_COURSE_CATEGORIES,
  DIFFICULTY_LEVEL_LABELS,
  getDifficultyLabel,
} from "@/types/course";

function getStatusBadgeVariant(status: string): "success" | "warning" | "outline" {
  if (status === "PUBLISHED") return "success";
  if (status === "DRAFT") return "warning";
  return "outline";
}

function CourseThumbnailThumb({ url, title }: { url?: string | null; title: string }) {
  const [failed, setFailed] = useState(false);
  const src = resolveApiAssetUrl(url);

  if (!src || failed) {
    return (
      <div className="flex h-12 w-20 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-brand-cream/70 text-brand-teal/60">
        <ImageIcon className="h-5 w-5" />
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={`${title} thumbnail`}
      onError={() => setFailed(true)}
      className="h-12 w-20 shrink-0 rounded-xl border border-slate-200 object-cover bg-slate-100"
    />
  );
}

function CoursePricingCell({ course }: { course: CourseSummary }) {
  if (course.is_free) {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
        Free
      </span>
    );
  }

  const hasDiscount =
    course.compare_at_price_inr != null && course.compare_at_price_inr > course.price_inr;

  return (
    <div className="space-y-0.5">
      <div className="font-semibold text-slate-900">
        {formatInrFromPaise(course.price_inr)}
      </div>
      {hasDiscount && course.compare_at_price_inr != null && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-slate-400 line-through">
            {formatInrFromPaise(course.compare_at_price_inr)}
          </span>
          {course.discount_percentage != null && (
            <span className="rounded bg-brand-peach px-1.5 py-0.5 text-[10px] font-bold text-rose-700">
              -{course.discount_percentage}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminCoursesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState("");
  const [page, setPage] = useState(1);
  const [archiveTarget, setArchiveTarget] = useState<CourseSummary | null>(null);

  const { data: metadataOptions } = useQuery({
    queryKey: ["course-metadata-options"],
    queryFn: () => coursesApi.getMetadataOptions(),
    staleTime: 60_000,
    retry: false,
  });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: [
      "manage-courses",
      search,
      statusFilter,
      categoryFilter,
      difficultyFilter,
      page,
    ],
    queryFn: () =>
      coursesApi.listManageCourses({
        search: search || undefined,
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        difficulty_level: difficultyFilter || undefined,
        page,
        per_page: 20,
      }),
  });

  const forkRevisionMutation = useMutation({
    mutationFn: (courseId: string) => coursesApi.createRevision(courseId),
    onSuccess: (revision) => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
      toast.success("New draft revision created.");
      window.location.href = `/admin/courses/${revision.course_id}/edit`;
    },
    onError: (err) => {
      toast.error(parseApiError(err).message || "Could not fork draft revision.");
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (courseId: string) => coursesApi.archiveCourse(courseId),
    onSuccess: (archived) => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
      toast.success(`Archived "${archived.title}".`);
      setArchiveTarget(null);
    },
    onError: (err) => {
      toast.error(parseApiError(err).message || "Failed to archive course.");
    },
  });

  const categoryChoices = useMemo(() => {
    return metadataOptions?.categories?.length
      ? metadataOptions.categories
      : [...DEFAULT_COURSE_CATEGORIES];
  }, [metadataOptions?.categories]);

  const difficultyChoices = useMemo(() => {
    return metadataOptions?.difficulty_levels?.length
      ? metadataOptions.difficulty_levels
      : Object.entries(DIFFICULTY_LEVEL_LABELS).map(([value, label]) => ({
          value,
          label,
        }));
  }, [metadataOptions?.difficulty_levels]);

  const hasActiveFilters = Boolean(
    search.trim() || statusFilter || categoryFilter || difficultyFilter,
  );

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("");
    setCategoryFilter("");
    setDifficultyFilter("");
    setPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/admin"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Admin Dashboard
        </Link>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">
            Course Management Directory
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Author courses, edit rich metadata & pricing, manage revisions, and control catalog
            publishing.
          </p>
        </div>
        <Link href="/admin/courses/new">
          <Button variant="primary" size="default" className="min-h-[44px]">
            <Plus className="h-4 w-4 mr-2" />
            Create New Course
          </Button>
        </Link>
      </div>

      {/* Search and Metadata Filters */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
          <div className="relative md:col-span-5">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              aria-label="Search courses"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by title, slug, or category…"
              className="pl-10"
            />
          </div>

          <div className="md:col-span-2">
            <select
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
            >
              <option value="">All Statuses</option>
              <option value="DRAFT">Draft</option>
              <option value="PUBLISHED">Published</option>
              <option value="ARCHIVED">Archived</option>
            </select>
          </div>

          <div className="md:col-span-3">
            <select
              aria-label="Filter by category"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
            >
              <option value="">All Categories</option>
              {categoryChoices.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-2">
            <select
              aria-label="Filter by difficulty"
              value={difficultyFilter}
              onChange={(e) => {
                setDifficultyFilter(e.target.value);
                setPage(1);
              }}
              className="min-h-[44px] w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
            >
              <option value="">All Levels</option>
              {difficultyChoices.map((diff) => (
                <option key={diff.value} value={diff.value}>
                  {diff.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {hasActiveFilters && (
          <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
            <span>Showing filtered results</span>
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1 font-semibold text-brand-teal hover:underline"
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          </div>
        )}
      </div>

      {/* Directory States: Error / Loading / Empty / Data */}
      {isError ? (
        <ErrorAlert
          title="Could not load courses"
          message={parseApiError(error).message}
          requestId={parseApiError(error).requestId}
          onRetry={() => refetch()}
        />
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="flex h-64 flex-col items-center justify-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
              <p className="text-sm text-slate-500">Loading course directory…</p>
            </div>
          ) : !data?.items?.length ? (
            <div className="p-12 text-center text-slate-500 space-y-4">
              <BookMarked className="h-10 w-10 text-brand-teal/50 mx-auto" />
              <div className="space-y-1">
                <h3 className="font-heading font-bold text-base text-slate-900">
                  {hasActiveFilters ? "No matching courses found" : "No Courses Created Yet"}
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  {hasActiveFilters
                    ? "Try adjusting your search term or filter selections."
                    : "Get started by creating your first course with metadata, thumbnail, and INR pricing."}
                </p>
              </div>
              {hasActiveFilters ? (
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  Reset Filters
                </Button>
              ) : (
                <Link href="/admin/courses/new">
                  <Button variant="primary" size="sm">
                    <Plus className="h-4 w-4 mr-1.5" />
                    Create Your First Course
                  </Button>
                </Link>
              )}
            </div>
          ) : (
            <>
              {/* Desktop Table View */}
              <div className="hidden lg:block overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600">
                  <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                    <tr>
                      <th scope="col" className="px-5 py-3.5">Course</th>
                      <th scope="col" className="px-4 py-3.5">Category & Level</th>
                      <th scope="col" className="px-4 py-3.5">Price</th>
                      <th scope="col" className="px-4 py-3.5">Status</th>
                      <th scope="col" className="px-4 py-3.5">Last Updated</th>
                      <th scope="col" className="px-5 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.items.map((course) => (
                      <tr key={course.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3.5 min-w-0">
                            <CourseThumbnailThumb
                              url={course.thumbnail_url}
                              title={course.title}
                            />
                            <div className="min-w-0">
                              <Link
                                href={`/admin/courses/${course.id}/edit?tab=metadata`}
                                className="font-semibold text-slate-900 hover:text-brand-teal hover:underline line-clamp-1"
                              >
                                {course.title}
                              </Link>
                              <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-[240px]">
                                /{course.slug}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="text-xs font-semibold text-slate-800">
                            {course.category || "General"}
                          </div>
                          <div className="mt-0.5 text-xs text-slate-500">
                            {getDifficultyLabel(course.difficulty_level)} · {course.language || "English"}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <CoursePricingCell course={course} />
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant={getStatusBadgeVariant(course.status)}>
                            {course.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-4 text-xs text-slate-500 whitespace-nowrap">
                          {new Date(course.updated_at).toLocaleDateString("en-IN", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className="inline-flex items-center justify-end gap-1.5">
                            <Link href={`/admin/courses/${course.id}/edit?tab=metadata`}>
                              <Button variant="outline" size="sm" className="min-h-[36px]">
                                <Edit2 className="h-3.5 w-3.5 mr-1.5" />
                                Edit Course
                              </Button>
                            </Link>

                            <Link href={`/admin/courses/${course.id}/edit`}>
                              <Button variant="ghost" size="sm" className="min-h-[36px]">
                                <Layers className="h-3.5 w-3.5 mr-1.5" />
                                {course.status === "DRAFT" ? "Continue Editing" : "Curriculum"}
                              </Button>
                            </Link>

                            {course.status === "PUBLISHED" && (
                              <Link
                                href={`/courses/${course.slug}`}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <Button variant="ghost" size="sm" className="min-h-[36px]">
                                  <ExternalLink className="h-3.5 w-3.5 mr-1" />
                                  View
                                </Button>
                              </Link>
                            )}

                            {course.status === "PUBLISHED" && !course.draft_revision_id && (
                              <Button
                                variant="ghost"
                                size="sm"
                                isLoading={forkRevisionMutation.isPending}
                                onClick={() => forkRevisionMutation.mutate(course.id)}
                                title="Spawn new working draft revision"
                              >
                                <GitFork className="h-3.5 w-3.5 mr-1" />
                                Fork Draft
                              </Button>
                            )}

                            {course.status !== "ARCHIVED" && (
                              <button
                                type="button"
                                onClick={() => setArchiveTarget(course)}
                                className="text-slate-400 hover:text-rose-600 p-2 rounded-lg transition-colors inline-flex items-center justify-center min-h-[36px] min-w-[36px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                                title="Archive Course"
                                aria-label={`Archive ${course.title}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile / Tablet Responsive Cards */}
              <div className="divide-y divide-slate-100 lg:hidden">
                {data.items.map((course) => (
                  <div key={course.id} className="p-4 space-y-3">
                    <div className="flex items-start gap-3">
                      <CourseThumbnailThumb url={course.thumbnail_url} title={course.title} />
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-start justify-between gap-2">
                          <Link
                            href={`/admin/courses/${course.id}/edit?tab=metadata`}
                            className="font-semibold text-slate-900 hover:text-brand-teal break-words"
                          >
                            {course.title}
                          </Link>
                          <Badge variant={getStatusBadgeVariant(course.status)}>
                            {course.status}
                          </Badge>
                        </div>
                        <p className="font-mono text-xs text-slate-400 truncate">/{course.slug}</p>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
                          <span className="font-medium">{course.category || "General"}</span>
                          <span>{getDifficultyLabel(course.difficulty_level)}</span>
                          <span>{course.language || "English"}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                      <CoursePricingCell course={course} />
                      <span className="text-xs text-slate-500">
                        Updated{" "}
                        {new Date(course.updated_at).toLocaleDateString("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <Link
                        href={`/admin/courses/${course.id}/edit?tab=metadata`}
                        className="flex-1"
                      >
                        <Button variant="outline" size="sm" className="w-full min-h-[40px]">
                          <Edit2 className="h-3.5 w-3.5 mr-1.5" />
                          Edit Course
                        </Button>
                      </Link>
                      <Link href={`/admin/courses/${course.id}/edit`} className="flex-1">
                        <Button variant="ghost" size="sm" className="w-full min-h-[40px]">
                          <Layers className="h-3.5 w-3.5 mr-1.5" />
                          {course.status === "DRAFT" ? "Continue Editing" : "Curriculum"}
                        </Button>
                      </Link>
                      {course.status === "PUBLISHED" && (
                        <Link
                          href={`/courses/${course.slug}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <Button variant="ghost" size="sm" className="min-h-[40px]">
                            <ExternalLink className="h-3.5 w-3.5" />
                            <span className="sr-only">View Course</span>
                          </Button>
                        </Link>
                      )}
                      {course.status !== "ARCHIVED" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setArchiveTarget(course)}
                          aria-label={`Archive ${course.title}`}
                          className="min-h-[40px] text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination Footer */}
              {data.total_pages > 1 && (
                <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between text-xs text-slate-600">
                  <span>
                    Page <strong>{data.page}</strong> of <strong>{data.total_pages}</strong> (
                    {data.total} total)
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={data.page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="min-h-[36px]"
                    >
                      <ChevronLeft className="h-4 w-4 mr-1" />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={data.page >= data.total_pages}
                      onClick={() => setPage((p) => p + 1)}
                      className="min-h-[36px]"
                    >
                      Next
                      <ChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Archive Confirmation Modal */}
      <Modal
        open={Boolean(archiveTarget)}
        onOpenChange={(open) => {
          if (!open && !archiveMutation.isPending) {
            setArchiveTarget(null);
          }
        }}
      >
        <ModalContent>
          <ModalHeader>
            <ModalTitle>Archive Course</ModalTitle>
            <ModalDescription>
              Archived courses are removed from new public enrollments while preserving existing
              student history.
            </ModalDescription>
          </ModalHeader>
          <p className="py-2 text-sm text-slate-700">
            Are you sure you want to archive{" "}
            <strong className="text-slate-900">{archiveTarget?.title}</strong>?
          </p>
          <ModalFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setArchiveTarget(null)}
              disabled={archiveMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              isLoading={archiveMutation.isPending}
              onClick={() => {
                if (archiveTarget) {
                  archiveMutation.mutate(archiveTarget.id);
                }
              }}
            >
              Archive Course
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
