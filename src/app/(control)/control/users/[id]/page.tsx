"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Users,
  BookOpen,
  Award,
  FileCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Shield,
  Loader2,
  ExternalLink,
  ShieldAlert,
  UserX,
  UserCheck,
  Lock,
  History,
  FileText,
  Calendar,
  Percent,
} from "lucide-react";
import { usersApi } from "@/lib/api/users";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
} from "@/components/ui/Modal";

type ActiveTab = "enrollments" | "quizzes" | "assignments" | "certificates" | "audit";

export default function UserProfileDetailPage() {
  const params = useParams();
  const userId = params?.id as string;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<ActiveTab>("enrollments");

  // Modals for admin actions
  const [isStatusModalOpen, setIsStatusModalOpen] = useState(false);
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);

  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [targetRoleId, setTargetRoleId] = useState("STUDENT");
  const [roleAction, setRoleAction] = useState<"ASSIGN" | "REVOKE">("ASSIGN");
  const [roleError, setRoleError] = useState<string | null>(null);

  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Fetch full learning records
  const { data, isLoading, error } = useQuery({
    queryKey: ["control-user-learning-summary", userId],
    queryFn: () => usersApi.getStudentLearningRecords(userId),
    enabled: Boolean(userId),
  });

  // Status mutation
  const statusMutation = useMutation({
    mutationFn: () => {
      if (!data) throw new Error("User not loaded");
      return usersApi.updateStatus(userId, {
        is_active: !data.user.is_active,
        reason: statusReason.trim() || undefined,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-user-learning-summary", userId] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setIsStatusModalOpen(false);
      setStatusReason("");
      setStatusError(null);
      setFeedback({
        type: "success",
        text: `Account for ${updated.full_name} is now ${updated.is_active ? "Active" : "Suspended"}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setStatusError(err?.message || "Failed to update account status.");
    },
  });

  // Role mutation
  const roleMutation = useMutation({
    mutationFn: () => {
      return usersApi.manageRole(userId, {
        role_id: targetRoleId,
        action: roleAction,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-user-learning-summary", userId] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setIsRoleModalOpen(false);
      setRoleError(null);
      setFeedback({
        type: "success",
        text: `Successfully ${roleAction === "ASSIGN" ? "assigned" : "revoked"} role '${targetRoleId}' for ${updated.full_name}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setRoleError(err?.message || "Failed to update user role.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-[16px] border border-red-200 bg-red-50 p-6 text-center space-y-3">
        <AlertTriangle className="h-8 w-8 text-red-600 mx-auto" />
        <h2 className="text-lg font-bold text-red-900">User Profile Unavailable</h2>
        <p className="text-sm text-red-700">
          {(error as any)?.message || "Could not retrieve user learning history."}
        </p>
        <Link href="/control/users">
          <Button variant="outline" size="sm">
            <ArrowLeft className="h-4 w-4 mr-1.5" />
            Back to User Directory
          </Button>
        </Link>
      </div>
    );
  }

  const { user, enrollments, quiz_attempts, assignment_submissions, certificates, audit_logs } = data;
  const isSuperAdmin = user.roles.includes("SUPER_ADMIN");

  return (
    <div className="space-y-6">
      {/* Back button & Breadcrumbs */}
      <div className="flex items-center gap-2">
        <Link
          href="/control/users"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to User Directory
        </Link>
      </div>

      {/* Global Feedback Banner */}
      {feedback && (
        <div
          role="alert"
          className={`flex items-center gap-2 rounded-lg p-4 text-sm border ${
            feedback.type === "success"
              ? "bg-teal-50 text-teal-800 border-teal-200"
              : "bg-red-50 text-red-800 border-red-200"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          ) : (
            <AlertTriangle className="h-5 w-5 text-red-600 shrink-0" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Header Profile Card */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="h-16 w-16 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-2xl shrink-0 shadow-md">
              {user.full_name?.charAt(0)?.toUpperCase() || "U"}
            </div>
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-bold font-heading text-slate-900">{user.full_name}</h1>
                {isSuperAdmin && (
                  <Badge variant="error" className="gap-1 text-[11px]">
                    <Lock className="h-3 w-3" />
                    Platform Owner
                  </Badge>
                )}
                <Badge variant={user.is_active ? "success" : "error"}>
                  {user.is_active ? "Active" : "Suspended"}
                </Badge>
                {user.is_verified ? (
                  <span className="inline-flex items-center gap-1 text-xs text-teal-700 font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Verified Email
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-700 font-medium">
                    <XCircle className="h-3.5 w-3.5" />
                    Unverified
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 font-mono">{user.email}</div>
              <div className="text-[11px] text-slate-400">
                User ID: <span className="font-mono">{user.id}</span> • Registered:{" "}
                {new Date(user.created_at).toLocaleDateString()}
              </div>
              <div className="flex flex-wrap gap-1 pt-1">
                {user.roles.map((r) => (
                  <Badge key={r} variant="outline" className="text-[11px]">
                    {r}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRoleError(null);
                setTargetRoleId(user.roles[0] || "STUDENT");
                setRoleAction("ASSIGN");
                setIsRoleModalOpen(true);
              }}
            >
              <Shield className="h-4 w-4 mr-1.5 text-slate-600" />
              Manage Roles
            </Button>
            <Button
              variant={user.is_active ? "outline" : "primary"}
              size="sm"
              onClick={() => {
                setStatusError(null);
                setStatusReason("");
                setIsStatusModalOpen(true);
              }}
            >
              {user.is_active ? (
                <UserX className="h-4 w-4 mr-1.5 text-red-500" />
              ) : (
                <UserCheck className="h-4 w-4 mr-1.5 text-teal-600" />
              )}
              {user.is_active ? "Suspend Account" : "Activate Account"}
            </Button>
          </div>
        </div>

        {/* Academic KPI Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-100">
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500 font-medium">Enrolled Courses</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{enrollments.length}</div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500 font-medium">Quiz Attempts</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{quiz_attempts.length}</div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500 font-medium">Assignments</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{assignment_submissions.length}</div>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <div className="text-xs text-slate-500 font-medium">Certificates</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{certificates.length}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 overflow-x-auto gap-1">
        <button
          onClick={() => setActiveTab("enrollments")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeTab === "enrollments"
              ? "border-primary-teal text-primary-teal bg-teal-50/50"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <BookOpen className="h-4 w-4" />
          Course Enrollments ({enrollments.length})
        </button>
        <button
          onClick={() => setActiveTab("quizzes")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeTab === "quizzes"
              ? "border-primary-teal text-primary-teal bg-teal-50/50"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <FileCheck className="h-4 w-4" />
          Quiz Assessments ({quiz_attempts.length})
        </button>
        <button
          onClick={() => setActiveTab("assignments")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeTab === "assignments"
              ? "border-primary-teal text-primary-teal bg-teal-50/50"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <FileText className="h-4 w-4" />
          Assignment Deliverables ({assignment_submissions.length})
        </button>
        <button
          onClick={() => setActiveTab("certificates")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeTab === "certificates"
              ? "border-primary-teal text-primary-teal bg-teal-50/50"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <Award className="h-4 w-4" />
          Certificates ({certificates.length})
        </button>
        <button
          onClick={() => setActiveTab("audit")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
            activeTab === "audit"
              ? "border-primary-teal text-primary-teal bg-teal-50/50"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <History className="h-4 w-4" />
          Audit Trail ({audit_logs.length})
        </button>
      </div>

      {/* Tab Panels */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-6 shadow-sm">
        {/* Tab 1: Enrollments */}
        {activeTab === "enrollments" && (
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Enrolled Courses & Completion Progress</h3>
            {!enrollments.length ? (
              <div className="py-12 text-center text-slate-400 text-xs">
                No active or historical course enrollments found for this student.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {enrollments.map((enr) => (
                  <div key={enr.id} className="py-4 first:pt-0 last:pb-0 space-y-2">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <div className="font-semibold text-sm text-slate-900">{enr.course_title}</div>
                        <div className="text-xs text-slate-500">
                          Granted: {new Date(enr.granted_at).toLocaleDateString()} •{" "}
                          {enr.expires_at
                            ? `Expires: ${new Date(enr.expires_at).toLocaleDateString()}`
                            : "Lifetime Access"}
                        </div>
                      </div>
                      <Badge variant={enr.status === "ACTIVE" ? "success" : "error"}>
                        {enr.status}
                      </Badge>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs text-slate-600">
                        <span>
                          {enr.completed_lessons_count} of {enr.total_lessons_count} lessons completed
                        </span>
                        <span className="font-semibold text-slate-900">{enr.progress_percentage}%</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className="h-full bg-primary-teal rounded-full transition-all duration-300"
                          style={{ width: `${Math.min(100, enr.progress_percentage)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Quizzes */}
        {activeTab === "quizzes" && (
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Quiz Assessment Attempts & Scores</h3>
            {!quiz_attempts.length ? (
              <div className="py-12 text-center text-slate-400 text-xs">
                No quiz assessment attempts recorded.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-600">
                  <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3">Quiz</th>
                      <th className="px-4 py-3">Attempt #</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Score</th>
                      <th className="px-4 py-3">Result</th>
                      <th className="px-4 py-3">Completed At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {quiz_attempts.map((att) => (
                      <tr key={att.id} className="hover:bg-slate-50/50">
                        <td className="px-4 py-3 font-semibold text-slate-900">{att.quiz_title}</td>
                        <td className="px-4 py-3">Attempt {att.attempt_no}</td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">{att.status}</Badge>
                        </td>
                        <td className="px-4 py-3 font-mono font-semibold">
                          {att.score !== null ? `${att.score}%` : "—"}
                        </td>
                        <td className="px-4 py-3">
                          {att.is_passed === true ? (
                            <Badge variant="success">Passed</Badge>
                          ) : att.is_passed === false ? (
                            <Badge variant="error">Failed</Badge>
                          ) : (
                            <span className="text-slate-400">Pending</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-500">
                          {att.completed_at ? new Date(att.completed_at).toLocaleString() : "In Progress"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Assignments */}
        {activeTab === "assignments" && (
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Assignment Deliverables & Rubric Grading</h3>
            {!assignment_submissions.length ? (
              <div className="py-12 text-center text-slate-400 text-xs">
                No assignment project deliverables submitted.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {assignment_submissions.map((sub) => (
                  <div key={sub.id} className="py-4 first:pt-0 last:pb-0 space-y-2">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <div className="font-semibold text-sm text-slate-900">{sub.assignment_title}</div>
                        <div className="text-xs text-slate-500">
                          Attempt #{sub.attempt_no} • Submitted:{" "}
                          {new Date(sub.submitted_at).toLocaleDateString()}
                          {sub.graded_at && ` • Graded: ${new Date(sub.graded_at).toLocaleDateString()}`}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            sub.status === "GRADED"
                              ? "success"
                              : sub.status === "REJECTED"
                              ? "error"
                              : "peach"
                          }
                        >
                          {sub.status}
                        </Badge>
                        {sub.final_score !== null && (
                          <span className="font-bold text-sm text-slate-900 font-mono">
                            {sub.final_score} / {sub.max_score}
                          </span>
                        )}
                      </div>
                    </div>

                    {sub.feedback && (
                      <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-700 border border-slate-100">
                        <span className="font-semibold text-slate-900">Evaluator Feedback:</span> {sub.feedback}
                      </div>
                    )}

                    {sub.file_url && (
                      <div className="text-xs">
                        <a
                          href={sub.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-primary-teal hover:underline font-medium"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Download Deliverable Archive
                        </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Certificates */}
        {activeTab === "certificates" && (
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Digitally Verifiable Certificates</h3>
            {!certificates.length ? (
              <div className="py-12 text-center text-slate-400 text-xs">
                No completion certificates earned yet.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {certificates.map((cert) => (
                  <div
                    key={cert.id}
                    className="rounded-xl border border-slate-200 p-4 space-y-3 bg-gradient-to-br from-white to-slate-50 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Award className="h-6 w-6 text-amber-500 shrink-0" />
                        <div>
                          <div className="font-bold text-sm text-slate-900">{cert.certificate_no}</div>
                          <div className="text-xs text-slate-600">{cert.course_title}</div>
                        </div>
                      </div>
                      <Badge variant={cert.is_revoked ? "error" : "success"}>
                        {cert.is_revoked ? "Revoked" : "Verifiable"}
                      </Badge>
                    </div>

                    <div className="space-y-1 text-xs text-slate-500">
                      <div>Issued: {new Date(cert.issued_at).toLocaleDateString()}</div>
                      <div className="font-mono text-[11px] truncate">Hash: {cert.verification_hash}</div>
                    </div>

                    <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
                      <Link
                        href={`/verify/certificate/${cert.verification_hash}`}
                        target="_blank"
                        className="inline-flex items-center gap-1 text-xs text-primary-teal hover:underline font-medium"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Public Verification
                      </Link>
                      {cert.pdf_url && (
                        <a
                          href={cert.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900 font-medium ml-auto"
                        >
                          <FileText className="h-3.5 w-3.5" />
                          Certificate PDF
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 5: Audit Trail */}
        {activeTab === "audit" && (
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Security & Operational Activity Trail</h3>
            {!audit_logs.length ? (
              <div className="py-12 text-center text-slate-400 text-xs">
                No recent security audit actions recorded for this account.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-600">
                  <thead className="bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3">Action</th>
                      <th className="px-4 py-3">Actor Type</th>
                      <th className="px-4 py-3">Resource</th>
                      <th className="px-4 py-3">IP Address</th>
                      <th className="px-4 py-3">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {audit_logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50/50">
                        <td className="px-4 py-3 font-mono font-semibold text-slate-900">{log.action}</td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">{log.actor_type}</Badge>
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {log.resource_type} {log.resource_id ? `(${log.resource_id.slice(0, 8)}…)` : ""}
                        </td>
                        <td className="px-4 py-3 text-slate-500 font-mono">{log.ip_address || "—"}</td>
                        <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Role Management Modal */}
      {isRoleModalOpen && (
        <Modal open={true} onOpenChange={(open) => !open && setIsRoleModalOpen(false)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Manage Roles: {user.full_name}</ModalTitle>
              <ModalDescription>
                Assign or revoke authoritative system roles. Changes take effect on next token/session refresh.
              </ModalDescription>
            </ModalHeader>

            {roleError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{roleError}</span>
              </div>
            )}

            <div className="space-y-4 text-xs">
              <div>
                <span className="font-semibold text-slate-700">Currently Assigned Roles:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {user.roles.map((r) => (
                    <Badge key={r} variant="outline">
                      {r}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="font-semibold text-slate-700">Target Role:</label>
                <select
                  value={targetRoleId}
                  onChange={(e) => setTargetRoleId(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="STUDENT">STUDENT — Enrolled Learner</option>
                  <option value="STAFF">STAFF — Teaching Assistant / Grader</option>
                  <option value="ADMIN">ADMIN — Delegated Operations</option>
                  <option value="SUPER_ADMIN">SUPER_ADMIN — Platform Owner</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="font-semibold text-slate-700">Action:</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="profile-role-action"
                      checked={roleAction === "ASSIGN"}
                      onChange={() => setRoleAction("ASSIGN")}
                    />
                    <span>Grant Role</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="profile-role-action"
                      checked={roleAction === "REVOKE"}
                      onChange={() => setRoleAction("REVOKE")}
                    />
                    <span>Revoke Role</span>
                  </label>
                </div>
              </div>

              {isSuperAdmin && roleAction === "REVOKE" && targetRoleId === "SUPER_ADMIN" && (
                <div className="rounded-lg bg-amber-50 p-3 text-[11px] text-amber-800 border border-amber-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                  <span>
                    <strong>Invariant Protection:</strong> The sole active Super Admin cannot be demoted. The database
                    will reject this transaction if no other active Super Admin exists.
                  </span>
                </div>
              )}
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsRoleModalOpen(false)}
                disabled={roleMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => roleMutation.mutate()}
                disabled={roleMutation.isPending}
              >
                {roleMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Confirm Role Update
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}

      {/* Account Status Toggle Modal */}
      {isStatusModalOpen && (
        <Modal open={true} onOpenChange={(open) => !open && setIsStatusModalOpen(false)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>
                {user.is_active ? "Suspend Account" : "Activate Account"}: {user.full_name}
              </ModalTitle>
              <ModalDescription>
                {user.is_active
                  ? "Suspending this user account immediately revokes all active sessions. The student's learning history and enrollments remain preserved."
                  : "Activating this account restores login capabilities for the user."}
              </ModalDescription>
            </ModalHeader>

            {statusError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              {user.is_active && (
                <div className="rounded-lg bg-red-50 p-3 text-red-800 border border-red-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
                  <div>
                    <strong>Immediate Session Displacement:</strong> The user will be immediately logged out across all devices.
                    Future authentication requests will fail closed with HTTP 403 ACCOUNT_SUSPENDED.
                  </div>
                </div>
              )}

              {isSuperAdmin && user.is_active && (
                <div className="rounded-lg bg-amber-50 p-3 text-amber-800 border border-amber-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                  <span>
                    <strong>Invariant Protection:</strong> Cannot suspend the sole active Super Admin account.
                  </span>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-700">Audit Justification / Reason (Optional):</label>
                <Input
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  placeholder="e.g., Requested account freeze, dispute investigation…"
                  className="text-xs"
                />
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsStatusModalOpen(false)}
                disabled={statusMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant={user.is_active ? "destructive" : "primary"}
                size="sm"
                onClick={() => statusMutation.mutate()}
                disabled={statusMutation.isPending}
              >
                {statusMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                {user.is_active ? "Confirm Suspension" : "Confirm Activation"}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}
    </div>
  );
}
