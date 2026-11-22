"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Search,
  Clock,
  ShieldCheck,
  Loader2,
  X,
  Code,
  Terminal,
} from "lucide-react";
import { auditApi } from "@/lib/api/audit";
import { AuditLogResponse } from "@/types/audit";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function ControlAuditLogsPage() {
  const [actionFilter, setActionFilter] = useState("");
  const [resourceTypeFilter, setResourceTypeFilter] = useState("");
  const [ipFilter, setIpFilter] = useState("");
  const [page, setPage] = useState(1);
  const [selectedLog, setSelectedLog] = useState<AuditLogResponse | null>(null);

  const { data: auditData, isLoading } = useQuery({
    queryKey: ["control-audit-logs", actionFilter, resourceTypeFilter, ipFilter, page],
    queryFn: () =>
      auditApi.listAuditLogs({
        action: actionFilter.trim() ? actionFilter.trim().toUpperCase() : undefined,
        resource_type: resourceTypeFilter || undefined,
        ip_address: ipFilter.trim() || undefined,
        page,
        per_page: 25,
      }),
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Immutable Security Audit Trail
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Cryptographically immutable event log recording all sensitive system mutations and access events.
        </p>
      </div>

      {/* Filter Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(1);
            }}
            placeholder="Filter by action (e.g. AUTH_LOGIN, USER_LOGOUT)..."
            className="pl-10"
          />
        </div>

        <div className="relative">
          <Input
            value={ipFilter}
            onChange={(e) => {
              setIpFilter(e.target.value);
              setPage(1);
            }}
            placeholder="Filter by IP address (e.g. 192.168.1.1)..."
          />
        </div>

        <select
          value={resourceTypeFilter}
          onChange={(e) => {
            setResourceTypeFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
        >
          <option value="">All Resource Types</option>
          <option value="media_asset">media_asset</option>
          <option value="course">course</option>
          <option value="user">user</option>
          <option value="auth_session">auth_session</option>
          <option value="order">order</option>
          <option value="submission">submission</option>
        </select>
      </div>

      {/* Audit Log Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !auditData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <ShieldCheck className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No audit events match filters</p>
            <p className="text-xs text-slate-500">Security audit entries will appear here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Action Event</th>
                  <th scope="col" className="px-6 py-4">Actor</th>
                  <th scope="col" className="px-6 py-4">Resource Target</th>
                  <th scope="col" className="px-6 py-4">IP Address</th>
                  <th scope="col" className="px-6 py-4">Timestamp</th>
                  <th scope="col" className="px-6 py-4 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {auditData.items.map((log) => (
                  <tr
                    key={log.id}
                    onClick={() => setSelectedLog(log)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer"
                  >
                    <td className="px-6 py-3.5">
                      <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      <span className="font-semibold text-slate-800">{log.actor_type}</span>
                      {log.actor_id && (
                        <span className="block font-mono text-[11px] text-slate-400 truncate max-w-[120px]">
                          {log.actor_id}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-600">
                      <span className="font-medium text-slate-800">{log.resource_type}</span>
                      {log.resource_id && (
                        <span className="block font-mono text-[11px] text-slate-400 truncate max-w-[120px]">
                          {log.resource_id}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3.5 font-mono text-xs text-slate-500">
                      {log.ip_address || "127.0.0.1"}
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-500">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedLog(log);
                        }}
                        className="text-xs text-primary-teal hover:bg-teal-50"
                      >
                        <Code className="h-3.5 w-3.5 mr-1" />
                        Inspect
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* JSON State Diff Modal */}
      {selectedLog && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="audit-diff-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="relative w-full max-w-3xl max-h-[90vh] flex flex-col rounded-[16px] bg-slate-900 text-slate-100 shadow-2xl border border-slate-700 overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-950">
              <div className="flex items-center gap-3">
                <Terminal className="h-5 w-5 text-teal-400" />
                <h2 id="audit-diff-title" className="font-heading text-sm font-bold text-white">
                  Audit Record: {selectedLog.action}
                </h2>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="text-slate-400 hover:text-white min-h-[44px] min-w-[44px] flex items-center justify-center"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs font-mono">
              <div className="grid grid-cols-2 gap-4 pb-4 border-b border-slate-800 text-slate-300">
                <div>
                  <span className="text-slate-500 block">Event ID:</span>
                  <span>{selectedLog.id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">IP Address:</span>
                  <span>{selectedLog.ip_address || "None"}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Actor:</span>
                  <span>{selectedLog.actor_type} ({selectedLog.actor_id || "System"})</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Resource:</span>
                  <span>{selectedLog.resource_type} ({selectedLog.resource_id || "Global"})</span>
                </div>
              </div>

              {/* Before State */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 mb-1">
                  Before State Snapshot
                </h4>
                <pre className="rounded-lg bg-slate-950 p-4 border border-slate-800 overflow-x-auto text-amber-200/90">
                  {selectedLog.before_state
                    ? JSON.stringify(selectedLog.before_state, null, 2)
                    : "// Null before_state (Resource Created)"}
                </pre>
              </div>

              {/* After State */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-teal-400 mb-1">
                  After State Snapshot
                </h4>
                <pre className="rounded-lg bg-slate-950 p-4 border border-slate-800 overflow-x-auto text-teal-200/90">
                  {selectedLog.after_state
                    ? JSON.stringify(selectedLog.after_state, null, 2)
                    : "// Null after_state (Resource Deleted)"}
                </pre>
              </div>

              {/* Metadata */}
              {selectedLog.metadata && Object.keys(selectedLog.metadata).length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Request Metadata
                  </h4>
                  <pre className="rounded-lg bg-slate-950 p-4 border border-slate-800 overflow-x-auto text-slate-300">
                    {JSON.stringify(selectedLog.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-slate-800 px-6 py-3 bg-slate-950 flex justify-end">
              <Button variant="ghost" size="sm" onClick={() => setSelectedLog(null)} className="text-white hover:bg-slate-800">
                Close Inspector
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
