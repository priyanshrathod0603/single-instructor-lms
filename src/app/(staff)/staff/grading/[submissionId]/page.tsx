"use client";

import React, { useState, useEffect, use } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  FileText,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ShieldAlert,
  Loader2,
  Check,
  Download,
} from "lucide-react";
import { assignmentsApi } from "@/lib/api/assignments";
import { useAuth } from "@/lib/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";

export default function SubmissionGradingWorkspacePage({
  params,
}: {
  params: Promise<{ submissionId: string }>;
}) {
  const resolvedParams = use(params);
  const submissionId = resolvedParams.submissionId;
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const isAdminOrSuper =
    user?.roles?.includes("ADMIN") || user?.roles?.includes("SUPER_ADMIN");

  // Query Submission
  const { data: submission, isLoading: subLoading } = useQuery({
    queryKey: ["submission", submissionId],
    queryFn: () => assignmentsApi.getSubmission(submissionId),
  });

  // Query Assignment to obtain active Rubric
  const { data: assignment, isLoading: assignLoading } = useQuery({
    queryKey: ["assignment", submission?.assignment_id],
    queryFn: () => assignmentsApi.getAssignment(submission!.assignment_id),
    enabled: !!submission?.assignment_id,
  });

  const rubric = assignment?.active_rubric;

  // Rubric Scores Form State
  const [criterionScores, setCriterionScores] = useState<Record<string, number>>({});
  const [criterionFeedbacks, setCriterionFeedbacks] = useState<Record<string, string>>({});
  const [generalFeedback, setGeneralFeedback] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Admin Override State
  const [overrideScore, setOverrideScore] = useState<number>(100);
  const [overrideReason, setOverrideReason] = useState<string>("");
  const [isOverrideOpen, setIsOverrideOpen] = useState(false);

  useEffect(() => {
    if (submission && rubric) {
      const scores: Record<string, number> = {};
      const feedbacks: Record<string, string> = {};

      // If already graded, pre-fill
      if (submission.rubric_scores && submission.rubric_scores.length > 0) {
        submission.rubric_scores.forEach((rs) => {
          scores[rs.criteria_id] = rs.points_awarded;
          if (rs.feedback) feedbacks[rs.criteria_id] = rs.feedback;
        });
      } else {
        // Default each criterion to max points
        rubric.criteria.forEach((c) => {
          scores[c.id] = c.max_points;
        });
      }

      setCriterionScores(scores);
      setCriterionFeedbacks(feedbacks);
      setGeneralFeedback(submission.feedback || "");
    }
  }, [submission, rubric]);

  // Compute calculated score
  const totalScore = Object.values(criterionScores).reduce((sum, val) => sum + (val || 0), 0);

  // Grade Submission Mutation
  const gradeMutation = useMutation({
    mutationFn: () => {
      const scores = Object.entries(criterionScores).map(([criteriaId, points]) => ({
        criteria_id: criteriaId,
        points_awarded: Number(points),
        feedback: criterionFeedbacks[criteriaId] || null,
      }));

      return assignmentsApi.gradeSubmission(submissionId, {
        scores,
        overall_feedback: generalFeedback,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["submission", submissionId] });
      setSuccessMessage("Grade successfully evaluated and recorded!");
      setTimeout(() => setSuccessMessage(null), 3000);
    },
    onError: (err: any) => {
      setErrorMessage(err?.message || "Failed to record submission grade.");
    },
  });

  // Override Grade Mutation (Admin Only)
  const overrideMutation = useMutation({
    mutationFn: () =>
      assignmentsApi.overrideGrade(submissionId, {
        new_score: Number(overrideScore),
        reason: overrideReason.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["submission", submissionId] });
      setIsOverrideOpen(false);
      setSuccessMessage("Administrative grade override recorded.");
      setTimeout(() => setSuccessMessage(null), 3000);
    },
    onError: (err: any) => {
      setErrorMessage(err?.message || "Failed to execute grade override.");
    },
  });

  if (subLoading || assignLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
      </div>
    );
  }

  if (!submission) {
    return (
      <div className="rounded-[16px] bg-rose-50 p-8 text-center text-rose-800">
        Submission not found.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Breadcrumb */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Link href="/staff/grading" className="hover:text-slate-800 flex items-center gap-1">
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Grading Queue</span>
          </Link>
          <span>/</span>
          <span className="text-slate-700 font-medium">Evaluation Workspace</span>
        </div>
        <Badge variant={submission.status === "GRADED" ? "success" : "outline"}>
          {submission.status}
        </Badge>
      </div>

      {successMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-4 text-sm text-rose-700 border border-rose-200">
          <AlertCircle className="h-5 w-5 text-rose-600 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Pane: Student Submission Details */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-6 shadow-sm space-y-5">
          <div className="border-b border-slate-100 pb-4">
            <h2 className="font-heading text-lg font-bold text-slate-900">
              Student Project Submission
            </h2>
            <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
              <span className="font-semibold text-slate-800">
                {submission.student_name || "Student"}
              </span>
              <span>·</span>
              <span>{submission.student_email || submission.student_id}</span>
              <span>·</span>
              <span>Attempt #{submission.attempt_no}</span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Submitted on: {new Date(submission.submitted_at).toLocaleString()}
            </p>
          </div>

          {/* Submission Notes */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">
              Student Accompanying Notes
            </h3>
            <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-800 border border-slate-100 whitespace-pre-wrap">
              {submission.text_notes || "No additional text notes provided."}
            </div>
          </div>

          {/* Submitted File / Project Artifact */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5">
              Project Artifact Attachment
            </h3>
            <div className="flex items-center justify-between rounded-[12px] border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-3 min-w-0">
                <FileText className="h-6 w-6 text-primary-teal shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate" title={submission.file_url}>
                    {submission.file_url.split("/").pop() || "project_submission.zip"}
                  </p>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-xs">
                    {submission.file_url}
                  </p>
                </div>
              </div>
              <a
                href={submission.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0"
              >
                <Button variant="outline" size="sm">
                  <Download className="h-3.5 w-3.5 mr-1" />
                  Download
                </Button>
              </a>
            </div>
          </div>

          {/* Existing Grade Status if Graded */}
          {submission.final_score !== null && submission.final_score !== undefined && (
            <div className="rounded-[12px] bg-teal-50/60 border border-teal-200 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-teal-800">
                  Recorded Final Score
                </span>
                <span className="text-xl font-extrabold text-teal-900">
                  {submission.final_score} Points
                </span>
              </div>
              {submission.grader_name && (
                <p className="text-xs text-teal-700">
                  Evaluated by: {submission.grader_name} on{" "}
                  {submission.graded_at ? new Date(submission.graded_at).toLocaleDateString() : ""}
                </p>
              )}
            </div>
          )}

          {/* Admin Grade Override Accordion / Trigger */}
          {isAdminOrSuper && (
            <div className="pt-4 border-t border-slate-100">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsOverrideOpen(!isOverrideOpen)}
                className="text-slate-600 hover:text-slate-900 text-xs"
              >
                <ShieldAlert className="h-3.5 w-3.5 mr-1 text-amber-600" />
                {isOverrideOpen ? "Hide Administrative Override" : "Administrative Grade Override"}
              </Button>

              {isOverrideOpen && (
                <div className="mt-3 p-4 rounded-lg bg-amber-50/60 border border-amber-200 space-y-3">
                  <h4 className="text-xs font-bold uppercase text-amber-900">
                    Administrator Score Override
                  </h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[11px] font-bold text-slate-700">Override Points</label>
                      <Input
                        type="number"
                        value={overrideScore}
                        onChange={(e) => setOverrideScore(Number(e.target.value))}
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-slate-700">Mandatory Reason</label>
                      <Input
                        value={overrideReason}
                        onChange={(e) => setOverrideReason(e.target.value)}
                        placeholder="e.g. Formal dispute approved"
                      />
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!overrideReason.trim() || overrideMutation.isPending}
                    isLoading={overrideMutation.isPending}
                    onClick={() => overrideMutation.mutate()}
                    className="bg-amber-600 hover:bg-amber-700"
                  >
                    Apply Override
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Pane: Standardized Rubric Evaluation Form */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-6 shadow-sm space-y-6">
          <div className="border-b border-slate-100 pb-4 flex items-center justify-between">
            <div>
              <h2 className="font-heading text-lg font-bold text-slate-900">
                Rubric Evaluation
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {rubric ? rubric.title : "Default Grading Criteria"}
              </p>
            </div>
            <div className="text-right">
              <span className="text-xs text-slate-400 font-medium">Computed Total</span>
              <p className="text-2xl font-extrabold text-primary-teal">{totalScore} pts</p>
            </div>
          </div>

          {!rubric?.criteria || rubric.criteria.length === 0 ? (
            <div className="p-6 text-center text-slate-500 text-sm">
              No active rubric configured for this assignment.
            </div>
          ) : (
            <div className="space-y-6">
              {rubric.criteria.map((criterion) => {
                const currentVal = criterionScores[criterion.id] ?? criterion.max_points;

                return (
                  <div
                    key={criterion.id}
                    className="rounded-[12px] border border-slate-200 p-4 bg-slate-50/50 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-sm font-bold text-slate-900">{criterion.title}</h4>
                        {criterion.description && (
                          <p className="text-xs text-slate-500 mt-0.5">{criterion.description}</p>
                        )}
                      </div>
                      <span className="text-xs font-bold text-slate-700">
                        Max: {criterion.max_points} pts
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min="0"
                        max={criterion.max_points}
                        value={currentVal}
                        onChange={(e) =>
                          setCriterionScores({
                            ...criterionScores,
                            [criterion.id]: Number(e.target.value),
                          })
                        }
                        className="flex-1 accent-primary-teal"
                      />
                      <Input
                        type="number"
                        min="0"
                        max={criterion.max_points}
                        value={currentVal}
                        onChange={(e) =>
                          setCriterionScores({
                            ...criterionScores,
                            [criterion.id]: Number(e.target.value),
                          })
                        }
                        className="w-20 text-center font-bold"
                      />
                    </div>

                    <Input
                      placeholder="Optional criterion-specific feedback..."
                      value={criterionFeedbacks[criterion.id] || ""}
                      onChange={(e) =>
                        setCriterionFeedbacks({
                          ...criterionFeedbacks,
                          [criterion.id]: e.target.value,
                        })
                      }
                      className="text-xs bg-white"
                    />
                  </div>
                );
              })}

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  General Instructor Feedback
                </label>
                <Textarea
                  rows={4}
                  value={generalFeedback}
                  onChange={(e) => setGeneralFeedback(e.target.value)}
                  placeholder="Provide comprehensive, encouraging pedagogical feedback to help the student grow..."
                />
              </div>

              <div className="pt-2">
                <Button
                  variant="primary"
                  size="default"
                  className="w-full justify-center"
                  isLoading={gradeMutation.isPending}
                  onClick={() => gradeMutation.mutate()}
                >
                  <Check className="h-4 w-4 mr-2" />
                  Save & Publish Evaluation
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
