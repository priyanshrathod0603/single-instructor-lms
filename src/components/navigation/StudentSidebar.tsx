"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  FileCheck,
  CheckSquare,
  Award,
  Receipt,
  User as UserIcon,
  LogOut,
  GraduationCap,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { label: "Overview", href: "/app", icon: LayoutDashboard },
  { label: "My Courses", href: "/app/courses", icon: BookOpen },
  { label: "Assignments", href: "/app/assignments", icon: FileCheck },
  { label: "Quizzes", href: "/app/quizzes", icon: CheckSquare },
  { label: "Certificates", href: "/app/certificates", icon: Award },
  { label: "Orders", href: "/app/orders", icon: Receipt },
  { label: "Profile", href: "/app/profile", icon: UserIcon },
];

export const StudentSidebar: React.FC = () => {
  const pathname = usePathname();
  const { user, logout, isLoggingOut } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col border-r border-slate-200 bg-white min-h-screen sticky top-0 transition-all duration-200 z-30",
        isCollapsed ? "w-20" : "w-60"
      )}
      aria-label="Student Navigation"
    >
      {/* Brand Header */}
      <div className={cn("flex h-16 items-center border-b border-slate-100 px-4", isCollapsed ? "justify-center" : "justify-between")}>
        <Link href="/app" className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-[8px] bg-primary-teal text-white shadow-sm shrink-0">
            <GraduationCap className="h-5 w-5" />
          </div>
          {!isCollapsed && (
            <span className="font-heading text-lg font-bold tracking-tight text-slate-900 truncate">
              Instructor<span className="text-primary-teal">LMS</span>
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={cn(
            "hidden md:flex lg:flex h-8 w-8 items-center justify-center rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors",
            isCollapsed && "mt-2"
          )}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 space-y-1.5 px-3 py-4" aria-label="Student Nav Items">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href ||
            (item.href !== "/app" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              title={isCollapsed ? item.label : undefined}
              className={cn(
                "group flex items-center rounded-[10px] font-sans text-sm font-medium transition-all duration-150 min-h-[44px]",
                isCollapsed ? "justify-center px-0 py-2.5" : "gap-3 px-3.5 py-2.5",
                isActive
                  ? "bg-accent-mint/50 text-primary-teal font-semibold shadow-xs"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )}
            >
              <Icon
                className={cn(
                  "h-5 w-5 transition-colors shrink-0",
                  isActive ? "text-primary-teal" : "text-slate-400 group-hover:text-slate-600"
                )}
              />
              {!isCollapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* User profile & Logout */}
      <div className="border-t border-slate-100 p-3">
        <div className={cn("flex items-center gap-3 mb-3", isCollapsed && "justify-center")}>
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-peach/50 text-accent-coral font-bold text-sm shrink-0">
            {user?.full_name ? user.full_name[0].toUpperCase() : "S"}
          </div>
          {!isCollapsed && (
            <div className="flex-1 min-w-0">
              <p className="truncate font-sans text-sm font-semibold text-slate-900">
                {user?.full_name || "Student"}
              </p>
              <p className="truncate font-sans text-xs text-slate-500">
                {user?.email || ""}
              </p>
            </div>
          )}
        </div>
        <button
          onClick={() => logout()}
          disabled={isLoggingOut}
          type="button"
          title={isCollapsed ? "Sign Out" : undefined}
          className={cn(
            "flex w-full items-center rounded-[8px] py-2 text-xs font-medium text-slate-600 hover:bg-rose-50 hover:text-rose-700 transition-colors min-h-[44px]",
            isCollapsed ? "justify-center px-0" : "gap-2.5 px-3"
          )}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {!isCollapsed && <span>{isLoggingOut ? "Signing out..." : "Sign Out"}</span>}
        </button>
      </div>

      <AuthLoadingOverlay
        isOpen={isLoggingOut}
        statusMessage="Signing out securely…"
        subMessage="Ending your active session"
      />
    </aside>
  );
};
