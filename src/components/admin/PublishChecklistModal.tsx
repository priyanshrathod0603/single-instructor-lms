"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  X,
  UploadCloud,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";

interface PublishChecklistModalProps {
  isOpen: boolean;
  onClose: () => void;
  courseId: string;
  revisionId: string;
  onSuccess?: () => void;
}

function getActionableHint(code: string): string | null {
  switch (code) {
    case "MEDIA_NOT_READY":
      return "Video is transcoding in the background. Wait a moment for processing to finish, or select a ready video from Media Library.";
    case "EMPTY_TITLE":
    case "EMPTY_SLUG":
    case "EMPTY_HEADLINE":
      return "Go to Course Details to fill in required metadata.";
    case "INVALID_PRICING":
      return "Configure a price in INR in Course Settings, or mark the course as Free.";
    case "NO_SECTIONS":
      return "Add at least one curriculum section in the Curriculum tab.";
    case "EMPTY_SECTION":
      return "Add at least one lesson to this section, or remove the empty section.";
    case "EMPTY_QUIZ":
    case "EMPTY_QUIZ_OPTIONS":
    case "NO_CORRECT_OPTION":
      return "Open Quiz Builder to add questions and designate correct answer options.";
    case "EMPTY_ASSIGNMENT":
      return "Add instructions and a grading rubric for this assignment.";
    default:
      return null;
  }
}

export const PublishChecklistModal: React.FC<PublishChecklistModalProps> = ({
  isOpen,
  onClose,
  courseId,
  revisionId,
  onSuccess,
}) => {
  const queryClient = useQueryClient();

  const { data: checklist, isLoading, error } = useQuery({
    queryKey: ["publish-checklist", courseId, revisionId],
    queryFn: () => coursesApi.getPublishChecklist(courseId, revisionId),
    enabled: isOpen && !!courseId && !!revisionId,
  });

  const publishMutation = useMutation({
    mutationFn: () => coursesApi.publishRevision(courseId, revisionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
      queryClient.invalidateQueries({ queryKey: ["course-revision", courseId] });
      queryClient.invalidateQueries({ queryKey: ["course", courseId] });
      if (onSuccess) onSuccess();
      onClose();
    },
  });

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="publish-checklist-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 sm:p-6"
    >
      <div className="relative w-full max-w-xl flex flex-col rounded-[16px] bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50">
          <h2 id="publish-checklist-title" className="font-heading text-lg font-bold text-slate-900">
            Publish Pre-Flight Checklist
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {isLoading ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
            </div>
          ) : error ? (
            <div className="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 border border-rose-200">
              Failed to evaluate pre-flight checklist. Please verify revision state.
            </div>
          ) : checklist ? (
            <>
              {/* Mutation Error Feedback */}
              {publishMutation.error && (
                <div className="flex items-start gap-2.5 rounded-lg border border-rose-300 bg-rose-50 p-3.5 text-xs text-rose-900">
                  <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold">Publishing Blocked</p>
                    <p className="mt-0.5 text-rose-700">
                      {publishMutation.error instanceof Error
                        ? publishMutation.error.message
                        : "Pre-flight checklist validation failed. Please address the blockers below before publishing."}
                    </p>
                  </div>
                </div>
              )}

              {/* Overall Status Banner */}
              <div
                className={`flex items-start gap-3 rounded-[12px] p-4 border ${
                  checklist.can_publish
                    ? "bg-teal-50 border-teal-200 text-teal-900"
                    : "bg-rose-50 border-rose-200 text-rose-900"
                }`}
              >
                {checklist.can_publish ? (
                  <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
                )}
                <div>
                  <h3 className="font-heading font-bold text-sm">
                    {checklist.can_publish
                      ? "Ready for Publication"
                      : "Publication Blocked: Issues Require Resolution"}
                  </h3>
                  <p className="text-xs mt-1 text-slate-600">
                    Revision #{checklist.revision_no} has been evaluated against curriculum and content standards.
                  </p>
                </div>
              </div>

              {/* Blockers */}
              {checklist.blockers && checklist.blockers.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-rose-700">
                    Blocking Issues ({checklist.blockers.length})
                  </h4>
                  <div className="space-y-2">
                    {checklist.blockers.map((b, idx) => {
                      const hint = getActionableHint(b.code);
                      return (
                        <div
                          key={idx}
                          className="flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50/50 p-3 text-xs text-rose-900"
                        >
                          <XCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="font-semibold text-rose-950">{b.message}</p>
                            {hint && (
                              <p className="text-[11px] text-slate-700 mt-1 bg-white/70 rounded p-1.5 border border-rose-100">
                                <span className="font-semibold text-slate-900">How to fix: </span>
                                {hint}
                              </p>
                            )}
                            <p className="text-[10px] text-rose-500 mt-1 font-mono">Code: {b.code}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {checklist.warnings && checklist.warnings.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-700">
                    Recommended Improvements ({checklist.warnings.length})
                  </h4>
                  <div className="space-y-2">
                    {checklist.warnings.map((w, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2.5 rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-xs text-amber-900"
                      >
                        <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold">{w.message}</p>
                          <p className="text-[11px] text-amber-700 mt-0.5 font-mono">Code: {w.code}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state when fully compliant */}
              {checklist.can_publish && checklist.blockers.length === 0 && checklist.warnings.length === 0 && (
                <div className="text-center py-6 text-sm text-slate-600">
                  All automated checks passed. Ready to snapshot and deploy this revision as the live version.
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 bg-slate-50">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!checklist?.can_publish || publishMutation.isPending}
            isLoading={publishMutation.isPending}
            onClick={() => publishMutation.mutate()}
          >
            <UploadCloud className="h-4 w-4 mr-2" />
            Publish Live Snapshot
          </Button>
        </div>
      </div>
    </div>
  );
};
