"use client";

import React from "react";
import Link from "next/link";
import {
  FileText,
  ArrowRight,
  Clock,
  Shield,
  User,
  Globe,
  Database,
  CheckCircle2,
} from "lucide-react";
import { AuditLogEntry } from "@/types/control";

interface RecentActivityLedgerProps {
  activity: AuditLogEntry[];
}

function formatTimestamp(timestampStr: string): string {
  try {
    const d = new Date(timestampStr);
    if (!isNaN(d.getTime())) {
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  } catch {
    // fallback
  }
  return timestampStr;
}

function getActionBadgeStyle(action: string): { bg: string; text: string } {
  const upper = action.toUpperCase();
  if (upper.includes("AUTH") || upper.includes("LOGIN") || upper.includes("SESSION")) {
    return { bg: "bg-blue-50", text: "text-blue-700" };
  }
  if (upper.includes("REGISTER") || upper.includes("USER") || upper.includes("STAFF")) {
    return { bg: "bg-teal-50", text: "text-teal-700" };
  }
  if (upper.includes("ORDER") || upper.includes("PAYMENT") || upper.includes("REFUND")) {
    return { bg: "bg-emerald-50", text: "text-emerald-700" };
  }
  if (upper.includes("ROLE") || upper.includes("PERMISSION") || upper.includes("REVOKE")) {
    return { bg: "bg-rose-50", text: "text-rose-700" };
  }
  return { bg: "bg-slate-100", text: "text-slate-700" };
}

export const RecentActivityLedger: React.FC<RecentActivityLedgerProps> = ({ activity }) => {
  return (
    <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-teal-50 text-primary-teal">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-heading text-lg font-bold text-slate-900">
                Recent Platform Activity
              </h3>
              <p className="text-xs text-slate-500">
                Live append-only audit stream capturing platform events and security actions
              </p>
            </div>
          </div>
        </div>

        <Link
          href="/control/audit"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-teal hover:text-teal-700 transition-colors self-start sm:self-auto"
        >
          <span>Full Audit Explorer</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* Content */}
      <div className="mt-4">
        {activity.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <Database className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm font-medium text-slate-600">No recent activity recorded</p>
            <p className="text-xs text-slate-400 mt-1">
              Events will appear here as users, admins, and students interact with the LMS.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-600 uppercase tracking-wider font-bold">
                  <th className="py-2.5 px-3">Action</th>
                  <th className="py-2.5 px-3">Actor</th>
                  <th className="py-2.5 px-3">Target Resource</th>
                  <th className="py-2.5 px-3 hidden md:table-cell">IP Context</th>
                  <th className="py-2.5 px-3 text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {activity.map((entry) => {
                  const badgeStyle = getActionBadgeStyle(entry.action);

                  return (
                    <tr
                      key={entry.id}
                      className="hover:bg-slate-50/80 transition-colors group"
                    >
                      {/* Action */}
                      <td className="py-3 px-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${badgeStyle.bg} ${badgeStyle.text}`}
                        >
                          {entry.action}
                        </span>
                      </td>

                      {/* Actor */}
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <User className="h-3.5 w-3.5 text-slate-400" />
                          <span className="font-medium text-slate-800">
                            {entry.actor_type || "SYSTEM"}
                          </span>
                        </div>
                      </td>

                      {/* Resource */}
                      <td className="py-3 px-3">
                        <div className="font-mono text-[11px] text-slate-600">
                          <span className="text-slate-900 font-semibold">{entry.resource_type}</span>
                          {entry.resource_id && (
                            <span className="text-slate-400 ml-1">
                              ({entry.resource_id.slice(0, 8)}…)
                            </span>
                          )}
                        </div>
                      </td>

                      {/* IP Context */}
                      <td className="py-3 px-3 hidden md:table-cell">
                        <div className="flex items-center gap-1 text-slate-500 font-mono text-[11px]">
                          <Globe className="h-3 w-3 text-slate-400" />
                          <span>{entry.ip_address || "Internal"}</span>
                        </div>
                      </td>

                      {/* Timestamp */}
                      <td className="py-3 px-3 text-right text-slate-500 font-medium whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1">
                          <Clock className="h-3 w-3 text-slate-400" />
                          <span>{formatTimestamp(entry.created_at)}</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
