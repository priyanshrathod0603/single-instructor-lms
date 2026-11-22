"use client";

import React from "react";
import Link from "next/link";
import {
  CheckCircle,
  Circle,
  PlayCircle,
  FileText,
  HelpCircle,
  CheckSquare,
  ChevronDown,
  X,
} from "lucide-react";
import { CourseDetail, CurriculumLesson } from "@/types/course";
import { cn } from "@/lib/utils";

interface CurriculumSidebarProps {
  course: CourseDetail;
  currentLessonId: string;
  completedLessonIds: Set<string>;
  onCloseMobile?: () => void;
}

export const CurriculumSidebar: React.FC<CurriculumSidebarProps> = ({
  course,
  currentLessonId,
  completedLessonIds,
  onCloseMobile,
}) => {
  const getLessonIcon = (type: string, isCurrent: boolean) => {
    const iconClass = cn("h-4 w-4 shrink-0", isCurrent ? "text-primary-teal" : "text-slate-400");
    switch (type) {
      case "VIDEO":
        return <PlayCircle className={iconClass} />;
      case "ARTICLE":
        return <FileText className={iconClass} />;
      case "QUIZ":
        return <HelpCircle className={iconClass} />;
      case "ASSIGNMENT":
        return <CheckSquare className={iconClass} />;
      default:
        return <FileText className={iconClass} />;
    }
  };

  return (
    <div className="flex h-full flex-col bg-white border-l border-slate-200">
      {/* Sidebar Header */}
      <div className="flex items-center justify-between border-b border-slate-200 p-4">
        <div>
          <span className="font-mono text-xs font-semibold text-primary-teal uppercase tracking-wider">
            Curriculum
          </span>
          <h2 className="font-heading text-sm font-bold text-slate-900 line-clamp-1">
            {course.title}
          </h2>
        </div>
        {onCloseMobile && (
          <button
            onClick={onCloseMobile}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 lg:hidden"
            aria-label="Close Curriculum Drawer"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Sections and Lessons List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
        {course.curriculum?.map((section, sectionIdx) => (
          <div key={section.id} className="py-2">
            <div className="px-4 py-2 font-heading text-xs font-bold text-slate-500 uppercase tracking-wider">
              Section {sectionIdx + 1}: {section.title}
            </div>

            <div className="space-y-0.5">
              {section.lessons?.map((lesson) => {
                const isCurrent = lesson.id === currentLessonId;
                const isCompleted = completedLessonIds.has(lesson.id);

                return (
                  <Link
                    key={lesson.id}
                    href={`/learn/${course.id}/${lesson.id}`}
                    onClick={() => onCloseMobile?.()}
                    className={cn(
                      "flex items-center justify-between px-4 py-2.5 text-xs transition-colors",
                      isCurrent
                        ? "bg-primary-teal/10 font-bold text-primary-teal border-r-4 border-primary-teal"
                        : "text-slate-700 hover:bg-slate-50 font-medium"
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      {isCompleted ? (
                        <CheckCircle className="h-4 w-4 text-primary-teal shrink-0" />
                      ) : (
                        <Circle className="h-4 w-4 text-slate-300 shrink-0" />
                      )}
                      {getLessonIcon(lesson.lesson_type, isCurrent)}
                      <span className="truncate">{lesson.title}</span>
                    </div>

                    {lesson.duration_seconds > 0 && (
                      <span className="font-mono text-[10px] text-slate-400 shrink-0 ml-2">
                        {Math.round(lesson.duration_seconds / 60)}m
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
