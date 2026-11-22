"use client";

import React from "react";
import { ShieldAlert, Check, X } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

export default function ControlPermissionsPage() {
  const permissionsList = [
    { module: "Courses", key: "course:view_public", desc: "View catalog & public previews", roles: ["VISITOR", "STUDENT", "STAFF", "ADMIN", "SUPER_ADMIN"] },
    { module: "Courses", key: "course:view_all", desc: "View draft & archived courses", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Courses", key: "course:create", desc: "Create new courses", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Courses", key: "course:edit", desc: "Edit curriculum draft content", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Courses", key: "course:publish", desc: "Freeze and publish course live", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Courses", key: "course:delete", desc: "Permanent course purge", roles: ["SUPER_ADMIN"] },
    { module: "Curriculum", key: "curriculum:manage", desc: "Add/edit sections & lessons", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Curriculum", key: "curriculum:reorder", desc: "Drag-and-drop sort ordering", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Media", key: "media:upload", desc: "Request presigned upload intents", roles: ["STAFF", "ADMIN", "SUPER_ADMIN"] },
    { module: "Media", key: "media:view_protected", desc: "Request signed playback tokens", roles: ["STUDENT", "STAFF", "ADMIN", "SUPER_ADMIN"] },
    { module: "Assignments", key: "assignment:submit", desc: "Submit project deliverables", roles: ["STUDENT", "SUPER_ADMIN"] },
    { module: "Assignments", key: "assignment:grade", desc: "Grade submissions against rubrics", roles: ["STAFF", "ADMIN", "SUPER_ADMIN"] },
    { module: "Assignments", key: "assignment:override", desc: "Administrative grade override", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Quizzes", key: "quiz:attempt", desc: "Take quiz attempt", roles: ["STUDENT", "SUPER_ADMIN"] },
    { module: "Quizzes", key: "quiz:import_csv", desc: "Bulk import questions via CSV", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Enrollments", key: "enrollment:grant", desc: "Manual scholarship enrollment", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Enrollments", key: "enrollment:revoke", desc: "Revoke student course access", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Commerce", key: "payments:refund", desc: "Authorize payment refunds", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Auditing", key: "audit:view", desc: "Inspect immutable audit log trail", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Governance", key: "staff:invite", desc: "Issue staff onboarding tokens", roles: ["ADMIN", "SUPER_ADMIN"] },
    { module: "Governance", key: "roles:assign", desc: "Modify system role assignments", roles: ["SUPER_ADMIN"] },
  ];

  const roles = ["VISITOR", "STUDENT", "STAFF", "ADMIN", "SUPER_ADMIN"] as const;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Role-Based Access Control (RBAC) Matrix
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Authoritative permissions specification enforced across API routes and database transactions.
        </p>
      </div>

      {/* Matrix Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
              <tr>
                <th scope="col" className="px-6 py-4">Domain & Permission Key</th>
                <th scope="col" className="px-6 py-4">Description</th>
                {roles.map((r) => (
                  <th key={r} scope="col" className="px-4 py-4 text-center">
                    {r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {permissionsList.map((p) => (
                <tr key={p.key} className="hover:bg-slate-50/80 transition-colors">
                  <td className="px-6 py-3.5">
                    <span className="font-mono text-xs font-semibold text-slate-900">{p.key}</span>
                    <span className="block text-[11px] text-slate-400 mt-0.5">{p.module}</span>
                  </td>
                  <td className="px-6 py-3.5 text-xs text-slate-600">{p.desc}</td>
                  {roles.map((r) => {
                    const hasAccess = p.roles.includes(r);
                    return (
                      <td key={r} className="px-4 py-3.5 text-center">
                        {hasAccess ? (
                          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-teal-50 text-primary-teal">
                            <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                          </span>
                        ) : (
                          <span className="inline-flex h-5 w-5 items-center justify-center text-slate-300">
                            <X className="h-3.5 w-3.5" />
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
