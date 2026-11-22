"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  CheckSquare,
  Clock,
  AlertCircle,
  FileText,
  Award,
  CheckCircle2,
  Send,
  ExternalLink,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { assignmentsApi } from "@/lib/api/assignments";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { AssignmentResponse, SubmissionResponse } from "@/types/assignment";

export default function AssignmentDetailPage() {
  const params = useParams();
  const rawId = params?.id as string;
  const queryClient = useQueryClient();

  // Form states with input preservation
  const [fileUrl, setFileUrl] = useState("");
  const [textNotes, setTextNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // Fetch Assignment details (fallback to lesson assignment if needed)
  const {
    data: assignment,
    isLoading: isAssignmentLoading,
    isError: isAssignmentError,
    error: assignmentError,
    refetch: refetchAssignment,
  } = useQuery<AssignmentResponse>({
    queryKey: ["assignment-detail", rawId],
    queryFn: async () => {
      try {
        return await assignmentsApi.getAssignment(rawId);
      } catch {
        return await assignmentsApi.getLessonAssignment(rawId);
      }
    },
    enabled: !!rawId,
  });

  // Fetch Student's Submission for this assignment if available
  const { data: submissionsData, refetch: refetchSubmissions } = useQuery({
    queryKey: ["assignment-submissions", assignment?.id],
    queryFn: () =>
      assignment?.id
        ? assignmentsApi.listAssignmentSubmissions(assignment.id, { page: 1, size: 1 })
        : null,
    enabled: !!assignment?.id,
    retry: false,
  });

  const latestSubmission = submissionsData?.items?.[0] as SubmissionResponse | undefined;

  // Submit project mutation
  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!assignment?.id) throw new Error("Assignment not ready");
      return await assignmentsApi.submitProject(assignment.id, {
        file_url: fileUrl.trim(),
        text_notes: textNotes.trim() || undefined,
      });
    },
    onSuccess: (data) => {
      setFormSuccess("Project submitted successfully for grading!");
      setFormError(null);
      queryClient.invalidateQueries({ queryKey: ["assignment-submissions", assignment?.id] });
    },
    onError: (err: any) => {
      // PRESERVE INPUT ON ERROR - NEVER CLEAR FORM
      setFormError(
        err?.message ||
          "Failed to submit project work. Your input has been preserved. Please retry."
      );
      setFormSuccess(null);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    if (!fileUrl.trim()) {
      setFormError("Project repository or storage file URL is required.");
      return;
    }

    submitMutation.mutate();
  };

  if (isAssignmentLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (isAssignmentError || !assignment) {
    return (
      <div className="space-y-6">
        <Link
          href="/app/assignments"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Assignments
        </Link>
        <ErrorAlert
          title="Could not find assignment"
          message={
            assignmentError?.message ||
            "The requested assignment or lesson project could not be found."
          }
          onRetry={() => refetchAssignment()}
        />
      </div>
    );
  }

  const rubric = assignment.active_rubric;

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <Link
          href="/app/assignments"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Assignments
        </Link>
      </div>

      {/* Assignment Header */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-6 sm:p-8 shadow-card space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <Badge variant="outline" size="sm">
            Assignment
          </Badge>
          <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
            {assignment.due_date && (
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5 text-slate-400" />
                Due: {new Date(assignment.due_date).toLocaleDateString()}
              </span>
            )}
            <span>Pass Score: {assignment.pass_score} / {assignment.max_score}</span>
          </div>
        </div>

        <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">
          {assignment.title}
        </h1>

        <div className="prose prose-slate max-w-none text-sm sm:text-base text-slate-700 font-sans whitespace-pre-wrap">
          {assignment.instructions}
        </div>
      </div>

      {/* Active Rubric Criteria */}
      {rubric && rubric.criteria?.length > 0 && (
        <Card className="p-6 sm:p-8 border border-slate-200 bg-white">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-heading text-lg font-bold text-slate-900">
                Evaluation Rubric (Version {rubric.version})
              </h2>
              <p className="font-sans text-xs text-slate-500">
                Your project will be evaluated according to these weighted criteria:
              </p>
            </div>
            <Award className="h-5 w-5 text-accent-coral" />
          </div>

          <div className="divide-y divide-slate-100">
            {rubric.criteria.map((c) => (
              <div key={c.id} className="py-3 flex items-start justify-between gap-4">
                <div>
                  <h4 className="font-heading text-sm font-bold text-slate-800">
                    {c.title}
                  </h4>
                  {c.description && (
                    <p className="text-xs text-slate-600 mt-0.5">{c.description}</p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <span className="font-mono text-xs font-semibold text-slate-900">
                    Max: {c.max_points} pts
                  </span>
                  {c.weight !== 1.0 && (
                    <p className="font-mono text-[10px] text-slate-400">
                      weight: {c.weight}x
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Existing Submission Status Card if Submitted */}
      {latestSubmission && (
        <Card className="p-6 border border-slate-200 bg-slate-50/70 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-heading text-base font-bold text-slate-900">
              Latest Submission (Attempt #{latestSubmission.attempt_no})
            </h3>
            <Badge
              variant={
                latestSubmission.status === "GRADED"
                  ? (latestSubmission.final_score ?? 0) >= assignment.pass_score
                    ? "mint"
                    : "error"
                  : latestSubmission.status === "SUBMITTED"
                  ? "outline"
                  : "coral"
              }
              size="sm"
            >
              {latestSubmission.status}
            </Badge>
          </div>

          <div className="space-y-1 text-xs sm:text-sm font-sans text-slate-700">
            <p>
              <span className="font-semibold">Submitted File:</span>{" "}
              <a
                href={latestSubmission.file_url}
                target="_blank"
                rel="noreferrer"
                className="text-primary-teal underline inline-flex items-center gap-1 font-mono break-all"
              >
                {latestSubmission.file_url}
                <ExternalLink className="h-3 w-3 inline" />
              </a>
            </p>
            {latestSubmission.text_notes && (
              <p>
                <span className="font-semibold">Student Notes:</span> {latestSubmission.text_notes}
              </p>
            )}
            <p className="text-slate-500 font-mono text-xs">
              Submitted on: {new Date(latestSubmission.submitted_at).toLocaleString()}
            </p>
          </div>

          {/* Graded Feedback & Rubric Scores */}
          {latestSubmission.status === "GRADED" && (
            <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-heading text-sm font-bold text-slate-900">
                  Final Evaluated Score:
                </span>
                <span className="font-mono text-base font-bold text-primary-teal">
                  {latestSubmission.final_score} / {assignment.max_score} pts
                </span>
              </div>

              {latestSubmission.feedback && (
                <div className="rounded-lg bg-white p-3 border border-slate-200 text-xs text-slate-800">
                  <span className="font-semibold block mb-1">Evaluator Feedback:</span>
                  <p>{latestSubmission.feedback}</p>
                </div>
              )}

              {latestSubmission.rubric_scores?.length > 0 && (
                <div className="space-y-1.5 pt-2">
                  <span className="font-heading text-xs font-bold text-slate-800">
                    Criterion Breakdown:
                  </span>
                  {latestSubmission.rubric_scores.map((rs) => (
                    <div
                      key={rs.id}
                      className="flex items-center justify-between text-xs font-sans bg-white px-3 py-1.5 rounded border border-slate-100"
                    >
                      <span className="text-slate-700">{rs.criteria_title || "Criterion"}</span>
                      <span className="font-mono font-semibold text-slate-900">
                        {rs.points_awarded} pts
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Project Submission Form */}
      <Card className="p-6 sm:p-8 border border-slate-200 bg-white">
        <h2 className="font-heading text-lg font-bold text-slate-900 mb-1">
          {latestSubmission ? "Submit New Project Revision" : "Submit Your Project Work"}
        </h2>
        <p className="font-sans text-xs text-slate-500 mb-6">
          Provide your project file URL (GitHub repo, S3 link, or cloud drive) and any notes for the instructor.
        </p>

        {formError && (
          <div className="mb-4">
            <ErrorAlert message={formError} />
          </div>
        )}

        {formSuccess && (
          <div className="mb-4 flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs sm:text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <span>{formSuccess}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Project File / Repository URL"
            type="url"
            placeholder="https://github.com/student/my-project or file link"
            value={fileUrl}
            onChange={(e) => setFileUrl(e.target.value)}
            required
            helperText="Public repository or accessible direct download URL"
          />

          <Textarea
            label="Project Commentary & Implementation Notes (Optional)"
            placeholder="Describe your architectural approach, any challenges faced, and instructions for running your project..."
            value={textNotes}
            onChange={(e) => setTextNotes(e.target.value)}
            rows={5}
          />

          <div className="pt-2 flex justify-end">
            <Button
              type="submit"
              variant="primary"
              size="default"
              isLoading={submitMutation.isPending}
            >
              <Send className="mr-2 h-4 w-4" />
              {latestSubmission ? "Submit New Revision" : "Submit Project"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
