"use client";

import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle,
  Circle,
  PlayCircle,
  FileText,
  HelpCircle,
  CheckSquare,
  Award,
  Download,
  Clock,
  Sparkles,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { coursesApi } from "@/lib/api/courses";
import { progressApi } from "@/lib/api/progress";
import { certificatesApi } from "@/lib/api/certificates";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/Accordion";
import { CurriculumLesson } from "@/types/course";

export default function EnrolledCourseDetailPage() {
  const params = useParams();
  const courseId = params?.id as string;

  const {
    data: course,
    isLoading: isCourseLoading,
    isError: isCourseError,
    error: courseError,
    refetch: refetchCourse,
  } = useQuery({
    queryKey: ["course-detail", courseId],
    queryFn: () => coursesApi.getCourseDetail(courseId),
    enabled: !!courseId,
  });

  const {
    data: progress,
    isLoading: isProgressLoading,
    refetch: refetchProgress,
  } = useQuery({
    queryKey: ["course-progress", courseId],
    queryFn: () => progressApi.getCourseProgress(courseId),
    enabled: !!courseId,
  });

  const isCompleted = progress?.is_completed ?? false;
  const completedLessonIds = new Set(progress?.completed_lesson_ids ?? []);
  const percentage = progress ? Math.round(Number(progress.progress_percentage)) : 0;

  const { data: certificate } = useQuery({
    queryKey: ["course-certificate", courseId],
    queryFn: () => certificatesApi.getCourseCertificate(courseId),
    enabled: isCompleted && !!courseId,
    retry: false,
  });

  if (isCourseLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-24 w-full" />
        <div className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      </div>
    );
  }

  if (isCourseError || !course) {
    return (
      <div className="space-y-6">
        <Link
          href="/app/courses"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to My Courses
        </Link>
        <ErrorAlert
          title="Could not load course curriculum"
          message={courseError?.message || "Course information could not be retrieved."}
          onRetry={() => {
            refetchCourse();
            refetchProgress();
          }}
        />
      </div>
    );
  }

  // Find first incomplete lesson or first lesson overall for Resume CTA
  let firstActionableLesson: CurriculumLesson | null = null;
  for (const section of course.curriculum || []) {
    for (const lesson of section.lessons || []) {
      if (!completedLessonIds.has(lesson.id)) {
        firstActionableLesson = lesson;
        break;
      }
    }
    if (firstActionableLesson) break;
  }
  if (!firstActionableLesson && course.curriculum?.[0]?.lessons?.[0]) {
    firstActionableLesson = course.curriculum[0].lessons[0];
  }

  const getLessonIcon = (type: string) => {
    switch (type) {
      case "VIDEO":
        return <PlayCircle className="h-4 w-4 text-primary-teal shrink-0" />;
      case "ARTICLE":
        return <FileText className="h-4 w-4 text-sky-600 shrink-0" />;
      case "QUIZ":
        return <HelpCircle className="h-4 w-4 text-amber-600 shrink-0" />;
      case "ASSIGNMENT":
        return <CheckSquare className="h-4 w-4 text-accent-coral shrink-0" />;
      default:
        return <FileText className="h-4 w-4 text-slate-500 shrink-0" />;
    }
  };

  return (
    <div className="space-y-8">
      {/* Back button */}
      <div>
        <Link
          href="/app/courses"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to My Courses
        </Link>
      </div>

      {/* Header Info Banner */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-6 sm:p-8 shadow-card">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center gap-2">
              <Badge variant={isCompleted ? "mint" : "outline"} size="sm">
                {isCompleted ? "Course Completed" : "In Progress"}
              </Badge>
              {course.tags?.map((t) => (
                <Badge key={t} variant="outline" size="sm">
                  {t}
                </Badge>
              ))}
            </div>
            <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">
              {course.title}
            </h1>
            {course.headline && (
              <p className="font-sans text-sm sm:text-base text-slate-600">
                {course.headline}
              </p>
            )}
          </div>

          {/* Quick Action Button */}
          {firstActionableLesson && (
            <div className="shrink-0">
              <Link href={`/learn/${course.id}/${firstActionableLesson.id}`}>
                <Button variant="primary" size="lg" className="w-full sm:w-auto">
                  <PlayCircle className="mr-2 h-5 w-5" />
                  {isCompleted ? "Review Lessons" : "Continue Learning"}
                </Button>
              </Link>
            </div>
          )}
        </div>

        {/* Progress Bar */}
        <div className="mt-6 pt-6 border-t border-slate-100 space-y-2">
          <div className="flex items-center justify-between text-xs sm:text-sm font-medium text-slate-700">
            <span>Overall Syllabus Completion</span>
            <span className="font-bold text-slate-900">{percentage}%</span>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-primary-teal transition-all duration-300"
              style={{ width: `${percentage}%` }}
            />
          </div>
          {progress && (
            <p className="text-xs text-slate-500">
              {progress.completed_lessons_count} of {progress.total_lessons_count} lessons completed
            </p>
          )}
        </div>
      </div>

      {/* Certificate Notice if 100% completed */}
      {isCompleted && (
        <Card className="border border-emerald-200 bg-emerald-50/70 p-5 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-800">
                <Award className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-heading text-base font-bold text-emerald-950">
                  Congratulations! Course Completed 🎓
                </h3>
                <p className="text-xs sm:text-sm text-emerald-800 mt-0.5">
                  Your verifiable certificate of completion is ready.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/app/certificates">
                <Button variant="secondary" size="sm">
                  View Certificates
                </Button>
              </Link>
              {certificate && (
                <a
                  href={certificatesApi.getDownloadUrl(course.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Button variant="primary" size="sm">
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                    Download PDF
                  </Button>
                </a>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Curriculum Accordion */}
      <div className="space-y-4">
        <h2 className="font-heading text-xl font-bold text-slate-900">
          Curriculum Syllabus
        </h2>

        {course.curriculum && course.curriculum.length > 0 ? (
          <Accordion
            type="multiple"
            defaultValue={course.curriculum.map((s) => s.id)}
            className="space-y-3"
          >
            {course.curriculum.map((section, idx) => {
              const sectionLessonIds = (section.lessons || []).map((l) => l.id);
              const completedInSection = sectionLessonIds.filter((id) =>
                completedLessonIds.has(id)
              ).length;

              return (
                <AccordionItem
                  key={section.id}
                  value={section.id}
                  className="rounded-[12px] border border-slate-200 bg-white overflow-hidden shadow-xs"
                >
                  <AccordionTrigger className="px-5 py-4 hover:no-underline hover:bg-slate-50/50">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full pr-4 text-left gap-1">
                      <div>
                        <span className="font-mono text-xs font-semibold text-primary-teal uppercase tracking-wider">
                          Section {idx + 1}
                        </span>
                        <h3 className="font-heading text-base font-bold text-slate-900">
                          {section.title}
                        </h3>
                      </div>
                      <span className="font-sans text-xs text-slate-500">
                        {completedInSection} / {section.lessons?.length || 0} completed
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="border-t border-slate-100 divide-y divide-slate-100 bg-slate-50/30">
                    {section.lessons && section.lessons.length > 0 ? (
                      section.lessons.map((lesson) => {
                        const isLessonCompleted = completedLessonIds.has(lesson.id);

                        return (
                          <div
                            key={lesson.id}
                            className="flex items-center justify-between p-4 px-5 hover:bg-white transition-colors"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              {isLessonCompleted ? (
                                <CheckCircle className="h-5 w-5 text-primary-teal shrink-0" />
                              ) : (
                                <Circle className="h-5 w-5 text-slate-300 shrink-0" />
                              )}
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  {getLessonIcon(lesson.lesson_type)}
                                  <span className="font-sans text-sm font-semibold text-slate-800 truncate">
                                    {lesson.title}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2 mt-0.5 font-mono text-xs text-slate-400">
                                  <span>{lesson.lesson_type}</span>
                                  {lesson.duration_seconds > 0 && (
                                    <>
                                      <span>•</span>
                                      <span>{Math.round(lesson.duration_seconds / 60)} min</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>

                            <Link href={`/learn/${course.id}/${lesson.id}`}>
                              <Button
                                variant={isLessonCompleted ? "ghost" : "primary"}
                                size="sm"
                                className="min-h-[32px] shrink-0 text-xs"
                              >
                                {isLessonCompleted ? "Review" : "Start"}
                              </Button>
                            </Link>
                          </div>
                        );
                      })
                    ) : (
                      <p className="p-4 text-xs text-slate-400 italic">
                        No lessons in this section.
                      </p>
                    )}
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        ) : (
          <p className="text-sm text-slate-500 italic">
            Curriculum content is being finalized by the instructor.
          </p>
        )}
      </div>
    </div>
  );
}
