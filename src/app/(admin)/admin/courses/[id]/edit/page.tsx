"use client";

import React, { useState, use } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookMarked,
  Layers,
  Settings,
  UploadCloud,
  ExternalLink,
  Loader2,
  Check,
  AlertCircle,
  GitFork,
  Plus,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { CurriculumBuilder } from "@/components/admin/CurriculumBuilder";
import { PublishChecklistModal } from "@/components/admin/PublishChecklistModal";

export default function CourseEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const courseId = resolvedParams.id;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<"curriculum" | "metadata">("curriculum");
  const [isChecklistOpen, setIsChecklistOpen] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // 1. Fetch Course Detail
  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ["course", courseId],
    queryFn: () => coursesApi.getCourseDetail(courseId),
  });

  // 2. Fetch Revision Tree
  const targetRevId = course?.live_revision_id || undefined;
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

  // Metadata form state
  const [title, setTitle] = useState("");
  const [headline, setHeadline] = useState("");
  const [description, setDescription] = useState("");
  const [priceInRupees, setPriceInRupees] = useState("");
  const [isFree, setIsFree] = useState(false);
  const [tagsInput, setTagsInput] = useState("");

  React.useEffect(() => {
    if (course) {
      setTitle(course.title);
      setHeadline(course.headline || "");
      setDescription(course.description || "");
      setPriceInRupees(String(course.price_inr / 100));
      setIsFree(course.is_free || false);
      setTagsInput(course.tags?.join(", ") || "");
    }
  }, [course]);

  const updateMetadataMutation = useMutation({
    mutationFn: () => {
      const tags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const pricePaise = isFree ? 0 : Math.round(parseFloat(priceInRupees || "0") * 100);

      return coursesApi.updateCourse(courseId, {
        title,
        headline,
        description,
        price_inr: pricePaise,
        is_free: isFree,
        tags,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["course", courseId] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    },
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
        <div className="rounded-[16px] border border-slate-200 bg-white p-6 sm:p-8 shadow-sm max-w-3xl space-y-6">
          {saveSuccess && (
            <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-3 text-sm text-teal-800 border border-teal-200">
              <Check className="h-4 w-4 text-teal-600" />
              <span>Course metadata saved successfully!</span>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateMetadataMutation.mutate();
            }}
            className="space-y-4"
          >
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Title
              </label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Headline
              </label>
              <Input value={headline} onChange={(e) => setHeadline(e.target.value)} />
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Description
              </label>
              <Textarea
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Price (INR ₹)
                </label>
                <Input
                  type="number"
                  disabled={isFree}
                  value={priceInRupees}
                  onChange={(e) => setPriceInRupees(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-3 pt-6">
                <input
                  type="checkbox"
                  id="metadata-is-free"
                  checked={isFree}
                  onChange={(e) => setIsFree(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-primary-teal focus:ring-primary-teal"
                />
                <label htmlFor="metadata-is-free" className="text-sm font-semibold text-slate-800">
                  Free Course
                </label>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Tags
              </label>
              <Input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} />
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <Button
                type="submit"
                variant="primary"
                size="default"
                isLoading={updateMetadataMutation.isPending}
              >
                <Check className="h-4 w-4 mr-2" />
                Save Settings
              </Button>
            </div>
          </form>
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
