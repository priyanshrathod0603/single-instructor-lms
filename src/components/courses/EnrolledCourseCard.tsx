"use client";

import React from "react";
import Link from "next/link";
import { BookOpen, CheckCircle, PlayCircle, ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { EnrollmentResponse } from "@/types/enrollment";
import { progressApi } from "@/lib/api/progress";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface EnrolledCourseCardProps {
  enrollment: EnrollmentResponse;
}

export const EnrolledCourseCard: React.FC<EnrolledCourseCardProps> = ({
  enrollment,
}) => {
  const { data: progress, isLoading: isProgressLoading } = useQuery({
    queryKey: ["course-progress", enrollment.course_id],
    queryFn: () => progressApi.getCourseProgress(enrollment.course_id),
    staleTime: 30_000,
  });

  const percentage = progress ? Math.round(Number(progress.progress_percentage)) : 0;
  const isFinished = progress?.is_completed ?? false;

  return (
    <Card className="flex flex-col justify-between overflow-hidden border border-slate-200/80 bg-white shadow-card transition-all duration-200 hover:-translate-y-1 hover:shadow-card-hover">
      <div className="p-5 sm:p-6">
        <div className="flex items-center justify-between gap-2 mb-3">
          <Badge
            variant={isFinished ? "mint" : "outline"}
            size="sm"
            className="flex items-center gap-1 font-medium"
          >
            {isFinished ? (
              <>
                <CheckCircle className="h-3 w-3 text-primary-teal" />
                Completed
              </>
            ) : (
              <>
                <PlayCircle className="h-3 w-3 text-slate-500" />
                In Progress
              </>
            )}
          </Badge>
          <span className="font-mono text-xs text-slate-400">
            Enrolled {new Date(enrollment.granted_at).toLocaleDateString()}
          </span>
        </div>

        <h3 className="font-heading text-lg font-bold text-slate-900 line-clamp-2">
          {enrollment.course_title || "Enrolled Course"}
        </h3>

        {/* Progress bar */}
        <div className="mt-4 space-y-1.5">
          <div className="flex items-center justify-between text-xs font-sans text-slate-600">
            <span>Course Progress</span>
            <span className="font-semibold text-slate-900">
              {isProgressLoading ? "..." : `${percentage}%`}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
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

      <div className="border-t border-slate-100 bg-slate-50/50 p-4 sm:px-6 flex items-center justify-between">
        <Link
          href={`/app/courses/${enrollment.course_id}`}
          className="text-xs font-semibold text-slate-700 hover:text-primary-teal hover:underline"
        >
          View Syllabus
        </Link>
        <Link href={`/app/courses/${enrollment.course_id}`}>
          <Button variant="primary" size="sm" className="min-h-[36px]">
            <span>{isFinished ? "Review Course" : "Continue Learning"}</span>
            <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
          </Button>
        </Link>
      </div>
    </Card>
  );
};
