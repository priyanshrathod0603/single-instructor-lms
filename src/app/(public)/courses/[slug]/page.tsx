"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Clock,
  PlayCircle,
  FileText,
  HelpCircle,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Award,
  Video,
  FileCheck,
  ChevronLeft,
  Lock,
} from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { resolveApiAssetUrl } from "@/lib/api/client";
import { CourseDetail, CurriculumSection, CurriculumLesson } from "@/types/course";
import { useAuth } from "@/lib/hooks/useAuth";
import { formatCurrency } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { EmptyState } from "@/components/feedback/EmptyState";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/Accordion";

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "5 min";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function getLessonIcon(lessonType: string) {
  switch (lessonType.toUpperCase()) {
    case "VIDEO":
      return <Video className="h-4 w-4 text-primary-teal" />;
    case "ARTICLE":
      return <FileText className="h-4 w-4 text-amber-600" />;
    case "QUIZ":
      return <HelpCircle className="h-4 w-4 text-purple-600" />;
    case "ASSIGNMENT":
      return <FileCheck className="h-4 w-4 text-accent-coral" />;
    default:
      return <PlayCircle className="h-4 w-4 text-primary-teal" />;
  }
}

export default function CourseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;
  const { isAuthenticated } = useAuth();
  const [imageError, setImageError] = useState(false);

  const { data: course, isLoading, isError, error, refetch } = useQuery<CourseDetail>({
    queryKey: ["courseDetail", slug],
    queryFn: () => coursesApi.getCourseDetail(slug),
    enabled: Boolean(slug),
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center gap-2 text-sm text-slate-400">
          <Skeleton className="h-4 w-16" />
          <span>/</span>
          <Skeleton className="h-4 w-32" />
        </div>
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-12 w-3/4" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-40 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
          <div className="lg:col-span-1">
            <Skeleton className="h-96 w-full rounded-2xl" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !course) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 lg:px-8">
        <ErrorAlert
          title="Course Not Found"
          message={
            error instanceof Error
              ? error.message
              : "The requested course could not be found or is not currently published."
          }
        />
        <div className="mt-8 flex justify-center gap-4">
          <Button variant="outline" onClick={() => router.push("/courses")}>
            <ChevronLeft className="mr-2 h-4 w-4" />
            Back to Courses
          </Button>
          <Button variant="primary" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // Calculate totals
  const totalSections = course.curriculum?.length || 0;
  const totalLessons =
    course.curriculum?.reduce(
      (acc, sec) => acc + (sec.lessons?.length || 0),
      0
    ) || 0;
  const totalSeconds =
    course.curriculum?.reduce(
      (secAcc, sec) =>
        secAcc +
        (sec.lessons?.reduce((lesAcc, les) => lesAcc + (les.duration_seconds || 0), 0) || 0),
      0
    ) || 0;

  // Primary action button destination
  const checkoutHref = isAuthenticated
    ? `/app`
    : `/signup?redirect=/courses/${course.slug || course.id}`;

  return (
    <div className="relative pb-24 lg:pb-16">
      {/* Course Hero Banner */}
      <section className="border-b border-soft-peach/60 bg-gradient-to-b from-warm-cream via-white to-warm-cream/30 py-8 sm:py-12 lg:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Breadcrumbs */}
          <nav className="mb-6 flex items-center gap-2 text-xs sm:text-sm font-medium text-slate-500">
            <Link
              href="/courses"
              className="hover:text-primary-teal transition-colors flex items-center gap-1"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Courses
            </Link>
            <span>/</span>
            <span className="text-slate-800 truncate max-w-xs sm:max-w-md">
              {course.title}
            </span>
          </nav>

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3 lg:gap-12">
            {/* Left Header Content */}
            <div className="lg:col-span-2 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {course.is_free ? (
                  <Badge variant="mint" size="md">
                    FREE MASTERCLASS
                  </Badge>
                ) : (
                  <Badge variant="teal" size="md">
                    PROFESSIONAL TRACK
                  </Badge>
                )}
                {course.tags?.map((tag) => (
                  <Badge key={tag} variant="outline" size="sm">
                    {tag}
                  </Badge>
                ))}
              </div>

              <h1 className="font-heading text-[clamp(1.75rem,2.8vw+0.75rem,2.75rem)] font-extrabold tracking-tight text-slate-900 leading-tight text-balance">
                {course.title}
              </h1>

              {course.headline && (
                <p className="font-sans text-base text-slate-700 sm:text-lg lg:text-xl leading-relaxed text-balance">
                  {course.headline}
                </p>
              )}

              {/* Course Meta stats */}
              <div className="flex flex-wrap items-center gap-4 pt-2 text-xs sm:text-sm text-slate-700 font-medium font-sans">
                <div className="flex items-center gap-1.5">
                  <BookOpen className="h-4 w-4 text-primary-teal" />
                  <span>
                    <strong className="text-slate-900">{totalSections}</strong> {totalSections === 1 ? "Section" : "Sections"}
                  </span>
                </div>
                <div className="h-3.5 w-px bg-slate-300" />
                <div className="flex items-center gap-1.5">
                  <PlayCircle className="h-4 w-4 text-primary-teal" />
                  <span>
                    <strong className="text-slate-900">{totalLessons}</strong> Lessons
                  </span>
                </div>
                {totalSeconds > 0 && (
                  <>
                    <div className="h-3.5 w-px bg-slate-300" />
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-4 w-4 text-primary-teal" />
                      <span>{formatDuration(totalSeconds)} total content</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Right Desktop CTA Floating Card */}
            <div className="hidden lg:block lg:col-span-1">
              <div className="sticky top-24 rounded-2xl border border-soft-peach bg-white p-6 shadow-elevated">
                {/* 16:9 Thumbnail Header */}
                <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-slate-100 mb-6">
                  {(() => {
                    const thumbnailSrc = resolveApiAssetUrl(course.thumbnail_url);
                    return thumbnailSrc && !imageError ? (
                      <Image
                        src={thumbnailSrc}
                        alt={course.title}
                        fill
                        sizes="400px"
                        className="object-cover"
                        onError={() => setImageError(true)}
                        unoptimized={thumbnailSrc.startsWith("http") || thumbnailSrc.includes("/api/v1/media/public/")}
                      />
                    ) : (
                      <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-primary-teal/15 via-accent-mint/30 to-soft-peach/40">
                        <BookOpen className="h-10 w-10 text-primary-teal" />
                      </div>
                    );
                  })()}
                </div>

                {/* Price Display */}
                <div className="mb-6 space-y-1">
                  <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">
                    Tuition
                  </span>
                  <div className="font-heading text-3xl font-extrabold text-slate-900">
                    {course.is_free
                      ? "Free Access"
                      : formatCurrency(course.price_inr, "INR")}
                  </div>
                  <p className="text-xs text-slate-500 font-sans">
                    {course.is_free
                      ? "Full access to all course materials & community"
                      : "One-time enrollment. Full lifetime access & future updates."}
                  </p>
                </div>

                {/* Enrollment CTA */}
                <div className="space-y-3">
                  <Link href={checkoutHref} className="block w-full">
                    <Button variant="primary" size="lg" className="w-full">
                      {course.is_free ? "Enroll for Free" : "Enroll Now"}
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </Link>

                  <div className="pt-4 border-t border-soft-peach/60 space-y-2.5 text-xs text-slate-600 font-sans">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-primary-teal shrink-0" />
                      <span>Direct rubric evaluation on assignments</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Award className="h-4 w-4 text-amber-600 shrink-0" />
                      <span>Cryptographically verifiable certificate</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-primary-teal shrink-0" />
                      <span>Self-paced access from desktop & mobile</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Body: Syllabus & Details */}
      <section className="py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-12">
              {/* Description Section */}
              {course.description && (
                <div className="space-y-4">
                  <h2 className="font-heading text-2xl font-bold text-slate-900">
                    Course Overview
                  </h2>
                  <div className="prose prose-slate max-w-none font-sans text-sm sm:text-base text-slate-600 leading-relaxed whitespace-pre-line">
                    {course.description}
                  </div>
                </div>
              )}

              {/* Curriculum Syllabus Section */}
              <div className="space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <h2 className="font-heading text-2xl font-bold text-slate-900">
                    Curriculum Syllabus
                  </h2>
                  <span className="text-xs sm:text-sm font-sans text-slate-500">
                    {totalSections} {totalSections === 1 ? "Section" : "Sections"} • {totalLessons} Lessons
                  </span>
                </div>

                {course.curriculum && course.curriculum.length > 0 ? (
                  <Accordion
                    type="multiple"
                    defaultValue={course.curriculum.map((s) => s.id)}
                    className="space-y-3"
                  >
                    {course.curriculum.map((section, secIdx) => (
                      <AccordionItem
                        key={section.id}
                        value={section.id}
                        className="rounded-xl border border-soft-peach bg-white px-5 shadow-subtle overflow-hidden"
                      >
                        <AccordionTrigger className="hover:no-underline py-4">
                          <div className="flex items-center gap-3 text-left">
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent-mint/50 text-xs font-bold text-primary-teal">
                              {secIdx + 1}
                            </span>
                            <div>
                              <span className="font-heading text-base font-bold text-slate-900 block">
                                {section.title}
                              </span>
                              {section.description && (
                                <span className="text-xs font-normal text-slate-500 line-clamp-1">
                                  {section.description}
                                </span>
                              )}
                            </div>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="divide-y divide-soft-peach/50 pt-1">
                            {section.lessons && section.lessons.length > 0 ? (
                              section.lessons.map((lesson, lesIdx) => (
                                <div
                                  key={lesson.id}
                                  className="flex items-center justify-between py-3 text-xs sm:text-sm font-sans"
                                >
                                  <div className="flex items-center gap-3">
                                    <div className="flex h-6 w-6 items-center justify-center rounded text-slate-500">
                                      {getLessonIcon(lesson.lesson_type)}
                                    </div>
                                    <span className="font-medium text-slate-800">
                                      {lesson.title}
                                    </span>
                                    {lesson.is_preview && (
                                      <Badge variant="mint" size="sm" className="text-[10px]">
                                        Preview
                                      </Badge>
                                    )}
                                  </div>

                                  <div className="flex items-center gap-2 text-slate-400">
                                    <span>{formatDuration(lesson.duration_seconds)}</span>
                                    {!lesson.is_preview && !isAuthenticated && (
                                      <Lock className="h-3.5 w-3.5 text-slate-300" />
                                    )}
                                  </div>
                                </div>
                              ))
                            ) : (
                              <div className="py-3 text-xs text-slate-400 italic">
                                Lesson list coming soon.
                              </div>
                            )}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                ) : (
                  <Card className="p-8 text-center text-slate-500">
                    <BookOpen className="mx-auto h-8 w-8 text-primary-teal/50 mb-2" />
                    <p className="text-sm font-sans">
                      The detailed syllabus for this masterclass will be announced shortly.
                    </p>
                  </Card>
                )}
              </div>

              {/* Single-Instructor Guarantee Box */}
              <div className="rounded-2xl border border-soft-peach bg-accent-mint/20 p-6 sm:p-8 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-teal text-white shadow-sm">
                    <Sparkles className="h-6 w-6" />
                  </div>
                  <div>
                    <h3 className="font-heading text-lg font-bold text-slate-900">
                      Direct Expert Instruction Guarantee
                    </h3>
                    <p className="font-sans text-xs sm:text-sm text-slate-600">
                      Every lecture, assignment rubric, and code repository is personally authored.
                    </p>
                  </div>
                </div>
                <p className="font-sans text-sm text-slate-700 leading-relaxed">
                  Unlike multi-instructor marketplaces with fragmented standards, you receive cohesive,
                  opinionated architectural guidance from day one. Get direct feedback on code submissions
                  and work towards an industry-standard portfolio.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Mobile Sticky Bottom Enrollment Bar (< lg viewports) */}
      <div className="fixed bottom-0 inset-x-0 z-30 block lg:hidden border-t border-soft-peach bg-white/95 backdrop-blur-md px-4 py-3 shadow-elevated">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div>
            <span className="block text-[11px] uppercase tracking-wider font-semibold text-slate-400">
              Tuition
            </span>
            <span className="font-heading text-xl font-extrabold text-slate-900">
              {course.is_free
                ? "Free Access"
                : formatCurrency(course.price_inr, "INR")}
            </span>
          </div>
          <Link href={checkoutHref} className="shrink-0">
            <Button variant="primary" size="default">
              {course.is_free ? "Enroll for Free" : "Enroll Now"}
              <ArrowRight className="ml-1.5 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
