"use client";

import React, { useState } from "react";
import { CheckCircle2, Circle, Clock, BookOpen } from "lucide-react";
import { progressApi } from "@/lib/api/progress";
import { Button } from "@/components/ui/Button";

interface ArticleReaderProps {
  lessonId: string;
  title: string;
  content?: Record<string, unknown> | null;
  isCompletedInitially?: boolean;
  onCompleted?: () => void;
}

export const ArticleReader: React.FC<ArticleReaderProps> = ({
  lessonId,
  title,
  content,
  isCompletedInitially = false,
  onCompleted,
}) => {
  const [isCompleted, setIsCompleted] = useState(isCompletedInitially);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Extract text or markdown from content dictionary
  const rawText =
    typeof content?.body === "string"
      ? content.body
      : typeof content?.text === "string"
      ? content.text
      : typeof content?.markdown === "string"
      ? content.markdown
      : "";

  const handleToggleComplete = async () => {
    setIsSubmitting(true);
    try {
      const targetState = !isCompleted;
      const res = await progressApi.recordLessonProgress(lessonId, {
        watch_position_seconds: 0,
        is_completed: targetState,
      });
      setIsCompleted(res.is_completed);
      if (res.is_completed) {
        onCompleted?.();
      }
    } catch (err) {
      console.error("Failed to update lesson completion status:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <article className="rounded-[16px] border border-slate-200 bg-white p-6 sm:p-10 shadow-card space-y-6">
      <div className="border-b border-slate-100 pb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="font-mono text-xs uppercase tracking-wider text-primary-teal font-semibold">
            Article Lesson
          </span>
          <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900 mt-1">
            {title}
          </h1>
        </div>

        <Button
          variant={isCompleted ? "secondary" : "primary"}
          size="default"
          onClick={handleToggleComplete}
          disabled={isSubmitting}
          className="shrink-0"
        >
          {isCompleted ? (
            <>
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Completed
            </>
          ) : (
            <>
              <Circle className="mr-2 h-4 w-4" />
              Mark as Complete
            </>
          )}
        </Button>
      </div>

      <div className="prose prose-slate max-w-none text-slate-800 leading-relaxed font-sans text-base">
        {rawText ? (
          <div className="whitespace-pre-wrap">{rawText}</div>
        ) : (
          <div className="p-8 rounded-[12px] bg-slate-50 text-center text-slate-500 font-sans">
            <BookOpen className="h-8 w-8 mx-auto text-slate-400 mb-2" />
            <p className="text-sm">
              This reading lesson contains supplementary guidance and reference material. Review the lesson instructions and attached resources.
            </p>
          </div>
        )}
      </div>

      <div className="border-t border-slate-100 pt-6 flex justify-end">
        <Button
          variant={isCompleted ? "secondary" : "primary"}
          size="default"
          onClick={handleToggleComplete}
          disabled={isSubmitting}
        >
          {isCompleted ? (
            <>
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Completed
            </>
          ) : (
            <>
              <Circle className="mr-2 h-4 w-4" />
              Mark as Complete
            </>
          )}
        </Button>
      </div>
    </article>
  );
};
