"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ShieldAlert,
  BookMarked,
  Users,
  CreditCard,
  FileText,
  CheckCircle2,
  LogOut,
  ArrowLeft,
  Menu,
  X,
  Film,
  GraduationCap,
  ShieldCheck,
  UserCog,
  KeyRound,
  FileEdit,
  Tag,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { AuthLoadingOverlay } from "@/components/auth/AuthLoadingOverlay";

interface StaffAdminSidebarProps {
  portal: "staff" | "admin" | "control";
}

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavSection {
  title?: string;
  items: NavItem[];
}

export const StaffAdminSidebar: React.FC<StaffAdminSidebarProps> = ({ portal }) => {
  const pathname = usePathname();
  const { user, logout, isLoggingOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isSuperAdmin = user?.roles?.includes("SUPER_ADMIN") ?? false;

  const getSections = (): NavSection[] => {
    if (portal === "staff") {
      return [
        {
          items: [
            { label: "Grading Queue", href: "/staff", icon: CheckCircle2 },
            { label: "Grading Workspace", href: "/staff/grading", icon: FileText },
          ],
        },
      ];
    }

    if (portal === "admin") {
      const operations: NavItem[] = [
        { label: "Dashboard", href: "/admin", icon: ShieldAlert },
        { label: "Course Management", href: "/admin/courses", icon: BookMarked },
        { label: "Media Library", href: "/admin/media", icon: Film },
        { label: "Student Roster", href: "/admin/students", icon: Users },
        { label: "Enrollment Grants", href: "/admin/enrollments", icon: GraduationCap },
        { label: "Financial Ledger", href: "/admin/orders", icon: CreditCard },
      ];

      const sections: NavSection[] = [
        { title: "Operations", items: operations },
      ];

      if (isSuperAdmin) {
        sections.push({
          title: "Super Admin Control",
          items: [
            { label: "Super Admin Control", href: "/control", icon: ShieldCheck },
            { label: "User Management", href: "/control/users", icon: Users },
            { label: "Security & Sessions", href: "/control/sessions", icon: KeyRound },
            { label: "Platform Settings", href: "/control/settings", icon: Settings },
            { label: "Audit Logs", href: "/control/audit", icon: FileText },
          ],
        });
      }

      return sections;
    }

    // portal === "control"
    return [
      {
        title: "Operations Workspace",
        items: [
          { label: "Admin Console", href: "/admin", icon: ShieldAlert },
          { label: "Course Management", href: "/admin/courses", icon: BookMarked },
          { label: "Media Library", href: "/admin/media", icon: Film },
          { label: "Student Roster", href: "/admin/students", icon: Users },
          { label: "Financial Ledger", href: "/admin/orders", icon: CreditCard },
        ],
      },
      {
        title: "Governance & Content",
        items: [
          { label: "Governance Overview", href: "/control", icon: ShieldAlert },
          { label: "Course Governance", href: "/control/courses", icon: BookMarked },
          { label: "Blog CMS", href: "/control/blog", icon: FileEdit },
          { label: "Notes CMS", href: "/control/notes", icon: FileText },
          { label: "Offers & Discounts", href: "/control/offers", icon: Tag },
          { label: "Payment Overview", href: "/control/payments", icon: CreditCard },
        ],
      },
      {
        title: "Platform & Security",
        items: [
          { label: "User Management", href: "/control/users", icon: Users },
          { label: "Administrator Hub", href: "/control/admins", icon: ShieldCheck },
          { label: "Staff Management", href: "/control/staff", icon: UserCog },
          { label: "Security & Sessions", href: "/control/sessions", icon: KeyRound },
          { label: "Permissions Matrix", href: "/control/permissions", icon: ShieldAlert },
          { label: "Platform Settings", href: "/control/settings", icon: Settings },
          { label: "Audit Logs", href: "/control/audit", icon: FileText },
        ],
      },
    ];
  };

  const sections = getSections();
  const portalTitle =
    portal === "staff"
      ? "Staff Portal"
      : portal === "admin"
      ? isSuperAdmin
        ? "Admin & Control"
        : "Admin Console"
      : "Super Admin Control";

  const getParentRoute = (): { href: string; label: string } | null => {
    if (portal === "admin") {
      if (pathname.startsWith("/admin/courses/") && pathname !== "/admin/courses") {
        return { href: "/admin/courses", label: "Courses" };
      }
      if (pathname !== "/admin") {
        return { href: "/admin", label: "Dashboard" };
      }
    }
    if (portal === "control") {
      if (pathname.startsWith("/control/users/") && pathname !== "/control/users") {
        return { href: "/control/users", label: "Users" };
      }
      if (pathname.startsWith("/control/sessions/") && pathname !== "/control/sessions") {
        return { href: "/control/sessions", label: "Sessions" };
      }
      if (pathname.startsWith("/control/courses/") && pathname !== "/control/courses") {
        return { href: "/control/courses", label: "Courses" };
      }
      if (pathname.startsWith("/control/blog/") && pathname !== "/control/blog") {
        return { href: "/control/blog", label: "Blog" };
      }
      if (pathname.startsWith("/control/notes/") && pathname !== "/control/notes") {
        return { href: "/control/notes", label: "Notes" };
      }
      if (pathname.startsWith("/control/offers/") && pathname !== "/control/offers") {
        return { href: "/control/offers", label: "Offers" };
      }
      if (pathname.startsWith("/control/payments/") && pathname !== "/control/payments") {
        return { href: "/control/payments", label: "Payments" };
      }
      if (pathname.startsWith("/control/settings/") && pathname !== "/control/settings") {
        return { href: "/control/settings", label: "Settings" };
      }
      if (pathname !== "/control") {
        return { href: "/control", label: "Control" };
      }
    }
    if (portal === "staff" && pathname !== "/staff") {
      return { href: "/staff", label: "Queue" };
    }
    return null;
  };

  const parentRoute = getParentRoute();

  return (
    <>
      {/* Mobile Top Navigation Header with Contextual Back Navigation */}
      <div className="md:hidden flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-900 px-4 text-white sticky top-0 z-40">
        <div className="flex items-center gap-2 min-w-0">
          {parentRoute && (
            <Link
              href={parentRoute.href}
              aria-label={`Back to ${parentRoute.label}`}
              className="flex items-center gap-1 text-xs font-semibold text-slate-300 hover:text-white py-1.5 px-2 -ml-2 rounded-lg hover:bg-slate-800 transition-colors min-h-[44px] min-w-[44px]"
            >
              <ArrowLeft className="h-4 w-4 shrink-0 text-primary-teal" />
              <span className="hidden xs:inline">{parentRoute.label}</span>
            </Link>
          )}
          <span className="font-heading text-sm font-bold tracking-tight text-white truncate">
            {portalTitle}
          </span>
        </div>
        <button
          type="button"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          onClick={() => setMobileOpen(!mobileOpen)}
          className="p-2 text-slate-300 hover:text-white focus:outline-none min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg hover:bg-slate-800"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Backdrop & Drawer */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 md:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <div
            className="w-64 bg-slate-900 text-white h-full flex flex-col p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
              <span className="font-heading text-base font-bold text-white">
                {portalTitle}
              </span>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="text-slate-400 hover:text-white min-h-[44px] min-w-[44px] flex items-center justify-center"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="flex-1 space-y-3 overflow-y-auto">
              {sections.map((section, sIdx) => (
                <div key={section.title || sIdx} className="space-y-1">
                  {section.title && (
                    <div className="px-3.5 pt-2 pb-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      {section.title}
                    </div>
                  )}
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const isActive =
                      pathname === item.href ||
                      (item.href !== "/admin" &&
                        item.href !== "/control" &&
                        item.href !== "/staff" &&
                        pathname.startsWith(item.href));

                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setMobileOpen(false)}
                        className={cn(
                          "group flex items-center gap-3 rounded-[10px] px-3.5 py-2.5 font-sans text-sm font-medium transition-colors min-h-[44px]",
                          isActive
                            ? "bg-primary-teal text-white font-semibold"
                            : "text-slate-300 hover:bg-slate-800 hover:text-white"
                        )}
                      >
                        <Icon className="h-5 w-5 shrink-0" />
                        <span>{item.label}</span>
                      </Link>
                    );
                  })}
                </div>
              ))}
            </nav>
            <div className="border-t border-slate-800 pt-4 mt-auto space-y-2">
              <Link
                href="/app"
                className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors min-h-[44px]"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>Exit to Student Dashboard</span>
              </Link>
              <button
                onClick={() => logout()}
                disabled={isLoggingOut}
                type="button"
                className="flex w-full items-center gap-2 rounded-[8px] px-3 py-2 text-xs font-medium text-rose-300 hover:bg-rose-950/40 hover:text-rose-200 transition-colors min-h-[44px]"
              >
                <LogOut className="h-4 w-4" />
                <span>{isLoggingOut ? "Signing out..." : "Sign Out"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Desktop Persistent Sidebar */}
      <aside className="w-64 flex-col border-r border-slate-200 bg-slate-900 text-white min-h-screen sticky top-0 hidden md:flex shrink-0">
        <div className="flex h-16 items-center px-6 border-b border-slate-800 justify-between">
          <span className="font-heading text-base font-bold tracking-tight text-white">
            {portalTitle}
          </span>
        </div>

        <nav className="flex-1 space-y-3 px-3 py-4 overflow-y-auto" aria-label={`${portalTitle} Navigation`}>
          {sections.map((section, sIdx) => (
            <div key={section.title || sIdx} className="space-y-1">
              {section.title && (
                <div className="px-3.5 pt-2 pb-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  {section.title}
                </div>
              )}
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive =
                  pathname === item.href ||
                  (item.href !== "/admin" &&
                    item.href !== "/control" &&
                    item.href !== "/staff" &&
                    pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "group flex items-center gap-3 rounded-[10px] px-3.5 py-2.5 font-sans text-sm font-medium transition-colors min-h-[44px]",
                      isActive
                        ? "bg-primary-teal text-white font-semibold"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    )}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-4 space-y-2">
          <Link
            href="/app"
            className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors min-h-[44px]"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Exit to Student Dashboard</span>
          </Link>
          <button
            onClick={() => logout()}
            disabled={isLoggingOut}
            type="button"
            className="flex w-full items-center gap-2 rounded-[8px] px-3 py-2 text-xs font-medium text-rose-300 hover:bg-rose-950/40 hover:text-rose-200 transition-colors min-h-[44px]"
          >
            <LogOut className="h-4 w-4" />
            <span>{isLoggingOut ? "Signing out..." : "Sign Out"}</span>
          </button>
        </div>
      </aside>

      <AuthLoadingOverlay
        isOpen={isLoggingOut}
        statusMessage="Signing out securely…"
        subMessage="Ending your active session"
      />
    </>
  );
};
