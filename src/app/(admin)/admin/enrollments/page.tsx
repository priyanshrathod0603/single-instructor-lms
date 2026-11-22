"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  GraduationCap,
  Plus,
  Trash2,
  XCircle,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Check,
  ArrowLeft,
} from "lucide-react";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { coursesApi } from "@/lib/api/courses";
import { usersApi } from "@/lib/api/users";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function AdminEnrollmentsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [isGrantModalOpen, setIsGrantModalOpen] = useState(false);

  // Form state for manual grant
  const [studentId, setStudentId] = useState("");
  const [courseId, setCourseId] = useState("");
  const [reason, setReason] = useState("Scholarship grant");
  const [grantError, setGrantError] = useState<string | null>(null);

  // Revoke state
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const { data: enrollmentsData, isLoading } = useQuery({
    queryKey: ["all-enrollments", statusFilter, page],
    queryFn: () =>
      enrollmentsApi.listAllEnrollments({
        status: statusFilter || undefined,
        page,
        per_page: 25,
      }),
  });

  const { data: coursesData } = useQuery({
    queryKey: ["manage-courses-picker"],
    queryFn: () => coursesApi.listManageCourses({ per_page: 50 }),
    enabled: isGrantModalOpen,
  });

  const grantMutation = useMutation({
    mutationFn: () =>
      enrollmentsApi.grantManualEnrollment({
        student_id: studentId.trim(),
        course_id: courseId.trim(),
        reason: reason.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-enrollments"] });
      setIsGrantModalOpen(false);
      setStudentId("");
      setCourseId("");
      setActionMessage("Manual enrollment successfully provisioned!");
      setTimeout(() => setActionMessage(null), 3000);
    },
    onError: (err: any) => {
      setGrantError(err?.message || "Failed to grant manual enrollment.");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      enrollmentsApi.revokeEnrollment(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-enrollments"] });
      setActionMessage("Enrollment successfully revoked.");
      setTimeout(() => setActionMessage(null), 3000);
    },
  });

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
            Student Enrollment Governance
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Audit student course access, grant manual scholarships, and revoke access.
          </p>
        </div>
        <Button
          variant="primary"
          size="default"
          onClick={() => {
            setGrantError(null);
            setIsGrantModalOpen(true);
          }}
        >
          <Plus className="h-4 w-4 mr-2" />
          Grant Manual Enrollment
        </Button>
      </div>

      {actionMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setStatusFilter("")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === ""
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          All Enrollments ({enrollmentsData?.total ?? 0})
        </button>
        <button
          onClick={() => setStatusFilter("ACTIVE")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === "ACTIVE"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Active
        </button>
        <button
          onClick={() => setStatusFilter("REVOKED")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === "REVOKED"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Revoked
        </button>
      </div>

      {/* Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !enrollmentsData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <GraduationCap className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No enrollments found</p>
            <p className="text-xs text-slate-500">Student access grants will appear here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Student & Course</th>
                  <th scope="col" className="px-6 py-4">Access Status</th>
                  <th scope="col" className="px-6 py-4">Granted Date</th>
                  <th scope="col" className="px-6 py-4">Revocation Details</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {enrollmentsData.items.map((enr) => (
                  <tr key={enr.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">
                        {enr.course_title || "Course Access"}
                      </div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5">
                        Student UUID: {enr.student_id}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={enr.status === "ACTIVE" ? "success" : "outline"}>
                        {enr.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(enr.granted_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {enr.revoked_at ? (
                        <div>
                          <span className="text-rose-600 font-medium">Revoked on {new Date(enr.revoked_at).toLocaleDateString()}</span>
                          {enr.revoked_reason && <p className="italic text-slate-400">{enr.revoked_reason}</p>}
                        </div>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {enr.status === "ACTIVE" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          isLoading={revokeMutation.isPending}
                          onClick={() => {
                            const inputReason = window.prompt("Reason for revoking course access:");
                            if (inputReason && inputReason.trim()) {
                              revokeMutation.mutate({ id: enr.id, reason: inputReason.trim() });
                            }
                          }}
                          className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        >
                          <XCircle className="h-3.5 w-3.5 mr-1" />
                          Revoke Access
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Manual Grant Modal */}
      {isGrantModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="manual-grant-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="relative w-full max-w-lg rounded-[16px] bg-white p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 id="manual-grant-title" className="font-heading text-lg font-bold text-slate-900">
                Grant Manual Course Enrollment
              </h2>
              <button
                onClick={() => setIsGrantModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 min-h-[44px] min-w-[44px] flex items-center justify-center"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {grantError && (
              <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 border border-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
                <span>{grantError}</span>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                grantMutation.mutate();
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Target Student UUID *
                </label>
                <Input
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value)}
                  placeholder="Paste student UUID (from Student Roster)"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Course Selection *
                </label>
                <select
                  value={courseId}
                  onChange={(e) => setCourseId(e.target.value)}
                  className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
                  required
                >
                  <option value="">Select course...</option>
                  {coursesData?.items?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title} (/{c.slug})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Grant Justification / Reason *
                </label>
                <Input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Scholarship award or corporate voucher"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                <Button variant="ghost" size="sm" onClick={() => setIsGrantModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={!studentId.trim() || !courseId.trim() || grantMutation.isPending}
                  isLoading={grantMutation.isPending}
                >
                  <Check className="h-4 w-4 mr-1.5" />
                  Confirm Grant
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
