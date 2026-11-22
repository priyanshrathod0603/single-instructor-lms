"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Menu,
  FileText,
  HelpCircle,
  CheckSquare,
  ArrowRight,
  Download,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { coursesApi } from "@/lib/api/courses";
import { progressApi } from "@/lib/api/progress";
import { VideoPlayer } from "@/components/player/VideoPlayer";
import { ArticleReader } from "@/components/player/ArticleReader";
import { ProtectedPdfViewer } from "@/components/player/ProtectedPdfViewer";
import { CurriculumSidebar } from "@/components/player/CurriculumSidebar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { CurriculumLesson } from "@/types/course";

export default function CourseLearningPlayerPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const courseId = params?.courseId as string;
  const lessonId = params?.lessonId as string;
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // 1. Fetch Course Structure & Curriculum
  const {
    data: course,
    isLoading: isCourseLoading,
    isError: isCourseError,
    error: courseError,
  } = useQuery({
    queryKey: ["course-detail", courseId],
    queryFn: () => coursesApi.getCourseDetail(courseId),
    enabled: !!courseId,
  });

  // 2. Fetch Progress Status
  const { data: progress } = useQuery({
    queryKey: ["course-progress", courseId],
    queryFn: () => progressApi.getCourseProgress(courseId),
    enabled: !!courseId,
  });

  const completedLessonIds = new Set(progress?.completed_lesson_ids ?? []);

  // Flatten lessons to find current, previous, and next
  const allLessons: CurriculumLesson[] = [];
  if (course?.curriculum) {
    for (const section of course.curriculum) {
      if (section.lessons) {
        allLessons.push(...section.lessons);
      }
    }
  }

  const currentIndex = allLessons.findIndex((l) => l.id === lessonId);
  const currentLesson = currentIndex >= 0 ? allLessons[currentIndex] : null;
  const prevLesson = currentIndex > 0 ? allLessons[currentIndex - 1] : null;
  const nextLesson =
    currentIndex >= 0 && currentIndex < allLessons.length - 1
      ? allLessons[currentIndex + 1]
      : null;

  const handleLessonCompleted = () => {
    queryClient.invalidateQueries({ queryKey: ["course-progress", courseId] });
  };

  if (isCourseLoading) {
    return (
      <div className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="aspect-video w-full rounded-[12px]" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isCourseError || !course) {
    return (
      <div className="flex-1 p-6 max-w-4xl mx-auto w-full">
        <ErrorAlert
          title="Could not load learning player"
          message={courseError?.message || "Course content could not be loaded."}
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  if (!currentLesson) {
    return (
      <div className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-4">
        <ErrorAlert
          title="Lesson Not Found"
          message="The requested lesson does not exist in this course curriculum."
        />
        <Link href={`/app/courses/${courseId}`}>
          <Button variant="primary">Return to Course Overview</Button>
        </Link>
      </div>
    );
  }

  // Extract media ID if video lesson (Task A: canonical media_asset_id with deterministic fallback)
  const lessonContent =
    currentLesson.content &&
    typeof currentLesson.content === "object" &&
    !Array.isArray(currentLesson.content)
      ? currentLesson.content
      : {};

  const resolvedContentMediaId =
    (typeof lessonContent.media_asset_id === "string" && lessonContent.media_asset_id.trim()) ||
    (typeof lessonContent.media_id === "string" && lessonContent.media_id.trim()) ||
    (typeof lessonContent.video_id === "string" && lessonContent.video_id.trim()) ||
    "";

  const resolvedResourceMediaId =
    currentLesson.resources?.find((r) => r.resource_type === "ASSET" || r.file_url)?.id ||
    "";

  const mediaId = resolvedContentMediaId || resolvedResourceMediaId || "";

  // Check for PDF resource
  const pdfResource = currentLesson.resources?.find(
    (r) => r.resource_type === "PDF" || r.file_url?.endsWith(".pdf")
  );

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Learning Stage (Left / Center) */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Navigation Bar & Mobile Curriculum Drawer Toggle */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsMobileSidebarOpen(true)}
              className="lg:hidden flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50"
            >
              <Menu className="h-4 w-4" />
              <span>Curriculum</span>
            </button>
            <h1 className="font-heading text-lg sm:text-xl font-bold text-slate-900 truncate">
              {currentLesson.title}
            </h1>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {prevLesson && (
              <Link href={`/learn/${courseId}/${prevLesson.id}`}>
                <Button variant="outline" size="sm" className="h-8 px-2.5 text-xs">
                  <ChevronLeft className="h-3.5 w-3.5 mr-1" />
                  <span className="hidden sm:inline">Previous</span>
                </Button>
              </Link>
            )}
            {nextLesson && (
              <Link href={`/learn/${courseId}/${nextLesson.id}`}>
                <Button variant="primary" size="sm" className="h-8 px-2.5 text-xs">
                  <span className="hidden sm:inline">Next</span>
                  <ChevronRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </Link>
            )}
          </div>
        </div>

        {/* Lesson Canvas by Type */}
        {currentLesson.lesson_type === "VIDEO" ? (
          <div className="space-y-6">
            {mediaId ? (
              <VideoPlayer
                mediaId={mediaId}
                lessonId={currentLesson.id}
                courseId={courseId}
                onCompleted={handleLessonCompleted}
              />
            ) : (
              <Card className="aspect-video w-full flex flex-col items-center justify-center p-8 text-center bg-slate-900 text-white rounded-[12px]">
                <h3 className="font-heading text-lg font-bold">
                  Video Stream Ready to Transcode
                </h3>
                <p className="text-xs text-slate-400 max-w-sm mt-1">
                  Video assets are scheduled for processing. Review supplementary lesson notes below.
                </p>
              </Card>
            )}
          </div>
        ) : currentLesson.lesson_type === "ARTICLE" ? (
          <ArticleReader
            lessonId={currentLesson.id}
            title={currentLesson.title}
            content={currentLesson.content}
            isCompletedInitially={completedLessonIds.has(currentLesson.id)}
            onCompleted={handleLessonCompleted}
          />
        ) : currentLesson.lesson_type === "QUIZ" ? (
          <Card className="p-6 sm:p-10 text-center space-y-4 max-w-2xl mx-auto border border-amber-200 bg-amber-50/40">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-amber-700 mx-auto">
              <HelpCircle className="h-7 w-7" />
            </div>
            <h2 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">
              Interactive Quiz Assessment
            </h2>
            <p className="font-sans text-sm text-slate-600 max-w-md mx-auto">
              Test your knowledge of this module. This timed assessment will record your score and verify your learning mastery.
            </p>
            <div className="pt-2">
              <Link href={`/app/quizzes/${currentLesson.id}`}>
                <Button variant="primary" size="lg">
                  Open Quiz Assessment
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </Card>
        ) : currentLesson.lesson_type === "ASSIGNMENT" ? (
          <Card className="p-6 sm:p-10 text-center space-y-4 max-w-2xl mx-auto border border-accent-coral/20 bg-accent-peach/30">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-peach text-accent-coral mx-auto">
              <CheckSquare className="h-7 w-7" />
            </div>
            <h2 className="font-heading text-xl sm:text-2xl font-bold text-slate-900">
              Hands-On Project Assignment
            </h2>
            <p className="font-sans text-sm text-slate-600 max-w-md mx-auto">
              Review project guidelines, complete the required implementation, and submit your project for rubric grading.
            </p>
            <div className="pt-2">
              <Link href={`/app/assignments/${currentLesson.id}`}>
                <Button variant="primary" size="lg">
                  View Assignment & Submit
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </Card>
        ) : null}

        {/* Protected PDF Viewer if attached */}
        {pdfResource && (
          <div className="space-y-3 pt-6 border-t border-slate-200">
            <h3 className="font-heading text-base font-bold text-slate-900">
              Lesson Document Resource
            </h3>
            <ProtectedPdfViewer
              mediaId={pdfResource.id}
              lessonId={currentLesson.id}
              title={pdfResource.title}
            />
          </div>
        )}
      </div>

      {/* Desktop Fixed Curriculum Sidebar */}
      <aside className="hidden lg:block w-80 shrink-0 h-full">
        <CurriculumSidebar
          course={course}
          currentLessonId={currentLesson.id}
          completedLessonIds={completedLessonIds}
        />
      </aside>

      {/* Mobile Slide-Out Curriculum Drawer */}
      {isMobileSidebarOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs"
            onClick={() => setIsMobileSidebarOpen(false)}
          />
          <div className="relative ml-auto flex h-full w-full max-w-xs flex-col bg-white shadow-xl">
            <CurriculumSidebar
              course={course}
              currentLessonId={currentLesson.id}
              completedLessonIds={completedLessonIds}
              onCloseMobile={() => setIsMobileSidebarOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
