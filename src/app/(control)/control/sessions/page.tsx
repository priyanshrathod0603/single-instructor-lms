"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ShieldAlert,
  ShieldCheck,
  KeyRound,
  Search,
  RotateCcw,
  AlertTriangle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Laptop,
  Smartphone,
  Globe,
  Clock,
  User,
  Users,
  UserX,
  X,
  CheckCircle2,
  FileText,
  Activity,
  LogOut,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import {
  SessionItem,
  SessionDetailResponse,
  DetailedSecurityMetricsData,
} from "@/types/control";
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

function parseUserAgent(ua?: string | null): {
  browser: string;
  os: string;
  isMobile: boolean;
} {
  if (!ua) return { browser: "Unknown Browser", os: "Unknown OS", isMobile: false };
  let browser = "Unknown Browser";
  let os = "Unknown OS";
  const isMobile = /Mobile|Android|iPhone|iPad/i.test(ua);

  if (/Firefox\/([0-9.]+)/i.test(ua)) browser = "Firefox";
  else if (/Edg\/([0-9.]+)/i.test(ua)) browser = "Edge";
  else if (/Chrome\/([0-9.]+)/i.test(ua)) browser = "Chrome";
  else if (/Safari\/([0-9.]+)/i.test(ua)) browser = "Safari";
  else if (/curl|Postman|python|httpx/i.test(ua)) browser = "API Client";

  if (/Windows/i.test(ua)) os = "Windows";
  else if (/Macintosh|Mac OS X/i.test(ua)) os = "macOS";
  else if (/Android/i.test(ua)) os = "Android";
  else if (/iPhone|iPad/i.test(ua)) os = "iOS";
  else if (/Linux/i.test(ua)) os = "Linux";

  return { browser, os, isMobile };
}

function maskIpAddress(ip?: string | null): string {
  if (!ip) return "Unknown";
  if (ip === "127.0.0.1" || ip === "::1" || ip === "localhost") return ip;
  const parts = ip.split(".");
  if (parts.length === 4) {
    return `${parts[0]}.${parts[1]}.***.***`;
  }
  if (ip.includes(":")) {
    const v6Parts = ip.split(":");
    return `${v6Parts[0]}:****:****:${v6Parts[v6Parts.length - 1]}`;
  }
  return ip.slice(0, 4) + "***";
}

export default function SecuritySessionsPage() {
  const queryClient = useQueryClient();

  // Filter & Pagination States
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [ipFilter, setIpFilter] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 15;

  // IP Unmasking State (set of session IDs with unmasked IPs)
  const [revealedIps, setRevealedIps] = useState<Record<string, boolean>>({});

  const toggleIpReveal = (id: string) => {
    setRevealedIps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Modals & Action States
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionToRevoke, setSessionToRevoke] = useState<SessionItem | null>(null);
  const [revokeReason, setRevokeReason] = useState("");

  const [userToRevoke, setUserToRevoke] = useState<{ id: string; name: string } | null>(null);
  const [userRevokeReason, setUserRevokeReason] = useState("");

  const [emergencyModalOpen, setEmergencyModalOpen] = useState(false);
  const [emergencyReason, setEmergencyReason] = useState("");
  const [emergencyConfirmed, setEmergencyConfirmed] = useState(false);

  // 1. Fetch Security Metrics
  const {
    data: metrics,
    isLoading: metricsLoading,
    error: metricsError,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ["control-security-metrics"],
    queryFn: () => controlApi.getSecurityMetrics(),
    refetchInterval: 30000,
  });

  // 2. Fetch Sessions List
  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    error: sessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: [
      "control-sessions",
      statusFilter,
      roleFilter,
      searchTerm,
      ipFilter,
      page,
      perPage,
    ],
    queryFn: () =>
      controlApi.listSessions({
        status: statusFilter === "ALL" ? undefined : statusFilter,
        role: roleFilter === "ALL" ? undefined : roleFilter,
        search: searchTerm.trim() || undefined,
        ip_address: ipFilter.trim() || undefined,
        page,
        per_page: perPage,
        sort_by: "created_at",
        sort_order: "desc",
      }),
  });

  // 3. Fetch Single Session Detail (for Inspect Modal)
  const {
    data: sessionDetail,
    isLoading: detailLoading,
    refetch: refetchSessionDetail,
  } = useQuery({
    queryKey: ["control-session-detail", selectedSessionId],
    queryFn: () =>
      selectedSessionId ? controlApi.getSession(selectedSessionId) : null,
    enabled: !!selectedSessionId,
  });

  // Mutations
  const revokeSessionMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      controlApi.revokeSession(id, { reason }),
    onSuccess: () => {
      toast.success("Session revoked successfully.");
      setSessionToRevoke(null);
      setRevokeReason("");
      queryClient.invalidateQueries({ queryKey: ["control-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["control-security-metrics"] });
      if (selectedSessionId) {
        refetchSessionDetail();
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || "Failed to revoke session.");
    },
  });

  const revokeUserSessionsMutation = useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      controlApi.revokeUserSessions(userId, { reason }),
    onSuccess: (res) => {
      toast.success(
        `Revoked ${res.revoked_sessions_count} active session(s) for user.`
      );
      setUserToRevoke(null);
      setUserRevokeReason("");
      queryClient.invalidateQueries({ queryKey: ["control-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["control-security-metrics"] });
      if (selectedSessionId) {
        setSelectedSessionId(null);
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || "Failed to revoke user sessions.");
    },
  });

  const emergencyRevocationMutation = useMutation({
    mutationFn: ({ reason }: { reason: string }) =>
      controlApi.revokeOtherSessions({ reason }),
    onSuccess: (res) => {
      toast.success(
        `Emergency containment executed: ${res.revoked_sessions_count} sessions revoked. Your session was preserved.`
      );
      setEmergencyModalOpen(false);
      setEmergencyReason("");
      setEmergencyConfirmed(false);
      queryClient.invalidateQueries({ queryKey: ["control-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["control-security-metrics"] });
      if (selectedSessionId) {
        setSelectedSessionId(null);
      }
    },
    onError: (err: any) => {
      toast.error(err?.message || "Failed to execute emergency revocation.");
    },
  });

  const handleClearFilters = () => {
    setSearchTerm("");
    setStatusFilter("ALL");
    setRoleFilter("ALL");
    setIpFilter("");
    setPage(1);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "ACTIVE":
        return <Badge variant="success">Active</Badge>;
      case "REVOKED":
        return <Badge variant="error">Revoked</Badge>;
      case "EXPIRED":
        return <Badge variant="outline">Expired</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getRoleBadge = (role?: string) => {
    switch (role) {
      case "SUPER_ADMIN":
        return <Badge variant="teal">Super Admin</Badge>;
      case "ADMIN":
        return <Badge variant="coral">Admin</Badge>;
      case "STAFF":
        return <Badge variant="peach">Staff</Badge>;
      case "STUDENT":
        return <Badge variant="mint">Student</Badge>;
      default:
        return <Badge variant="outline">{role || "User"}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <KeyRound className="h-6 w-6 text-primary-teal" />
            <h1 className="font-heading text-2xl font-bold text-slate-900">
              Security Governance & Session Surveillance
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Real-time surveillance of authenticated user sessions, client device footprints, and centralized revocation controls.
          </p>
        </div>

        <Button
          variant="outline"
          onClick={() => setEmergencyModalOpen(true)}
          className="bg-rose-50 border-rose-300 text-rose-700 hover:bg-rose-100 hover:text-rose-800 font-semibold flex items-center gap-2 self-start sm:self-auto"
        >
          <ShieldAlert className="h-4 w-4 text-rose-600" />
          Emergency Revocation
        </Button>
      </div>

      {/* Security Metrics Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Active Sessions */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Active Sessions
            </span>
            <Activity className="h-4 w-4 text-emerald-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-20 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-slate-900 font-mono">
                {metrics?.active_sessions_total ?? 0}
              </span>
              <div className="flex flex-wrap gap-1 mt-2 text-[11px]">
                {metrics?.active_sessions_by_role &&
                  Object.entries(metrics.active_sessions_by_role).map(([r, count]) => (
                    <span
                      key={r}
                      className="px-1.5 py-0.5 rounded bg-slate-100 font-mono text-slate-600"
                    >
                      {r}: {count}
                    </span>
                  ))}
              </div>
            </div>
          )}
        </div>

        {/* Card 2: Revoked (24h) */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Revoked (24h)
            </span>
            <ShieldAlert className="h-4 w-4 text-rose-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-20 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-rose-600 font-mono">
                {metrics?.sessions_revoked_24h ?? 0}
              </span>
              <p className="text-xs text-slate-400 mt-1">
                Admin & security revocations
              </p>
            </div>
          )}
        </div>

        {/* Card 3: Displaced (24h) */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Displaced (24h)
            </span>
            <RotateCcw className="h-4 w-4 text-amber-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-20 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-amber-600 font-mono">
                {metrics?.sessions_displaced_24h ?? 0}
              </span>
              <p className="text-xs text-slate-400 mt-1">
                Single-active-session policy
              </p>
            </div>
          )}
        </div>

        {/* Card 4: Suspended Accounts */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Suspended Accounts
            </span>
            <UserX className="h-4 w-4 text-slate-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-20 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-slate-800 font-mono">
                {metrics?.suspended_accounts_total ?? 0}
              </span>
              <p className="text-xs text-slate-400 mt-1">
                Platform access restricted
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Multi-Attribute Filter Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        {/* Search */}
        <div className="relative md:col-span-2">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            placeholder="Search by user name or email..."
            className="pl-10"
          />
        </div>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
        >
          <option value="ALL">All Statuses</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="REVOKED">REVOKED</option>
          <option value="EXPIRED">EXPIRED</option>
        </select>

        {/* Role Filter */}
        <select
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
        >
          <option value="ALL">All Roles</option>
          <option value="STUDENT">STUDENT</option>
          <option value="STAFF">STAFF</option>
          <option value="ADMIN">ADMIN</option>
          <option value="SUPER_ADMIN">SUPER_ADMIN</option>
        </select>

        {/* IP Address Filter */}
        <div className="flex gap-2">
          <Input
            value={ipFilter}
            onChange={(e) => {
              setIpFilter(e.target.value);
              setPage(1);
            }}
            placeholder="Filter IP..."
            className="text-xs"
          />
          {(searchTerm || statusFilter !== "ALL" || roleFilter !== "ALL" || ipFilter) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClearFilters}
              title="Clear filters"
              className="px-2 text-slate-500 hover:text-slate-800"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Sessions Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {sessionsLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : sessionsError ? (
          <div className="p-12 text-center text-rose-500 space-y-3">
            <AlertTriangle className="h-8 w-8 mx-auto" />
            <p className="text-sm font-semibold">Failed to load platform sessions</p>
            <Button variant="outline" size="sm" onClick={() => refetchSessions()}>
              Retry
            </Button>
          </div>
        ) : !sessionsData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <ShieldCheck className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">
              No sessions match your filter criteria
            </p>
            <p className="text-xs text-slate-500">
              Try adjusting your search, status, or role filters.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">User</th>
                  <th scope="col" className="px-6 py-4">Device & Client</th>
                  <th scope="col" className="px-6 py-4">IP Address</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Activity</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sessionsData.items.map((session) => {
                  const ua = parseUserAgent(session.user_agent);
                  const isRevealed = !!revealedIps[session.id];
                  const displayedIp = isRevealed
                    ? session.ip_address || "Unknown"
                    : maskIpAddress(session.ip_address);
                  const primaryRole = session.user?.roles?.[0] || "STUDENT";

                  return (
                    <tr
                      key={session.id}
                      className="hover:bg-slate-50/80 transition-colors"
                    >
                      {/* User Column */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600 font-semibold text-xs shrink-0">
                            {session.user?.full_name?.charAt(0) || "U"}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-900 truncate block max-w-[160px]">
                                {session.user?.full_name || "Unknown User"}
                              </span>
                              {getRoleBadge(primaryRole)}
                            </div>
                            <span className="text-xs text-slate-500 truncate block max-w-[180px]">
                              {session.user?.email || session.user_id}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Device & Client Column */}
                      <td className="px-6 py-4 text-xs">
                        <div className="flex items-center gap-2 text-slate-800">
                          {ua.isMobile ? (
                            <Smartphone className="h-4 w-4 text-slate-400 shrink-0" />
                          ) : (
                            <Laptop className="h-4 w-4 text-slate-400 shrink-0" />
                          )}
                          <span className="font-medium">
                            {ua.browser} on {ua.os}
                          </span>
                        </div>
                        <span
                          className="block text-[11px] text-slate-400 truncate max-w-[200px] mt-0.5"
                          title={session.user_agent || "No User-Agent"}
                        >
                          {session.user_agent || "Direct Client"}
                        </span>
                      </td>

                      {/* IP Address Column */}
                      <td className="px-6 py-4">
                        <div className="inline-flex items-center gap-2 bg-slate-50 px-2 py-1 rounded border border-slate-200">
                          <Globe className="h-3.5 w-3.5 text-slate-400" />
                          <span className="font-mono text-xs text-slate-700">
                            {displayedIp}
                          </span>
                          <button
                            type="button"
                            onClick={() => toggleIpReveal(session.id)}
                            className="text-slate-400 hover:text-slate-700 transition-colors ml-1"
                            title={isRevealed ? "Mask IP" : "Reveal full IP"}
                          >
                            {isRevealed ? (
                              <EyeOff className="h-3.5 w-3.5 text-primary-teal" />
                            ) : (
                              <Eye className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </td>

                      {/* Status Column */}
                      <td className="px-6 py-4">
                        <div className="space-y-1">
                          {getStatusBadge(session.status)}
                          {session.status === "REVOKED" && session.revocation_reason && (
                            <span
                              className="block text-[10px] text-rose-600 truncate max-w-[140px]"
                              title={session.revocation_reason}
                            >
                              {session.revocation_reason}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Timestamps Column */}
                      <td className="px-6 py-4 text-xs text-slate-500">
                        <div className="flex items-center gap-1 text-slate-700 font-medium">
                          <Clock className="h-3 w-3 text-slate-400" />
                          <span>
                            {new Date(session.last_active_at).toLocaleString([], {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                        <span className="block text-[11px] text-slate-400 mt-0.5">
                          Started:{" "}
                          {new Date(session.created_at).toLocaleDateString([], {
                            month: "short",
                            day: "numeric",
                          })}
                        </span>
                      </td>

                      {/* Actions Column */}
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelectedSessionId(session.id)}
                            className="text-xs text-primary-teal hover:bg-teal-50"
                          >
                            Inspect
                          </Button>

                          {session.status === "ACTIVE" ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSessionToRevoke(session);
                                setRevokeReason("");
                              }}
                              className="text-xs text-rose-600 border-rose-200 hover:bg-rose-50"
                            >
                              Revoke
                            </Button>
                          ) : null}

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setUserToRevoke({
                                id: session.user_id,
                                name: session.user?.full_name || session.user_id,
                              });
                              setUserRevokeReason("");
                            }}
                            title="Revoke all active sessions for this user"
                            className="text-xs text-slate-500 hover:text-rose-600 hover:bg-rose-50"
                          >
                            <UserX className="h-3.5 w-3.5" />
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

        {/* Pagination Bar */}
        {sessionsData && sessionsData.pages > 1 && (
          <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3">
            <span className="text-xs text-slate-500">
              Page {sessionsData.page} of {sessionsData.pages} ({sessionsData.total} total sessions)
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= sessionsData.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Modal 1: Session Details & Correlated Audit Events */}
      <Modal
        open={!!selectedSessionId}
        onOpenChange={(open) => !open && setSelectedSessionId(null)}
      >
        <ModalContent className="max-w-2xl">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-slate-900">
              <KeyRound className="h-5 w-5 text-primary-teal" />
              Session Surveillance Inspection
            </ModalTitle>
            <ModalDescription>
              Detailed cryptographic identifier, client footprint, and correlated security audit events.
            </ModalDescription>
          </ModalHeader>

          {detailLoading || !sessionDetail ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
            </div>
          ) : (
            <div className="space-y-6 text-sm">
              {/* Session Meta Card */}
              <div className="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-[12px] border border-slate-200">
                <div>
                  <span className="text-xs text-slate-500 block">Session ID</span>
                  <span className="font-mono text-xs font-semibold text-slate-900 block truncate" title={sessionDetail.id}>
                    {sessionDetail.id}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Status</span>
                  <div className="mt-0.5">{getStatusBadge(sessionDetail.status)}</div>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">User Account</span>
                  <span className="font-semibold text-slate-800">
                    {sessionDetail.user?.full_name || "Unknown"}
                  </span>
                  <span className="text-xs text-slate-500 block">
                    {sessionDetail.user?.email}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Assigned Roles</span>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {sessionDetail.user?.roles?.map((r) => (
                      <span key={r} className="text-xs font-mono bg-white border border-slate-200 px-1.5 py-0.5 rounded">
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Client IP Address</span>
                  <span className="font-mono text-xs text-slate-800">
                    {sessionDetail.ip_address || "Unknown"}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Client User Agent</span>
                  <span className="font-mono text-xs text-slate-600 block truncate" title={sessionDetail.user_agent || ""}>
                    {sessionDetail.user_agent || "Direct Client"}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Created At</span>
                  <span className="text-xs text-slate-700">
                    {new Date(sessionDetail.created_at).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-slate-500 block">Last Active</span>
                  <span className="text-xs text-slate-700">
                    {new Date(sessionDetail.last_active_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Revocation Information (if revoked) */}
              {sessionDetail.status === "REVOKED" && (
                <div className="bg-rose-50 border border-rose-200 p-4 rounded-[12px] space-y-2">
                  <div className="flex items-center gap-2 text-rose-800 font-semibold text-xs">
                    <ShieldAlert className="h-4 w-4" />
                    Revocation Metadata
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-rose-600 block">Reason:</span>
                      <span className="font-medium text-rose-950 font-mono">
                        {sessionDetail.revocation_reason || "Unspecified"}
                      </span>
                    </div>
                    <div>
                      <span className="text-rose-600 block">Revoked At:</span>
                      <span className="text-rose-950">
                        {sessionDetail.revoked_at
                          ? new Date(sessionDetail.revoked_at).toLocaleString()
                          : "N/A"}
                      </span>
                    </div>
                    {sessionDetail.revoked_by && (
                      <div className="col-span-2">
                        <span className="text-rose-600 block">Revoked By (Actor ID):</span>
                        <span className="font-mono text-xs text-rose-950">
                          {sessionDetail.revoked_by}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Correlated Audit Events */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                  <FileText className="h-4 w-4 text-slate-400" />
                  Correlated Security Audit Events ({sessionDetail.correlated_events?.length || 0})
                </h3>

                {!sessionDetail.correlated_events?.length ? (
                  <p className="text-xs text-slate-400 italic bg-slate-50 p-3 rounded-[8px] border border-slate-100">
                    No correlated audit records linked to this session ID.
                  </p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {sessionDetail.correlated_events.map((event) => (
                      <div
                        key={event.id}
                        className="bg-slate-50 p-2.5 rounded-[8px] border border-slate-200 text-xs flex items-center justify-between"
                      >
                        <div>
                          <span className="font-mono font-bold text-slate-800 bg-slate-200 px-1.5 py-0.5 rounded text-[11px]">
                            {event.action}
                          </span>
                          <span className="text-slate-500 ml-2">
                            IP: {event.ip_address || "N/A"}
                          </span>
                        </div>
                        <span className="text-slate-400 text-[11px]">
                          {new Date(event.created_at).toLocaleString([], {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <ModalFooter>
            {sessionDetail?.status === "ACTIVE" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSessionToRevoke(sessionDetail);
                  setRevokeReason("");
                }}
                className="bg-rose-50 text-rose-700 border-rose-300 hover:bg-rose-100 mr-auto"
              >
                Revoke This Session
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedSessionId(null)}
            >
              Close
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Modal 2: Single Session Revocation Dialog */}
      <Modal
        open={!!sessionToRevoke}
        onOpenChange={(open) => !open && setSessionToRevoke(null)}
      >
        <ModalContent>
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-rose-700">
              <ShieldAlert className="h-5 w-5" />
              Revoke Authentication Session
            </ModalTitle>
            <ModalDescription>
              Immediately invalidate this active session token. The user will be redirected to login upon their next action.
            </ModalDescription>
          </ModalHeader>

          <div className="space-y-4 py-2">
            <div className="bg-slate-50 p-3 rounded-[8px] border border-slate-200 text-xs space-y-1">
              <div>
                <span className="text-slate-500">Target User: </span>
                <span className="font-semibold text-slate-800">
                  {sessionToRevoke?.user?.full_name || sessionToRevoke?.user_id}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Session ID: </span>
                <span className="font-mono text-slate-700">{sessionToRevoke?.id}</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Revocation Justification (Required, min 5 characters)
              </label>
              <Input
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                placeholder="e.g. Suspicious concurrent access observed from anomalous geolocation"
                className="text-xs"
              />
              {revokeReason.trim().length > 0 && revokeReason.trim().length < 5 && (
                <p className="text-[11px] text-rose-500 mt-1">
                  Justification must be at least 5 characters long.
                </p>
              )}
            </div>
          </div>

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSessionToRevoke(null)}
              disabled={revokeSessionMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={
                revokeReason.trim().length < 5 || revokeSessionMutation.isPending
              }
              onClick={() => {
                if (sessionToRevoke) {
                  revokeSessionMutation.mutate({
                    id: sessionToRevoke.id,
                    reason: revokeReason.trim(),
                  });
                }
              }}
              className="bg-rose-600 hover:bg-rose-700 text-white"
            >
              {revokeSessionMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                  Revoking...
                </>
              ) : (
                "Confirm Revocation"
              )}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Modal 3: Revoke All User Sessions Dialog */}
      <Modal
        open={!!userToRevoke}
        onOpenChange={(open) => !open && setUserToRevoke(null)}
      >
        <ModalContent>
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-rose-700">
              <UserX className="h-5 w-5" />
              Revoke All Sessions for User
            </ModalTitle>
            <ModalDescription>
              Terminate ALL active sessions for this user across every browser and device.
            </ModalDescription>
          </ModalHeader>

          <div className="space-y-4 py-2">
            <div className="bg-rose-50 border border-rose-200 p-3 rounded-[8px] text-xs text-rose-900 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <strong>Warning:</strong> Target user{" "}
                <strong>{userToRevoke?.name}</strong> will be immediately logged out of all active devices.
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Revocation Justification (Required, min 5 characters)
              </label>
              <Input
                value={userRevokeReason}
                onChange={(e) => setUserRevokeReason(e.target.value)}
                placeholder="e.g. Account security audit or suspected credential compromise"
                className="text-xs"
              />
              {userRevokeReason.trim().length > 0 && userRevokeReason.trim().length < 5 && (
                <p className="text-[11px] text-rose-500 mt-1">
                  Justification must be at least 5 characters long.
                </p>
              )}
            </div>
          </div>

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setUserToRevoke(null)}
              disabled={revokeUserSessionsMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={
                userRevokeReason.trim().length < 5 ||
                revokeUserSessionsMutation.isPending
              }
              onClick={() => {
                if (userToRevoke) {
                  revokeUserSessionsMutation.mutate({
                    userId: userToRevoke.id,
                    reason: userRevokeReason.trim(),
                  });
                }
              }}
              className="bg-rose-600 hover:bg-rose-700 text-white"
            >
              {revokeUserSessionsMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                  Revoking...
                </>
              ) : (
                "Revoke All Sessions"
              )}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Modal 4: Emergency Platform Revocation Dialog (Emergency Containment) */}
      <Modal
        open={emergencyModalOpen}
        onOpenChange={(open) => !open && setEmergencyModalOpen(false)}
      >
        <ModalContent>
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-rose-700">
              <ShieldAlert className="h-6 w-6 text-rose-600" />
              Emergency Platform Containment
            </ModalTitle>
            <ModalDescription>
              Platform-wide security emergency intervention.
            </ModalDescription>
          </ModalHeader>

          <div className="space-y-4 py-2">
            <div className="bg-rose-50 border border-rose-300 p-4 rounded-[12px] space-y-2 text-xs text-rose-950">
              <div className="flex items-center gap-2 font-bold text-rose-800">
                <AlertTriangle className="h-5 w-5 text-rose-600" />
                CRITICAL EMERGENCY ACTION
              </div>
              <p>
                This operation will immediately terminate <strong>ALL active sessions</strong> across the entire LMS platform (Students, Staff, and Administrators).
              </p>
              <div className="p-2 bg-white/80 rounded border border-rose-200 text-rose-900 font-medium">
                ✓ <strong>Caller Session Preservation:</strong> Your current Super Admin session is automatically identified and protected by the server. You will remain logged in.
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Emergency Incident Justification (Required, min 5 characters)
              </label>
              <Input
                value={emergencyReason}
                onChange={(e) => setEmergencyReason(e.target.value)}
                placeholder="e.g. Critical platform credential leakage or active incident response"
                className="text-xs"
              />
              {emergencyReason.trim().length > 0 && emergencyReason.trim().length < 5 && (
                <p className="text-[11px] text-rose-500 mt-1">
                  Justification must be at least 5 characters long.
                </p>
              )}
            </div>

            <label className="flex items-start gap-2.5 cursor-pointer pt-2">
              <input
                type="checkbox"
                checked={emergencyConfirmed}
                onChange={(e) => setEmergencyConfirmed(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-rose-600 focus:ring-rose-500"
              />
              <span className="text-xs text-slate-700 leading-tight">
                I understand that this action forcefully terminates all active platform sessions.
              </span>
            </label>
          </div>

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEmergencyModalOpen(false)}
              disabled={emergencyRevocationMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={
                emergencyReason.trim().length < 5 ||
                !emergencyConfirmed ||
                emergencyRevocationMutation.isPending
              }
              onClick={() => {
                emergencyRevocationMutation.mutate({
                  reason: emergencyReason.trim(),
                });
              }}
              className="bg-rose-600 hover:bg-rose-700 text-white font-semibold"
            >
              {emergencyRevocationMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                  Executing Emergency Containment...
                </>
              ) : (
                "Execute Platform Containment"
              )}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
