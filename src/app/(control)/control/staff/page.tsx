"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  UserPlus,
  Mail,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Check,
  ExternalLink,
  UserX,
  UserCheck,
  Shield,
  ArrowLeft,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { usersApi } from "@/lib/api/users";
import { UserDirectoryItem } from "@/types/user";
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

export default function ControlStaffPage() {
  const queryClient = useQueryClient();

  // Invite modal state
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("STAFF");
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Status & Demote modals
  const [statusModalStaff, setStatusModalStaff] = useState<UserDirectoryItem | null>(null);
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);

  const [demoteModalStaff, setDemoteModalStaff] = useState<UserDirectoryItem | null>(null);
  const [demoteError, setDemoteError] = useState<string | null>(null);

  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [page, setPage] = useState(1);
  const perPage = 15;

  const { data: staffData, isLoading } = useQuery({
    queryKey: ["control-staff-directory", page, perPage],
    queryFn: () => usersApi.listUsers({ role: "STAFF", page, per_page: perPage }),
  });

  const inviteMutation = useMutation({
    mutationFn: () =>
      usersApi.inviteStaff({
        email: email.trim(),
        full_name: fullName.trim(),
        role,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["control-staff-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setIsInviteModalOpen(false);
      setEmail("");
      setFullName("");
      setInviteError(null);
      setInviteSuccess(`Invitation token generated and sent to ${res.email}!`);
      setTimeout(() => setInviteSuccess(null), 5000);
    },
    onError: (err: any) => {
      setInviteError(err?.message || "Failed to invite staff member.");
    },
  });

  // Status toggle mutation
  const statusMutation = useMutation({
    mutationFn: () => {
      if (!statusModalStaff) throw new Error("No staff member selected");
      return usersApi.updateStatus(statusModalStaff.id, {
        is_active: !statusModalStaff.is_active,
        reason: statusReason.trim() || undefined,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-staff-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setStatusModalStaff(null);
      setStatusReason("");
      setStatusError(null);
      setFeedback({
        type: "success",
        text: `Staff account for ${updated.full_name} is now ${updated.is_active ? "Active" : "Suspended"}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setStatusError(err?.message || "Failed to update staff status.");
    },
  });

  // Demote Staff mutation (Revoke STAFF role)
  const demoteMutation = useMutation({
    mutationFn: () => {
      if (!demoteModalStaff) throw new Error("No staff member selected");
      return usersApi.manageRole(demoteModalStaff.id, {
        role_id: "STAFF",
        action: "REVOKE",
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-staff-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setDemoteModalStaff(null);
      setDemoteError(null);
      setFeedback({
        type: "success",
        text: `Successfully revoked Staff role from ${updated.full_name}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setDemoteError(err?.message || "Failed to revoke staff role.");
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/control/users"
              className="text-xs font-semibold text-slate-500 hover:text-slate-900 inline-flex items-center gap-1"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              User Directory
            </Link>
          </div>
          <h1 className="font-heading text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Users className="h-6 w-6 text-primary-teal" />
            Staff & Teaching Assistant Management
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage course grading assistants and co-instructors with scoped rubrics and evaluation permissions.
          </p>
        </div>
        <Button
          variant="primary"
          size="default"
          onClick={() => {
            setInviteError(null);
            setIsInviteModalOpen(true);
          }}
        >
          <UserPlus className="h-4 w-4 mr-2" />
          Invite Staff Member
        </Button>
      </div>

      {inviteSuccess && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          <span>{inviteSuccess}</span>
        </div>
      )}

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

      {/* Directory Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !staffData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <Users className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No staff members enrolled yet</p>
            <p className="text-xs text-slate-500">Send an invitation to onboard your first teaching assistant.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Staff Member</th>
                  <th scope="col" className="px-6 py-4">Assigned Roles</th>
                  <th scope="col" className="px-6 py-4">Account Status</th>
                  <th scope="col" className="px-6 py-4">Onboarded Date</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {staffData.items.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">{user.full_name}</div>
                      <div className="text-xs text-slate-500">{user.email}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {user.roles?.map((r) => (
                          <Badge key={r} variant="outline" className="text-[11px]">
                            {r}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={user.is_active ? "success" : "error"}>
                        {user.is_active ? "Active" : "Suspended"}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <Link href={`/control/users/${user.id}`}>
                          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs">
                            <ExternalLink className="h-3.5 w-3.5 mr-1" />
                            Profile
                          </Button>
                        </Link>

                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 px-2 text-xs text-amber-700 hover:text-amber-800"
                          onClick={() => {
                            setDemoteError(null);
                            setDemoteModalStaff(user);
                          }}
                        >
                          <Shield className="h-3.5 w-3.5 mr-1" />
                          Demote
                        </Button>

                        <Button
                          variant={user.is_active ? "outline" : "primary"}
                          size="sm"
                          className="h-8 px-2 text-xs"
                          onClick={() => {
                            setStatusError(null);
                            setStatusReason("");
                            setStatusModalStaff(user);
                          }}
                        >
                          {user.is_active ? (
                            <UserX className="h-3.5 w-3.5 mr-1 text-red-500" />
                          ) : (
                            <UserCheck className="h-3.5 w-3.5 mr-1 text-teal-600" />
                          )}
                          {user.is_active ? "Suspend" : "Activate"}
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
        {staffData && staffData.total_pages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3 bg-slate-50">
            <div className="text-xs text-slate-500">
              Showing page <span className="font-semibold text-slate-700">{staffData.page}</span> of{" "}
              <span className="font-semibold text-slate-700">{staffData.total_pages}</span> ({staffData.total} total staff members)
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="h-8 px-2 text-xs"
              >
                <ChevronLeft className="h-4 w-4 mr-0.5" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= staffData.total_pages}
                onClick={() => setPage((p) => Math.min(staffData.total_pages, p + 1))}
                className="h-8 px-2 text-xs"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-0.5" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Invite Modal */}
      {isInviteModalOpen && (
        <Modal open={true} onOpenChange={(open) => !open && setIsInviteModalOpen(false)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Invite Staff Member</ModalTitle>
              <ModalDescription>
                Send an onboarding invitation token (48h TTL) to onboard a teaching assistant or grader.
              </ModalDescription>
            </ModalHeader>

            {inviteError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{inviteError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Full Name:</label>
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. John Doe"
                  className="text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Email Address:</label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. j.doe@example.com"
                  className="text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Role Designation:</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="STAFF">STAFF — Teaching Assistant & Grader</option>
                  <option value="ADMIN">ADMIN — Platform Administrator</option>
                </select>
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsInviteModalOpen(false)}
                disabled={inviteMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => inviteMutation.mutate()}
                disabled={inviteMutation.isPending || !email.trim() || !fullName.trim()}
              >
                {inviteMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Dispatch Invitation
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}

      {/* Demote Staff Modal */}
      {demoteModalStaff && (
        <Modal open={true} onOpenChange={(open) => !open && setDemoteModalStaff(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Revoke Staff Role</ModalTitle>
              <ModalDescription>
                Are you sure you want to revoke the Staff role from {demoteModalStaff.full_name}?
              </ModalDescription>
            </ModalHeader>

            {demoteError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{demoteError}</span>
              </div>
            )}

            <div className="text-xs text-slate-600 space-y-2">
              <p>
                Revoking this role will remove all teaching assistant and grading privileges upon next session verification.
                The account and student learning history remain preserved.
              </p>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDemoteModalStaff(null)}
                disabled={demoteMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => demoteMutation.mutate()}
                disabled={demoteMutation.isPending}
              >
                {demoteMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Confirm Demotion
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}

      {/* Account Status Toggle Modal */}
      {statusModalStaff && (
        <Modal open={true} onOpenChange={(open) => !open && setStatusModalStaff(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>
                {statusModalStaff.is_active ? "Suspend Staff Account" : "Activate Staff Account"}:{" "}
                {statusModalStaff.full_name}
              </ModalTitle>
              <ModalDescription>
                {statusModalStaff.is_active
                  ? "Suspending this staff member immediately revokes all active sessions across all devices."
                  : "Activating this account restores staff portal access."}
              </ModalDescription>
            </ModalHeader>

            {statusError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              {statusModalStaff.is_active && (
                <div className="rounded-lg bg-red-50 p-3 text-red-800 border border-red-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
                  <div>
                    <strong>Immediate Session Displacement:</strong> The staff member will be immediately logged out.
                  </div>
                </div>
              )}

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-700">Audit Justification / Reason (Optional):</label>
                <Input
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  placeholder="e.g., Semester end, role rotation…"
                  className="text-xs"
                />
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStatusModalStaff(null)}
                disabled={statusMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant={statusModalStaff.is_active ? "destructive" : "primary"}
                size="sm"
                onClick={() => statusMutation.mutate()}
                disabled={statusMutation.isPending}
              >
                {statusMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                {statusModalStaff.is_active ? "Confirm Suspension" : "Confirm Activation"}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}
    </div>
  );
}
