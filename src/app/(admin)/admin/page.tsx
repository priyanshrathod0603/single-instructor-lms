"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  BookMarked,
  Users,
  CreditCard,
  Film,
  Plus,
  ArrowRight,
  TrendingUp,
  ShieldCheck,
  CheckCircle2,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { ordersApi } from "@/lib/api/orders";
import { usersApi } from "@/lib/api/users";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useAuth } from "@/lib/hooks/useAuth";

export default function AdminDashboardPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.roles?.includes("SUPER_ADMIN") ?? false;

  const { data: coursesData, isLoading: coursesLoading } = useQuery({
    queryKey: ["manage-courses"],
    queryFn: () => coursesApi.listManageCourses({ per_page: 5 }),
  });

  const { data: enrollmentsData, isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["all-enrollments"],
    queryFn: () => enrollmentsApi.listAllEnrollments({ per_page: 5 }),
  });

  const { data: ordersData, isLoading: ordersLoading } = useQuery({
    queryKey: ["all-orders"],
    queryFn: () => ordersApi.listAllOrders({ per_page: 5 }),
  });

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ["all-users"],
    queryFn: () => usersApi.listUsers({ per_page: 5 }),
  });

  // Calculate revenue from paid orders
  const totalRevenuePaise =
    ordersData?.items
      ?.filter((o) => o.status === "PAID")
      ?.reduce((sum, o) => sum + (o.amount_inr || 0), 0) || 0;

  const formatCurrency = (paise: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(paise / 100);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Instructor Operations Console
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time analytics, course publishing status, and commercial revenue ledger.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 shrink-0">
          {isSuperAdmin && (
            <Link href="/control" className="w-full sm:w-auto">
              <Button
                variant="outline"
                size="default"
                className="w-full sm:w-auto shrink-0 whitespace-nowrap min-h-[44px] border-amber-600/30 text-amber-700 hover:bg-amber-50 hover:text-amber-800"
              >
                <ShieldCheck className="h-4 w-4 mr-2 shrink-0 text-amber-600" />
                Super Admin Control
              </Button>
            </Link>
          )}
          <Link href="/admin/courses/new" className="w-full sm:w-auto">
            <Button variant="primary" size="default" className="w-full sm:w-auto shrink-0 whitespace-nowrap min-h-[44px]">
              <Plus className="h-4 w-4 mr-2 shrink-0" />
              Create New Course
            </Button>
          </Link>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1 */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 truncate">
              Total Courses
            </span>
            <div className="p-2 rounded-lg bg-teal-50 text-primary-teal shrink-0">
              <BookMarked className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2 tracking-tight">
            {coursesLoading ? "..." : coursesData?.total ?? 0}
          </p>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2 truncate">
            <span className="font-semibold text-teal-700">
              {coursesData?.items?.filter((c) => c.status === "PUBLISHED").length || 0}
            </span>{" "}
            published live
          </div>
        </div>

        {/* Metric 2 */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 truncate">
              Active Enrollments
            </span>
            <div className="p-2 rounded-lg bg-orange-50 text-coral-orange shrink-0">
              <Users className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2 tracking-tight">
            {enrollmentsLoading ? "..." : enrollmentsData?.total ?? 0}
          </p>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2 truncate">
            <span className="font-semibold text-emerald-700">100% verified</span> via gateway webhooks
          </div>
        </div>

        {/* Metric 3 */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 truncate">
              Gross Sales (Sampled)
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600 shrink-0">
              <CreditCard className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2 tracking-tight">
            {ordersLoading ? "..." : formatCurrency(totalRevenuePaise)}
          </p>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2 truncate">
            Total transactions: {ordersData?.total ?? 0}
          </div>
        </div>

        {/* Metric 4 */}
        <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 truncate">
              Student Directory
            </span>
            <div className="p-2 rounded-lg bg-purple-50 text-purple-600 shrink-0">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
          <p className="text-2xl font-extrabold text-slate-900 mt-2 tracking-tight">
            {usersLoading ? "..." : usersData?.total ?? 0}
          </p>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-2 truncate">
            Registered learner accounts
          </div>
        </div>
      </div>

      {/* Two Column Layout: Recent Courses & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Course Status Overview */}
        <div className="lg:col-span-2 rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <h2 className="font-heading text-base font-bold text-slate-900">
              Courses Management
            </h2>
            <Link
              href="/admin/courses"
              className="text-xs font-semibold text-primary-teal hover:underline flex items-center gap-1"
            >
              <span>View all courses</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          <div className="divide-y divide-slate-100">
            {coursesLoading ? (
              <div className="p-8 text-center text-sm text-slate-500">Loading courses...</div>
            ) : !coursesData?.items?.length ? (
              <div className="p-8 text-center text-sm text-slate-500">
                No courses created yet. Click "Create New Course" above.
              </div>
            ) : (
              coursesData.items.map((course) => (
                <div key={course.id} className="flex items-center justify-between p-4 hover:bg-slate-50">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-slate-900 truncate">{course.title}</p>
                      <Badge variant={course.status === "PUBLISHED" ? "success" : "outline"}>
                        {course.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Slug: /{course.slug} · {course.is_free ? "Free" : formatCurrency(course.price_inr)}
                    </p>
                  </div>
                  <Link href={`/admin/courses/${course.id}/edit`}>
                    <Button variant="outline" size="sm">
                      Manage Curriculum
                    </Button>
                  </Link>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Quick Portal Links */}
        <div className="space-y-4">
          <div className="rounded-[16px] border border-slate-200 bg-white p-5 shadow-sm space-y-3">
            <h3 className="font-heading text-sm font-bold text-slate-900">
              Management Portals
            </h3>
            <div className="space-y-2">
              <Link
                href="/admin/courses"
                className="flex items-center justify-between p-3 rounded-[12px] bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <BookMarked className="h-4 w-4 text-primary-teal" />
                  <span className="text-sm font-medium text-slate-800">Course & Curriculum Hub</span>
                </div>
                <ArrowRight className="h-4 w-4 text-slate-400" />
              </Link>

              <Link
                href="/admin/media"
                className="flex items-center justify-between p-3 rounded-[12px] bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Film className="h-4 w-4 text-primary-teal" />
                  <span className="text-sm font-medium text-slate-800">Media & Video Library</span>
                </div>
                <ArrowRight className="h-4 w-4 text-slate-400" />
              </Link>

              <Link
                href="/admin/enrollments"
                className="flex items-center justify-between p-3 rounded-[12px] bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Users className="h-4 w-4 text-primary-teal" />
                  <span className="text-sm font-medium text-slate-800">Enrollment Grants</span>
                </div>
                <ArrowRight className="h-4 w-4 text-slate-400" />
              </Link>

              <Link
                href="/admin/orders"
                className="flex items-center justify-between p-3 rounded-[12px] bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <CreditCard className="h-4 w-4 text-primary-teal" />
                  <span className="text-sm font-medium text-slate-800">Orders & Refunds</span>
                </div>
                <ArrowRight className="h-4 w-4 text-slate-400" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
