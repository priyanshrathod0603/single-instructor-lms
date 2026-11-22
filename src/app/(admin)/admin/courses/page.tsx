"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BookMarked,
  Plus,
  Search,
  Edit2,
  Trash2,
  GitFork,
  ArrowRight,
  ArrowLeft,
  Loader2,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function AdminCoursesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["manage-courses", search, page],
    queryFn: () => coursesApi.listManageCourses({ search, page, per_page: 20 }),
  });

  const forkRevisionMutation = useMutation({
    mutationFn: (courseId: string) => coursesApi.createRevision(courseId),
    onSuccess: (revision) => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
      window.location.href = `/admin/courses/${revision.course_id}/edit`;
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (courseId: string) => coursesApi.archiveCourse(courseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
    },
  });

  const formatCurrency = (paise: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(paise / 100);
  };

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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">
            Course Management Directory
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Author courses, manage curriculum revisions, and control catalog publishing.
          </p>
        </div>
        <Link href="/admin/courses/new">
          <Button variant="primary" size="default">
            <Plus className="h-4 w-4 mr-2" />
            Create New Course
          </Button>
        </Link>
      </div>

      {/* Search and Filters */}
      <div className="flex items-center gap-4 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search courses by title or slug..."
            className="pl-10"
          />
        </div>
      </div>

      {/* Courses Table / Cards */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !data?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-3">
            <BookMarked className="h-10 w-10 text-slate-300 mx-auto" />
            <h3 className="font-heading font-bold text-base text-slate-800">No Courses Found</h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Get started by creating your first course entity.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Course Title & Slug</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Pricing</th>
                  <th scope="col" className="px-6 py-4">Updated</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((course) => (
                  <tr key={course.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">{course.title}</div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5">/{course.slug}</div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={course.status === "PUBLISHED" ? "success" : "outline"}>
                        {course.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-800">
                      {course.is_free ? "Free" : formatCurrency(course.price_inr)}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(course.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <Link href={`/admin/courses/${course.id}/edit`}>
                        <Button variant="outline" size="sm">
                          <Edit2 className="h-3.5 w-3.5 mr-1.5" />
                          Edit Curriculum
                        </Button>
                      </Link>

                      {course.status === "PUBLISHED" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          isLoading={forkRevisionMutation.isPending}
                          onClick={() => forkRevisionMutation.mutate(course.id)}
                          title="Spawn new working draft revision"
                        >
                          <GitFork className="h-3.5 w-3.5 mr-1.5" />
                          Fork Draft
                        </Button>
                      )}

                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Archive course "${course.title}"?`)) {
                            archiveMutation.mutate(course.id);
                          }
                        }}
                        className="text-slate-400 hover:text-rose-600 p-2 rounded transition-colors inline-flex items-center justify-center min-h-[36px] min-w-[36px]"
                        title="Archive Course"
                        aria-label={`Archive ${course.title}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
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
