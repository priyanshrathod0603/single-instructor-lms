import React from "react";
import { StaffAdminSidebar } from "@/components/navigation/StaffAdminSidebar";
import { requireServerAuth } from "@/lib/auth/serverAuth";

export default async function StaffLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Authoritative server-side session and role validation
  await requireServerAuth({
    requiredRole: "STAFF",
    redirectUrl: "/staff",
  });

  return (
    <div className="flex flex-col md:flex-row min-h-screen bg-slate-50">
      <StaffAdminSidebar portal="staff" />
      <main className="flex-1 p-4 sm:p-6 lg:p-8 min-w-0 max-w-7xl mx-auto w-full">
        {children}
      </main>
    </div>
  );
}
