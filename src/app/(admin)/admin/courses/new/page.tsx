"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { CourseMetadataForm } from "@/components/admin/course-form";

export default function NewCoursePage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-slate-500">
        <Link
          href="/admin/courses"
          className="inline-flex items-center gap-1.5 font-medium text-brand-teal hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Courses</span>
        </Link>
        <span aria-hidden="true">/</span>
        <span className="font-semibold text-slate-900">Create New Course</span>
      </nav>

      {/* Header */}
      <header className="space-y-1">
        <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Create Course Entity
        </h1>
        <p className="text-sm text-slate-600">
          Configure core metadata, visual cover thumbnail, learner outcomes, and INR pricing. An
          initial Draft Revision 1 will be created automatically.
        </p>
      </header>

      <CourseMetadataForm
        mode="create"
        onSaved={(createdCourse) => {
          queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
          router.push(`/admin/courses/${createdCourse.id}/edit?tab=metadata`);
        }}
        onCancel={() => router.push("/admin/courses")}
      />
    </div>
  );
}
