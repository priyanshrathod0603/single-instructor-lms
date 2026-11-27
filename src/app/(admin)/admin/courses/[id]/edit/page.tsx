"use client";

import React, { Suspense, useState, use, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookMarked,
  Layers,
  Settings,
  UploadCloud,
  ExternalLink,
  Loader2,
  AlertCircle,
  GitFork,
  Plus,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { CurriculumBuilder } from "@/components/admin/CurriculumBuilder";
import { PublishChecklistModal } from "@/components/admin/PublishChecklistModal";
import { CourseMetadataForm } from "@/components/admin/course-form";

function CourseEditorContent({ courseId }: { courseId: string }) {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") === "metadata" ? "metadata" : "curriculum";

  const [activeTab, setActiveTab] = useState<"curriculum" | "metadata">(requestedTab);
  const [isChecklistOpen, setIsChecklistOpen] = useState(false);

  useEffect(() => {
    setActiveTab(requestedTab);
  }, [requestedTab]);

  // 1. Fetch Course Detail
  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ["course", courseId],
    queryFn: () => coursesApi.getCourseDetail(courseId),
  });

  // 2. Fetch Revision Tree (prioritize active draft revision, then latest or live)
  const targetRevId =
    course?.draft_revision_id ||
    course?.latest_revision_id ||
    course?.live_revision_id ||
    undefined;
  const { data: revision, isLoading: revisionLoading } = useQuery({
    queryKey: ["course-revision", courseId, targetRevId],
    queryFn: async () => {
      if (targetRevId) {
        return coursesApi.getRevision(courseId, targetRevId);
      }
      return null;
    },
    enabled: !!courseId && !!targetRevId,
  });

  const forkDraftMutation = useMutation({
    mutationFn: () => coursesApi.createRevision(courseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course", courseId] });
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
    },
  });

  if (courseLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
      </div>
    );
  }

  if (!course) {
    return (
      <div className="rounded-[16px] bg-rose-50 p-8 text-center text-rose-800">
        Course not found or insufficient privileges to view course curriculum.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <Link href="/admin/courses" className="hover:text-slate-800 flex items-center gap-1">
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Courses</span>
            </Link>
            <span>/</span>
            <span className="text-slate-700 font-medium truncate max-w-xs">{course.title}</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-bold text-slate-900 truncate">
              {course.title}
            </h1>
            <Badge variant={course.status === "PUBLISHED" ? "success" : "outline"}>
              {course.status}
            </Badge>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-3">
          {course.status === "PUBLISHED" && (
            <Button
              variant="outline"
              size="sm"
              isLoading={forkDraftMutation.isPending}
              onClick={() => forkDraftMutation.mutate()}
            >
              <GitFork className="h-4 w-4 mr-1.5" />
              Fork New Draft
            </Button>
          )}

          {targetRevId && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsChecklistOpen(true)}
            >
              <UploadCloud className="h-4 w-4 mr-1.5" />
              Pre-Flight & Publish
            </Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-6">
        <button
          onClick={() => setActiveTab("curriculum")}
          className={`flex items-center gap-2 py-3 text-sm font-semibold border-b-2 transition-colors ${
            activeTab === "curriculum"
              ? "border-primary-teal text-primary-teal"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <Layers className="h-4 w-4" />
          <span>Curriculum Canvas</span>
        </button>

        <button
          onClick={() => setActiveTab("metadata")}
          className={`flex items-center gap-2 py-3 text-sm font-semibold border-b-2 transition-colors ${
            activeTab === "metadata"
              ? "border-primary-teal text-primary-teal"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          <Settings className="h-4 w-4" />
          <span>Course Settings & Pricing</span>
        </button>
      </div>

      {/* Tab 1: Curriculum Canvas */}
      {activeTab === "curriculum" && (
        <div>
          {revisionLoading ? (
            <div className="flex h-64 items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
            </div>
          ) : revision ? (
            <CurriculumBuilder courseId={courseId} revision={revision} />
          ) : (
            <div className="rounded-[16px] border border-slate-200 bg-white p-8 text-center space-y-3">
              <BookMarked className="h-8 w-8 text-slate-400 mx-auto" />
              <h3 className="font-heading font-bold text-slate-800">No Active Working Revision</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Spawn an initial draft revision to begin composing curriculum modules.
              </p>
              <Button
                variant="primary"
                size="sm"
                isLoading={forkDraftMutation.isPending}
                onClick={() => forkDraftMutation.mutate()}
              >
                <Plus className="h-4 w-4 mr-1.5" />
                Create Working Revision
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Metadata & Pricing Settings */}
      {activeTab === "metadata" && (
        <div className="max-w-4xl">
          <CourseMetadataForm
            mode="edit"
            courseId={courseId}
            initialCourse={course}
            onSaved={(updatedCourse) => {
              queryClient.setQueryData(["course", courseId], updatedCourse);
              queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
              queryClient.invalidateQueries({ queryKey: ["courses"] });
            }}
          />
        </div>
      )}

      {/* Pre-Flight Checklist Modal */}
      {targetRevId && (
        <PublishChecklistModal
          isOpen={isChecklistOpen}
          onClose={() => setIsChecklistOpen(false)}
          courseId={courseId}
          revisionId={targetRevId}
        />
      )}
    </div>
  );
}

export default function CourseEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  return (
    <Suspense
      fallback={
        <div className="flex h-96 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
        </div>
      }
    >
      <CourseEditorContent courseId={resolvedParams.id} />
    </Suspense>
  );
}
