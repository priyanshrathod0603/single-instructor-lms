"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  Search,
  ShieldCheck,
  UserX,
  UserCheck,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ArrowLeft,
} from "lucide-react";
import { usersApi } from "@/lib/api/users";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function AdminStudentsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [page, setPage] = useState(1);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-users", search, roleFilter, page],
    queryFn: () =>
      usersApi.listUsers({
        search: search || undefined,
        role: roleFilter || undefined,
        page,
        per_page: 20,
      }),
  });

  const toggleStatusMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      usersApi.updateStatus(userId, {
        is_active: isActive,
        reason: isActive ? "Administrative reactivation" : "Administrative suspension",
      }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setActionMessage(
        `User ${updated.full_name} status updated to ${updated.is_active ? "ACTIVE" : "SUSPENDED"}.`
      );
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
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Student Roster & User Governance
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Inspect student directory, view role assignments, and manage account activation status.
        </p>
      </div>

      {actionMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-center gap-4 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        <div className="relative flex-1 w-full">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search students by name or email..."
            className="pl-10"
          />
        </div>

        <select
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal/20 w-full sm:w-auto"
        >
          <option value="">All System Roles</option>
          <option value="STUDENT">Students</option>
          <option value="STAFF">Staff & Teaching Assistants</option>
          <option value="ADMIN">Administrators</option>
        </select>
      </div>

      {/* Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !data?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <Users className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No users found</p>
            <p className="text-xs text-slate-500">Try adjusting your search criteria or role filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Student Profile</th>
                  <th scope="col" className="px-6 py-4">System Roles</th>
                  <th scope="col" className="px-6 py-4">Account Status</th>
                  <th scope="col" className="px-6 py-4">Registered Date</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((user) => (
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
                      <Badge variant={user.is_active ? "success" : "outline"}>
                        {user.is_active ? "Active" : "Suspended"}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {user.is_active ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          isLoading={toggleStatusMutation.isPending}
                          onClick={() => {
                            if (window.confirm(`Suspend account for ${user.full_name}?`)) {
                              toggleStatusMutation.mutate({ userId: user.id, isActive: false });
                            }
                          }}
                          className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        >
                          <UserX className="h-3.5 w-3.5 mr-1" />
                          Suspend
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          isLoading={toggleStatusMutation.isPending}
                          onClick={() => {
                            if (window.confirm(`Reactivate account for ${user.full_name}?`)) {
                              toggleStatusMutation.mutate({ userId: user.id, isActive: true });
                            }
                          }}
                          className="text-teal-600 hover:bg-teal-50 hover:text-teal-700"
                        >
                          <UserCheck className="h-3.5 w-3.5 mr-1" />
                          Activate
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
    </div>
  );
}
