"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck,
  UserPlus,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ExternalLink,
  Lock,
  UserX,
  UserCheck,
  Shield,
  ArrowLeft,
  Mail,
  Users,
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

export default function ControlAdminsPage() {
  const queryClient = useQueryClient();

  // Invite modal state
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Status & Demote modals
  const [statusModalAdmin, setStatusModalAdmin] = useState<UserDirectoryItem | null>(null);
  const [statusReason, setStatusReason] = useState("");
  const [statusError, setStatusError] = useState<string | null>(null);

  const [demoteModalAdmin, setDemoteModalAdmin] = useState<UserDirectoryItem | null>(null);
  const [demoteError, setDemoteError] = useState<string | null>(null);

  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [page, setPage] = useState(1);
  const perPage = 15;

  // Query all users holding ADMIN role with pagination
  const { data: adminData, isLoading: isLoadingAdmins } = useQuery({
    queryKey: ["control-admins-directory", page, perPage],
    queryFn: () => usersApi.listUsers({ role: "ADMIN", page, per_page: perPage }),
  });

  // Query super admins as well to show full governance roster
  const { data: superAdminData, isLoading: isLoadingSuperAdmins } = useQuery({
    queryKey: ["control-super-admins-directory", page, perPage],
    queryFn: () => usersApi.listUsers({ role: "SUPER_ADMIN", page, per_page: perPage }),
  });

  const isLoading = isLoadingAdmins || isLoadingSuperAdmins;

  // Merge administrators and super administrators (deduplicated)
  const allAdminsMap = new Map<string, UserDirectoryItem>();
  superAdminData?.items?.forEach((u) => allAdminsMap.set(u.id, u));
  adminData?.items?.forEach((u) => allAdminsMap.set(u.id, u));
  const adminRoster = Array.from(allAdminsMap.values());

  const totalCount = (adminData?.total ?? 0) + (superAdminData?.total ?? 0);
  const totalPages = Math.max(adminData?.total_pages ?? 1, superAdminData?.total_pages ?? 1);

  // Invite Admin Mutation (Strictly requires Super Admin caller on backend)
  const inviteAdminMutation = useMutation({
    mutationFn: () =>
      usersApi.inviteStaff({
        email: email.trim(),
        full_name: fullName.trim(),
        role: "ADMIN",
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["control-admins-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setIsInviteModalOpen(false);
      setEmail("");
      setFullName("");
      setInviteError(null);
      setFeedback({
        type: "success",
        text: `Administrator invitation staged successfully for ${res.email}! 48h onboarding token generated.`,
      });
      setTimeout(() => setFeedback(null), 6000);
    },
    onError: (err: any) => {
      setInviteError(err?.message || "Failed to invite administrator.");
    },
  });

  // Status toggle mutation
  const statusMutation = useMutation({
    mutationFn: () => {
      if (!statusModalAdmin) throw new Error("No admin selected");
      return usersApi.updateStatus(statusModalAdmin.id, {
        is_active: !statusModalAdmin.is_active,
        reason: statusReason.trim() || undefined,
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-admins-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-super-admins-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setStatusModalAdmin(null);
      setStatusReason("");
      setStatusError(null);
      setFeedback({
        type: "success",
        text: `Administrator account for ${updated.full_name} is now ${updated.is_active ? "Active" : "Suspended"}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setStatusError(err?.message || "Failed to update administrator status.");
    },
  });

  // Demote Admin mutation (Revoke ADMIN role)
  const demoteMutation = useMutation({
    mutationFn: () => {
      if (!demoteModalAdmin) throw new Error("No admin selected");
      return usersApi.manageRole(demoteModalAdmin.id, {
        role_id: "ADMIN",
        action: "REVOKE",
      });
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["control-admins-directory"] });
      queryClient.invalidateQueries({ queryKey: ["control-users-directory"] });
      setDemoteModalAdmin(null);
      setDemoteError(null);
      setFeedback({
        type: "success",
        text: `Successfully revoked Administrator role from ${updated.full_name}.`,
      });
      setTimeout(() => setFeedback(null), 5000);
    },
    onError: (err: any) => {
      setDemoteError(err?.message || "Failed to revoke administrator role.");
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
            <ShieldCheck className="h-6 w-6 text-amber-600" />
            Administrator Management Hub
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Privileged platform administrators with delegated course, curriculum, and operational authority.
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
          Invite Administrator
        </Button>
      </div>

      {/* Invariant Banner */}
      <div className="rounded-[16px] border border-amber-200 bg-amber-50/70 p-4 text-xs text-amber-900 space-y-1">
        <div className="font-bold flex items-center gap-1.5 text-amber-800">
          <Lock className="h-4 w-4 text-amber-700" />
          Platform Governance & Sole Super Admin Protection Invariant
        </div>
        <p className="text-amber-800/90 leading-relaxed">
          Only verified Super Administrators can invite new Administrators. The platform owner (Super Admin) possesses
          unbreakable database serialization protections: under no circumstances may the final active Super Admin be
          suspended or demoted.
        </p>
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

      {/* Administrator Roster Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !adminRoster.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <ShieldAlert className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No administrators enrolled yet</p>
            <p className="text-xs text-slate-500">Send an invitation to onboard your first administrator.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Administrator</th>
                  <th scope="col" className="px-6 py-4">Governance Role</th>
                  <th scope="col" className="px-6 py-4">Account Status</th>
                  <th scope="col" className="px-6 py-4">Onboarded Date</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {adminRoster.map((user) => {
                  const isSuperAdmin = user.roles.includes("SUPER_ADMIN");
                  return (
                    <tr key={user.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-xs shrink-0">
                            {user.full_name?.charAt(0)?.toUpperCase() || "A"}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                              {user.full_name}
                              {isSuperAdmin && (
                                <span title="Protected Platform Owner">
                                  <Lock className="h-3.5 w-3.5 text-rose-600" />
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-slate-500">{user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((r) => (
                            <Badge
                              key={r}
                              variant={r === "SUPER_ADMIN" ? "error" : "warning"}
                              className="text-[11px]"
                            >
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

                          {!isSuperAdmin && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-8 px-2 text-xs text-amber-700 hover:text-amber-800"
                              onClick={() => {
                                setDemoteError(null);
                                setDemoteModalAdmin(user);
                              }}
                            >
                              <Shield className="h-3.5 w-3.5 mr-1" />
                              Demote
                            </Button>
                          )}

                          <Button
                            variant={user.is_active ? "outline" : "primary"}
                            size="sm"
                            className="h-8 px-2 text-xs"
                            onClick={() => {
                              setStatusError(null);
                              setStatusReason("");
                              setStatusModalAdmin(user);
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
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3 bg-slate-50">
            <div className="text-xs text-slate-500">
              Showing page <span className="font-semibold text-slate-700">{page}</span> of{" "}
              <span className="font-semibold text-slate-700">{totalPages}</span> ({totalCount} total administrators)
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
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="h-8 px-2 text-xs"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-0.5" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Invite Administrator Modal */}
      {isInviteModalOpen && (
        <Modal open={true} onOpenChange={(open) => !open && setIsInviteModalOpen(false)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Invite Administrator</ModalTitle>
              <ModalDescription>
                Issue a secure 48-hour onboarding invitation with full administrative delegation rights.
              </ModalDescription>
            </ModalHeader>

            {inviteError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{inviteError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              <div className="rounded-lg bg-slate-50 p-3 text-slate-700 border border-slate-100">
                <strong>Administrative Capabilities:</strong> Administrators can manage courses, reorder curriculum,
                inspect all student records, grant enrollments, and process order reconciliations.
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Administrator Full Name:</label>
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Eleanor Vance"
                  className="text-xs"
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Email Address:</label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. eleanor@example.com"
                  className="text-xs"
                />
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsInviteModalOpen(false)}
                disabled={inviteAdminMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => inviteAdminMutation.mutate()}
                disabled={inviteAdminMutation.isPending || !email.trim() || !fullName.trim()}
              >
                {inviteAdminMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                Dispatch Admin Invitation
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}

      {/* Demote Administrator Modal */}
      {demoteModalAdmin && (
        <Modal open={true} onOpenChange={(open) => !open && setDemoteModalAdmin(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>Revoke Administrator Privileges</ModalTitle>
              <ModalDescription>
                Are you sure you want to revoke the Administrator role from {demoteModalAdmin.full_name}?
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
                Revoking this role will immediately remove all administrative capabilities from this account upon next
                session verification. The user account itself and student records will remain preserved.
              </p>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDemoteModalAdmin(null)}
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
      {statusModalAdmin && (
        <Modal open={true} onOpenChange={(open) => !open && setStatusModalAdmin(null)}>
          <ModalContent>
            <ModalHeader>
              <ModalTitle>
                {statusModalAdmin.is_active ? "Suspend Administrator" : "Activate Administrator"}:{" "}
                {statusModalAdmin.full_name}
              </ModalTitle>
              <ModalDescription>
                {statusModalAdmin.is_active
                  ? "Suspending this administrator immediately revokes all active sessions across all devices."
                  : "Activating this account restores administrative login capabilities."}
              </ModalDescription>
            </ModalHeader>

            {statusError && (
              <div className="rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-red-600" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="space-y-3 text-xs">
              {statusModalAdmin.is_active && (
                <div className="rounded-lg bg-red-50 p-3 text-red-800 border border-red-200 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-600 mt-0.5" />
                  <div>
                    <strong>Immediate Session Displacement:</strong> The administrator will be immediately logged out.
                  </div>
                </div>
              )}

              {statusModalAdmin.roles.includes("SUPER_ADMIN") && statusModalAdmin.is_active && (
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
                  placeholder="e.g., Requested access rotation, leave of absence…"
                  className="text-xs"
                />
              </div>
            </div>

            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStatusModalAdmin(null)}
                disabled={statusMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant={statusModalAdmin.is_active ? "destructive" : "primary"}
                size="sm"
                onClick={() => statusMutation.mutate()}
                disabled={statusMutation.isPending}
              >
                {statusMutation.isPending && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                {statusModalAdmin.is_active ? "Confirm Suspension" : "Confirm Activation"}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      )}
    </div>
  );
}
