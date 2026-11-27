"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Search,
  CheckCircle2,
  Clock,
  ArrowRight,
  Loader2,
  BookMarked,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { assignmentsApi } from "@/lib/api/assignments";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function StaffGradingQueuePage() {
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const [selectedLessonId, setSelectedLessonId] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("SUBMITTED");

  // Fetch available courses
  const { data: coursesData } = useQuery({
    queryKey: ["manage-courses-staff"],
    queryFn: () => coursesApi.listManageCourses({ per_page: 50 }),
  });

  // Fetch target course details to get curriculum sections & lessons
  const { data: courseDetail } = useQuery({
    queryKey: ["course-detail-staff", selectedCourseId],
    queryFn: () => coursesApi.getCourseDetail(selectedCourseId),
    enabled: !!selectedCourseId,
  });

  // Extract all assignment lessons in this course
  const assignmentLessons =
    courseDetail?.curriculum?.flatMap((s) =>
      s.lessons.filter((l) => l.lesson_type === "ASSIGNMENT")
    ) || [];

  // Resolve the CurriculumLesson ID to its linked Assignment ID before fetching submissions
  const {
    data: resolvedAssignment,
    isLoading: assignmentLoading,
    isError: assignmentMissing,
  } = useQuery({
    queryKey: ["lesson-assignment-staff", selectedLessonId],
    queryFn: () => assignmentsApi.getLessonAssignment(selectedLessonId),
    enabled: !!selectedLessonId,
    retry: false,
  });

  const resolvedAssignmentId = resolvedAssignment?.id || "";

  // Fetch submissions for chosen assignment
  const { data: submissionsData, isLoading: submissionsLoading } = useQuery({
    queryKey: ["assignment-submissions", resolvedAssignmentId, statusFilter],
    queryFn: () =>
      assignmentsApi.listAssignmentSubmissions(resolvedAssignmentId, {
        status: statusFilter || undefined,
        size: 50,
      }),
    enabled: !!resolvedAssignmentId,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Staff Grading Queue
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Select a course assignment to view pending student submissions and execute rubric grading.
        </p>
      </div>

      {/* Selectors Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm">
        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
            Course Selection
          </label>
          <select
            value={selectedCourseId}
            onChange={(e) => {
              setSelectedCourseId(e.target.value);
              setSelectedLessonId("");
            }}
            className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
          >
            <option value="">Select a course...</option>
            {coursesData?.items?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
            Assignment Lesson
          </label>
          <select
            value={selectedLessonId}
            onChange={(e) => setSelectedLessonId(e.target.value)}
            disabled={!selectedCourseId}
            className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-teal/20 disabled:bg-slate-50 disabled:text-slate-400"
          >
            <option value="">
              {!selectedCourseId
                ? "First pick a course..."
                : assignmentLessons.length === 0
                ? "No assignment lessons in course"
                : "Select an assignment lesson..."}
            </option>
            {assignmentLessons.map((l) => (
              <option key={l.id} value={l.id}>
                {l.title}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">
            Submission Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-teal/20"
          >
            <option value="">All Statuses</option>
            <option value="SUBMITTED">Pending Grading (SUBMITTED)</option>
            <option value="GRADED">Evaluated (GRADED)</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>
      </div>

      {/* Submissions List */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {!selectedLessonId ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <BookMarked className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">
              Select a Course and Assignment above to view the grading queue.
            </p>
          </div>
        ) : assignmentLoading || submissionsLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : assignmentMissing || !resolvedAssignmentId ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <Clock className="h-8 w-8 text-amber-500 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">Assignment Not Configured</p>
            <p className="text-xs text-slate-500">
              This curriculum lesson does not have an assignment rubric configured yet.
            </p>
          </div>
        ) : !submissionsData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">Queue is Clear!</p>
            <p className="text-xs text-slate-500">
              No student submissions matching "{statusFilter || "All"}" status.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Student & Attempt</th>
                  <th scope="col" className="px-6 py-4">Submitted Date</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Score</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {submissionsData.items.map((sub) => (
                  <tr key={sub.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">
                        {sub.student_name || "Student"}
                      </div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5">
                        {sub.student_email || sub.student_id} · Attempt #{sub.attempt_no}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(sub.submitted_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={sub.status === "GRADED" ? "success" : "outline"}>
                        {sub.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 font-bold text-slate-900">
                      {sub.final_score !== null && sub.final_score !== undefined
                        ? `${sub.final_score} pts`
                        : "—"}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link href={`/staff/grading/${sub.id}`}>
                        <Button
                          variant="primary"
                          size="sm"
                        >
                          <FileText className="h-3.5 w-3.5 mr-1.5" />
                          {sub.status === "GRADED" ? "Review Grade" : "Grade Submission"}
                        </Button>
                      </Link>
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
