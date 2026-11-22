"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookMarked,
  BookOpen,
  Search,
  RotateCcw,
  CheckCircle2,
  Clock,
  Archive,
  Users,
  Eye,
  Layers,
  FileQuestion,
  ClipboardList,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  ArrowRightLeft,
  Tag,
  Shield,
  HelpCircle,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import { CourseGovernanceItem } from "@/types/content";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
} from "@/components/ui/Modal";
import { formatCurrency } from "@/lib/utils";

const SORT_OPTIONS = [
  { label: "Newest First", sort_by: "created_at", sort_order: "desc" },
  { label: "Oldest First", sort_by: "created_at", sort_order: "asc" },
  { label: "Title (A-Z)", sort_by: "title", sort_order: "asc" },
  { label: "Title (Z-A)", sort_by: "title", sort_order: "desc" },
];

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "0m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0 && minutes > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (hours > 0) {
    return `${hours}h`;
  }
  return `${minutes}m`;
}

export default function CourseGovernancePage() {
  const queryClient = useQueryClient();

  // Filters & Pagination State
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sortIndex, setSortIndex] = useState(0);
  const [page, setPage] = useState(1);
  const perPage = 10;

  // Modals State
  const [inspectCourse, setInspectCourse] = useState<CourseGovernanceItem | null>(null);
  const [statusCourse, setStatusCourse] = useState<CourseGovernanceItem | null>(null);
  const [targetStatus, setTargetStatus] = useState<string>("PUBLISHED");
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);

  const currentSort = SORT_OPTIONS[sortIndex];

  // 1. Fetch Overview Metrics (Total dataset sample for aggregate stats)
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ["control-courses-metrics"],
    queryFn: () => controlApi.listGovernedCourses({ per_page: 100 }),
    staleTime: 30000,
  });

  // Calculate metrics
  const totalCourses = metricsData?.total ?? 0;
  const publishedCourses = metricsData?.items.filter((c) => c.status === "PUBLISHED").length ?? 0;
  const draftCourses = metricsData?.items.filter((c) => c.status === "DRAFT").length ?? 0;
  const archivedCourses = metricsData?.items.filter((c) => c.status === "ARCHIVED").length ?? 0;
  const totalEnrollments =
    metricsData?.items.reduce((sum, c) => sum + (c.enrolled_students_count || 0), 0) ?? 0;

  // 2. Fetch Paginated Governed Courses
  const {
    data: coursesData,
    isLoading: coursesLoading,
    isFetching,
    error: coursesError,
    refetch,
  } = useQuery({
    queryKey: [
      "control-courses",
      statusFilter,
      searchTerm,
      currentSort.sort_by,
      currentSort.sort_order,
      page,
      perPage,
    ],
    queryFn: () =>
      controlApi.listGovernedCourses({
        status: statusFilter === "ALL" ? undefined : statusFilter,
        search: searchTerm.trim() || undefined,
        sort_by: currentSort.sort_by,
        sort_order: currentSort.sort_order,
        page,
        per_page: perPage,
      }),
  });

  // 3. Status Mutation
  const statusMutation = useMutation({
    mutationFn: ({
      id,
      status,
      reason,
    }: {
      id: string;
      status: string;
      reason?: string;
    }) =>
      controlApi.updateCourseStatus(id, {
        status,
        reason: reason?.trim() || undefined,
      }),
    onSuccess: (updatedCourse) => {
      toast.success(`Course "${updatedCourse.title}" status updated to ${updatedCourse.status}.`);
      setStatusCourse(null);
      setStatusReason("");
      setStatusError(null);
      queryClient.invalidateQueries({ queryKey: ["control-courses"] });
      queryClient.invalidateQueries({ queryKey: ["control-courses-metrics"] });
      if (inspectCourse && inspectCourse.id === updatedCourse.id) {
        setInspectCourse(updatedCourse);
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to update course status.";
      setStatusError(msg);
      toast.error(msg);
    },
  });

  const handleOpenStatusModal = (course: CourseGovernanceItem) => {
    setStatusCourse(course);
    setTargetStatus(
      course.status === "PUBLISHED"
        ? "DRAFT"
        : course.status === "DRAFT"
        ? "PUBLISHED"
        : "DRAFT"
    );
    setStatusReason("");
    setStatusError(null);
  };

  const handleConfirmStatusChange = () => {
    if (!statusCourse) return;
    statusMutation.mutate({
      id: statusCourse.id,
      status: targetStatus,
      reason: statusReason,
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PUBLISHED":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
            Published
          </span>
        );
      case "DRAFT":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
            Draft
          </span>
        );
      case "ARCHIVED":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 border border-rose-200">
            Archived
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookMarked className="h-6 w-6 text-primary-teal" />
            <h1 className="font-heading text-2xl font-bold text-slate-900">
              Course Governance & Curriculum Overview
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Super Admin platform oversight of course portfolios, curriculum aggregation stats, and lifecycle governance.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              refetch();
              queryClient.invalidateQueries({ queryKey: ["control-courses-metrics"] });
            }}
            disabled={isFetching}
            className="flex items-center gap-2"
          >
            <RotateCcw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* KPI Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Total Courses */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Courses
            </span>
            <BookOpen className="h-4 w-4 text-blue-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-slate-900 font-mono">
                {totalCourses}
              </span>
            </div>
          )}
        </div>

        {/* Published Courses */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Published
            </span>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-emerald-600 font-mono">
                {publishedCourses}
              </span>
            </div>
          )}
        </div>

        {/* Draft Courses */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Drafts
            </span>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-amber-600 font-mono">
                {draftCourses}
              </span>
            </div>
          )}
        </div>

        {/* Archived Courses */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Archived
            </span>
            <Archive className="h-4 w-4 text-rose-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-rose-600 font-mono">
                {archivedCourses}
              </span>
            </div>
          )}
        </div>

        {/* Total Enrollments */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm sm:col-span-2 lg:col-span-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Enrollments
            </span>
            <Users className="h-4 w-4 text-purple-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-purple-600 font-mono">
                {totalEnrollments}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              type="text"
              placeholder="Search by course title, slug, or headline..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
              className="pl-9 bg-slate-50 border-slate-200 text-sm"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-teal"
            >
              <option value="ALL">All Statuses</option>
              <option value="PUBLISHED">Published</option>
              <option value="DRAFT">Draft</option>
              <option value="ARCHIVED">Archived</option>
            </select>
          </div>

          {/* Sort By */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Sort:</span>
            <select
              value={sortIndex}
              onChange={(e) => {
                setSortIndex(Number(e.target.value));
                setPage(1);
              }}
              className="text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-teal"
            >
              {SORT_OPTIONS.map((opt, i) => (
                <option key={opt.label} value={i}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters */}
          {(searchTerm || statusFilter !== "ALL" || sortIndex !== 0) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearchTerm("");
                setStatusFilter("ALL");
                setSortIndex(0);
                setPage(1);
              }}
              className="text-xs text-slate-500 hover:text-slate-800"
            >
              Reset
            </Button>
          )}
        </div>
      </div>

      {/* Courses Table */}
      <div className="bg-white rounded-[16px] border border-slate-200 shadow-sm overflow-hidden">
        {coursesLoading ? (
          <div className="p-12 flex flex-col items-center justify-center text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
            <p className="text-sm">Loading governed courses...</p>
          </div>
        ) : coursesError ? (
          <div className="p-12 text-center text-rose-500">
            <AlertCircle className="h-8 w-8 mx-auto mb-3" />
            <p className="text-sm font-medium">Failed to load courses</p>
            <p className="text-xs text-slate-500 mt-1">
              {(coursesError as any)?.message || "Please check network or permissions."}
            </p>
          </div>
        ) : !coursesData?.items || coursesData.items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <BookOpen className="h-8 w-8 mx-auto mb-3 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">No courses match your criteria</p>
            <p className="text-xs text-slate-400 mt-1">
              Try adjusting your search terms or status filters.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-3 px-4">Course Info</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Curriculum Overview</th>
                  <th className="py-3 px-4">Price</th>
                  <th className="py-3 px-4">Students</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {coursesData.items.map((course) => (
                  <tr key={course.id} className="hover:bg-slate-50/50 transition-colors">
                    {/* Course Info */}
                    <td className="py-3 px-4 max-w-xs">
                      <div className="font-semibold text-slate-900 line-clamp-1">
                        {course.title}
                      </div>
                      <div className="text-xs font-mono text-slate-400 mt-0.5 truncate">
                        /{course.slug}
                      </div>
                      {course.headline && (
                        <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                          {course.headline}
                        </div>
                      )}
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getStatusBadge(course.status)}
                    </td>

                    {/* Curriculum Overview */}
                    <td className="py-3 px-4">
                      <div className="flex flex-col gap-1 text-xs text-slate-600">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-800">
                            {course.total_sections}
                          </span>{" "}
                          sections ·{" "}
                          <span className="font-medium text-slate-800">
                            {course.total_lessons}
                          </span>{" "}
                          lessons
                        </div>
                        <div className="flex items-center gap-2 text-slate-500">
                          <Clock className="h-3 w-3" />
                          <span>{formatDuration(course.total_duration_seconds)}</span>
                          <span className="text-slate-300">|</span>
                          {course.has_quiz ? (
                            <span className="inline-flex items-center gap-0.5 text-emerald-600 font-medium">
                              <HelpCircle className="h-3 w-3" /> Quiz
                            </span>
                          ) : (
                            <span className="text-slate-400">No quiz</span>
                          )}
                          <span className="text-slate-300">|</span>
                          {course.has_assignment ? (
                            <span className="inline-flex items-center gap-0.5 text-blue-600 font-medium">
                              <ClipboardList className="h-3 w-3" /> Assignment
                            </span>
                          ) : (
                            <span className="text-slate-400">No assign</span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Price */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      {course.is_free ? (
                        <Badge variant="mint">Free</Badge>
                      ) : (
                        <span className="font-mono font-medium text-slate-900">
                          {formatCurrency(course.price_inr)}
                        </span>
                      )}
                    </td>

                    {/* Students */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 font-mono text-slate-700">
                        <Users className="h-3.5 w-3.5 text-slate-400" />
                        <span>{course.enrolled_students_count}</span>
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setInspectCourse(course)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="Inspect Curriculum & Details"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          Inspect
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleOpenStatusModal(course)}
                          className="h-8 px-2 text-xs flex items-center gap-1 border-slate-200 text-slate-700 hover:bg-slate-50"
                          title="Change Lifecycle Status"
                        >
                          <ArrowRightLeft className="h-3.5 w-3.5" />
                          Status
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {coursesData && coursesData.pages > 1 && (
          <div className="py-3 px-4 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing page <span className="font-medium text-slate-700">{page}</span> of{" "}
              <span className="font-medium text-slate-700">{coursesData.pages}</span> (
              {coursesData.total} total courses)
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-7 px-2 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(coursesData.pages, p + 1))}
                disabled={page >= coursesData.pages}
                className="h-7 px-2 text-xs"
              >
                Next <ChevronRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Inspect Course Modal */}
      <Modal open={!!inspectCourse} onOpenChange={(open) => !open && setInspectCourse(null)}>
        <ModalContent className="max-w-2xl">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              <BookOpen className="h-5 w-5 text-primary-teal" />
              Course Governance Inspection
            </ModalTitle>
            <ModalDescription>
              Detailed platform curriculum statistics and operational metadata.
            </ModalDescription>
          </ModalHeader>

          {inspectCourse && (
            <div className="space-y-4 py-2 text-sm text-slate-700">
              {/* Header Info */}
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-slate-900 text-base">
                      {inspectCourse.title}
                    </h3>
                    <p className="text-xs font-mono text-slate-500">slug: /{inspectCourse.slug}</p>
                  </div>
                  <div>{getStatusBadge(inspectCourse.status)}</div>
                </div>
                {inspectCourse.headline && (
                  <p className="text-xs text-slate-600">{inspectCourse.headline}</p>
                )}
              </div>

              {/* Curriculum Breakdown */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-xs text-slate-500 font-medium">Sections</span>
                  <div className="text-xl font-bold font-mono text-slate-900 mt-1">
                    {inspectCourse.total_sections}
                  </div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-xs text-slate-500 font-medium">Lessons</span>
                  <div className="text-xl font-bold font-mono text-slate-900 mt-1">
                    {inspectCourse.total_lessons}
                  </div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-xs text-slate-500 font-medium">Total Duration</span>
                  <div className="text-xl font-bold font-mono text-slate-900 mt-1">
                    {formatDuration(inspectCourse.total_duration_seconds)}
                  </div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-xs text-slate-500 font-medium">Enrolled Students</span>
                  <div className="text-xl font-bold font-mono text-purple-600 mt-1">
                    {inspectCourse.enrolled_students_count}
                  </div>
                </div>
              </div>

              {/* Additional Attributes */}
              <div className="space-y-2 border-t border-slate-100 pt-3">
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="text-slate-500">Pricing Model:</span>
                    <p className="font-semibold text-slate-800 mt-0.5">
                      {inspectCourse.is_free
                        ? "Free Course"
                        : formatCurrency(inspectCourse.price_inr)}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Live Revision Snapshot:</span>
                    <p className="font-mono text-slate-800 mt-0.5 truncate">
                      {inspectCourse.live_revision_id || "None (Draft Only)"}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Quizzes Included:</span>
                    <p className="font-semibold text-slate-800 mt-0.5">
                      {inspectCourse.has_quiz ? "Yes (Interactive Quizzes)" : "No"}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Assignments Included:</span>
                    <p className="font-semibold text-slate-800 mt-0.5">
                      {inspectCourse.has_assignment ? "Yes (Project Assignments)" : "No"}
                    </p>
                  </div>
                </div>

                {inspectCourse.description && (
                  <div className="mt-3">
                    <span className="text-xs text-slate-500">Description:</span>
                    <p className="text-xs text-slate-600 mt-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200 line-clamp-4">
                      {inspectCourse.description}
                    </p>
                  </div>
                )}

                {inspectCourse.tags && inspectCourse.tags.length > 0 && (
                  <div className="mt-3">
                    <span className="text-xs text-slate-500">Tags:</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {inspectCourse.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setInspectCourse(null)}
            >
              Close
            </Button>
            {inspectCourse && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const c = inspectCourse;
                  setInspectCourse(null);
                  handleOpenStatusModal(c);
                }}
                className="bg-primary-teal hover:bg-primary-teal/90 text-white"
              >
                Change Status
              </Button>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Status Change Modal */}
      <Modal open={!!statusCourse} onOpenChange={(open) => !open && setStatusCourse(null)}>
        <ModalContent className="max-w-md">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              <ArrowRightLeft className="h-5 w-5 text-primary-teal" />
              Change Course Lifecycle Status
            </ModalTitle>
            <ModalDescription>
              Update course visibility on the platform. All status changes are audited.
            </ModalDescription>
          </ModalHeader>

          {statusCourse && (
            <div className="space-y-4 py-2 text-sm">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500">Course Target:</span>
                <div className="font-semibold text-slate-900 mt-0.5">{statusCourse.title}</div>
                <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                  <span>Current:</span>
                  {getStatusBadge(statusCourse.status)}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  New Status
                </label>
                <select
                  value={targetStatus}
                  onChange={(e) => setTargetStatus(e.target.value)}
                  className="w-full text-sm bg-white border border-slate-300 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="DRAFT">DRAFT (Unpublished / Under Construction)</option>
                  <option value="PUBLISHED">PUBLISHED (Live for Student Enrollment)</option>
                  <option value="ARCHIVED">ARCHIVED (Retired from New Sales)</option>
                </select>
              </div>

              {targetStatus === "PUBLISHED" && (
                <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <strong>Publishing Note:</strong> A course must possess a valid, validated live revision snapshot before transitioning to PUBLISHED status.
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Reason / Justification (Audit Log)
                </label>
                <textarea
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  rows={2}
                  placeholder="Optional justification for this status change..."
                  className="w-full text-sm bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                />
              </div>

              {statusError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {statusError}
                </div>
              )}
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setStatusCourse(null);
                setStatusError(null);
              }}
              disabled={statusMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleConfirmStatusChange}
              disabled={statusMutation.isPending}
              className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-1.5"
            >
              {statusMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Confirm Change
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
