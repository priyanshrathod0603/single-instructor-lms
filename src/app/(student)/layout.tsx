import React from "react";
import { StudentSidebar } from "@/components/navigation/StudentSidebar";
import { StudentBottomNav } from "@/components/navigation/StudentBottomNav";
import { requireServerAuth } from "@/lib/auth/serverAuth";

export default async function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Authoritative server-side session validation
  await requireServerAuth({ redirectUrl: "/app" });

  return (
    <div className="flex min-h-screen bg-slate-50/60">
      {/* Tablet and Desktop Sidebar (768px and above) */}
      <StudentSidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 p-4 sm:p-6 lg:p-8 pb-24 md:pb-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>

      {/* Mobile Fixed Bottom Navigation (below 768px) */}
      <StudentBottomNav />
    </div>
  );
}
