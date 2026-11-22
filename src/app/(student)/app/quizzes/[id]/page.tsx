"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Clock,
  HelpCircle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Send,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { quizzesApi } from "@/lib/api/quizzes";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import {
  QuizResponse,
  QuizAttemptStartResponse,
  QuizAttemptResultResponse,
  QuestionResponse,
} from "@/types/quiz";

export default function QuizExecutionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const rawId = params?.id as string;
  const initialAttemptId = searchParams?.get("attempt_id");

  // State machine: PREFLIGHT | IN_PROGRESS | COMPLETED
  const [activeAttempt, setActiveAttempt] = useState<QuizAttemptStartResponse | null>(null);
  const [completedResult, setCompletedResult] = useState<QuizAttemptResultResponse | null>(null);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

  // Student answers state: questionId -> { selected_option_ids: string[], text_response?: string }
  const [answersState, setAnswersState] = useState<
    Record<string, { selectedOptionIds: string[]; textResponse: string }>
  >({});
  const [autosaveStatus, setAutosaveStatus] = useState<"IDLE" | "SAVING" | "SAVED">("IDLE");

  // Server countdown timer state
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Fetch Quiz Configuration (supports quiz ID or lesson ID)
  const {
    data: quiz,
    isLoading: isQuizLoading,
    isError: isQuizError,
    error: quizError,
    refetch: refetchQuiz,
  } = useQuery<QuizResponse>({
    queryKey: ["quiz-config", rawId],
    queryFn: async () => {
      try {
        return await quizzesApi.getQuiz(rawId);
      } catch {
        return await quizzesApi.getLessonQuiz(rawId);
      }
    },
    enabled: !!rawId && !initialAttemptId,
  });

  // 2. Fetch Initial Attempt Result if reviewing past attempt
  const {
    data: initialResult,
    isLoading: isInitialResultLoading,
  } = useQuery({
    queryKey: ["quiz-attempt-result", initialAttemptId],
    queryFn: () => (initialAttemptId ? quizzesApi.getAttemptResult(initialAttemptId) : null),
    enabled: !!initialAttemptId,
  });

  useEffect(() => {
    if (initialResult) {
      setCompletedResult(initialResult);
    }
  }, [initialResult]);

  // 3. Start Quiz Attempt Mutation
  const startAttemptMutation = useMutation({
    mutationFn: async () => {
      if (!quiz?.id) throw new Error("Quiz configuration not loaded");
      return await quizzesApi.startQuizAttempt(quiz.id);
    },
    onSuccess: (data) => {
      setActiveAttempt(data);
      setCurrentQuestionIndex(0);
      setCompletedResult(null);

      // Initialize answers state
      const initialAnswers: Record<string, { selectedOptionIds: string[]; textResponse: string }> = {};
      data.questions.forEach((q) => {
        initialAnswers[q.id] = { selectedOptionIds: [], textResponse: "" };
      });
      setAnswersState(initialAnswers);

      // Start authoritative countdown timer from server_deadline
      if (data.server_deadline) {
        const deadlineMs = new Date(data.server_deadline).getTime();
        const diffSeconds = Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000));
        setSecondsRemaining(diffSeconds);
      } else if (data.time_limit_minutes > 0) {
        setSecondsRemaining(data.time_limit_minutes * 60);
      }
    },
  });

  // 4. Autosave Mutation
  const autosaveMutation = useMutation({
    mutationFn: async ({
      questionId,
      selectedOptionIds,
      textResponse,
    }: {
      questionId: string;
      selectedOptionIds?: string[];
      textResponse?: string;
    }) => {
      if (!activeAttempt) return;
      setAutosaveStatus("SAVING");
      return await quizzesApi.autosaveAnswer(activeAttempt.attempt_id, {
        question_id: questionId,
        selected_option_ids: selectedOptionIds,
        text_response: textResponse,
      });
    },
    onSuccess: () => {
      setAutosaveStatus("SAVED");
      setTimeout(() => setAutosaveStatus("IDLE"), 2000);
    },
    onError: () => {
      setAutosaveStatus("IDLE");
    },
  });

  // 5. Submit Quiz Mutation
  const submitAttemptMutation = useMutation({
    mutationFn: async () => {
      if (!activeAttempt) throw new Error("No active attempt to submit");
      return await quizzesApi.submitQuizAttempt(activeAttempt.attempt_id);
    },
    onSuccess: (result) => {
      setActiveAttempt(null);
      setCompletedResult(result);
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    },
  });

  // Timer countdown loop
  useEffect(() => {
    if (activeAttempt && secondsRemaining !== null) {
      timerIntervalRef.current = setInterval(() => {
        setSecondsRemaining((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timerIntervalRef.current!);
            // Auto-submit on expiration
            submitAttemptMutation.mutate();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, [activeAttempt]);

  const handleOptionSelect = (questionId: string, optionId: string, isMulti: boolean) => {
    setAnswersState((prev) => {
      const current = prev[questionId] || { selectedOptionIds: [], textResponse: "" };
      let updatedIds: string[];

      if (isMulti) {
        if (current.selectedOptionIds.includes(optionId)) {
          updatedIds = current.selectedOptionIds.filter((id) => id !== optionId);
        } else {
          updatedIds = [...current.selectedOptionIds, optionId];
        }
      } else {
        updatedIds = [optionId];
      }

      const updated = {
        ...prev,
        [questionId]: {
          ...current,
          selectedOptionIds: updatedIds,
        },
      };

      // Trigger debounced autosave
      autosaveMutation.mutate({
        questionId,
        selectedOptionIds: updatedIds,
      });

      return updated;
    });
  };

  const handleTextResponseChange = (questionId: string, text: string) => {
    setAnswersState((prev) => {
      const current = prev[questionId] || { selectedOptionIds: [], textResponse: "" };
      const updated = {
        ...prev,
        [questionId]: {
          ...current,
          textResponse: text,
        },
      };

      // Trigger autosave
      autosaveMutation.mutate({
        questionId,
        textResponse: text,
      });

      return updated;
    });
  };

  // Format seconds mm:ss
  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainder = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
  };

  // Render Loading
  if (isQuizLoading || isInitialResultLoading) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-10 w-3/4" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  // =========================================================================
  // VIEW 1: COMPLETED RESULT VIEW
  // =========================================================================
  if (completedResult) {
    const isPassed = completedResult.is_passed === true;

    return (
      <div className="space-y-8 max-w-3xl mx-auto">
        <Link
          href="/app/quizzes"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Quiz History
        </Link>

        {/* Score Banner */}
        <Card
          className={`p-6 sm:p-8 text-center space-y-4 border ${
            isPassed ? "border-emerald-200 bg-emerald-50/60" : "border-rose-200 bg-rose-50/60"
          }`}
        >
          <div
            className={`flex h-16 w-16 items-center justify-center rounded-full mx-auto ${
              isPassed ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
            }`}
          >
            {isPassed ? <CheckCircle2 className="h-8 w-8" /> : <XCircle className="h-8 w-8" />}
          </div>

          <div>
            <Badge variant={isPassed ? "mint" : "error"} size="md" className="text-sm">
              {isPassed ? "ASSESSMENT PASSED" : "ASSESSMENT NOT PASSED"}
            </Badge>
            <h1 className="font-heading text-3xl font-extrabold text-slate-900 mt-2">
              Score: {completedResult.score ?? 0}%
            </h1>
            <p className="font-sans text-sm text-slate-600 mt-1">
              Required passing threshold: {completedResult.pass_percentage}%
            </p>
          </div>

          {quiz && (
            <div className="pt-2 flex justify-center">
              <Button
                variant="primary"
                onClick={() => {
                  setCompletedResult(null);
                  startAttemptMutation.mutate();
                }}
                isLoading={startAttemptMutation.isPending}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                Retake Quiz Assessment
              </Button>
            </div>
          )}
        </Card>

        {/* Detailed Question Review Breakdown */}
        {completedResult.answers && completedResult.answers.length > 0 && (
          <div className="space-y-4">
            <h2 className="font-heading text-lg font-bold text-slate-900">
              Question Breakdown & Explanations
            </h2>

            {completedResult.answers.map((answer, idx) => (
              <Card key={answer.question_id} className="p-5 sm:p-6 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold text-slate-500">
                    Question {idx + 1} • {answer.question_type}
                  </span>
                  <Badge variant={answer.is_correct ? "mint" : "error"} size="sm">
                    {answer.is_correct ? "Correct" : "Incorrect"} ({answer.points_earned ?? 0} /{" "}
                    {answer.points_possible} pts)
                  </Badge>
                </div>

                <p className="font-heading text-sm sm:text-base font-bold text-slate-900">
                  {answer.prompt}
                </p>

                {/* Options Review */}
                {answer.options && (
                  <div className="space-y-1.5 pt-1">
                    {answer.options.map((opt) => {
                      const isSelected = answer.selected_option_ids?.includes(opt.id);
                      const isCorrectOption = opt.is_correct === true;

                      return (
                        <div
                          key={opt.id}
                          className={`flex items-center justify-between p-2.5 rounded-lg border text-xs sm:text-sm font-sans ${
                            isCorrectOption
                              ? "border-emerald-300 bg-emerald-50 text-emerald-950 font-semibold"
                              : isSelected
                              ? "border-rose-300 bg-rose-50 text-rose-950"
                              : "border-slate-200 bg-white text-slate-700"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {isSelected && <span className="text-xs">Your choice:</span>}
                            <span>{opt.option_text}</span>
                          </div>
                          {isCorrectOption && (
                            <span className="text-xs font-semibold text-emerald-700">
                              ✓ Correct Answer
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Pedagogical Explanation */}
                {answer.explanation && (
                  <div className="rounded-lg bg-slate-50 p-3 border border-slate-200 text-xs text-slate-700 space-y-1">
                    <span className="font-semibold text-slate-900 block">Explanation:</span>
                    <p>{answer.explanation}</p>
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  // =========================================================================
  // VIEW 2: ACTIVE IN-PROGRESS EXAM CANVAS
  // =========================================================================
  if (activeAttempt) {
    const questions = activeAttempt.questions || [];
    const currentQuestion: QuestionResponse | undefined = questions[currentQuestionIndex];

    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        {/* Sticky Server Countdown & Autosave Header */}
        <div className="sticky top-14 z-30 flex items-center justify-between rounded-[12px] border border-slate-200 bg-white/95 backdrop-blur-sm p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Clock
              className={`h-5 w-5 ${
                secondsRemaining && secondsRemaining < 300
                  ? "text-rose-600 animate-pulse"
                  : "text-primary-teal"
              }`}
            />
            <span className="font-heading text-base font-bold text-slate-900">
              {secondsRemaining !== null ? formatTime(secondsRemaining) : "Untimed"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-slate-500">
              {autosaveStatus === "SAVING" ? (
                "Saving answer..."
              ) : autosaveStatus === "SAVED" ? (
                <span className="text-emerald-600 flex items-center gap-1">
                  <Check className="h-3 w-3" /> Autosaved
                </span>
              ) : (
                "All answers recorded"
              )}
            </span>

            <Button
              variant="primary"
              size="sm"
              onClick={() => submitAttemptMutation.mutate()}
              isLoading={submitAttemptMutation.isPending}
            >
              <Send className="mr-1.5 h-3.5 w-3.5" />
              Finish & Submit
            </Button>
          </div>
        </div>

        {/* Question Canvas */}
        {currentQuestion ? (
          <Card className="p-6 sm:p-8 space-y-6 border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <span className="font-mono text-xs font-semibold text-primary-teal uppercase tracking-wider">
                Question {currentQuestionIndex + 1} of {questions.length}
              </span>
              <Badge variant="outline" size="sm">
                {currentQuestion.points} {currentQuestion.points === 1 ? "point" : "points"}
              </Badge>
            </div>

            <h2 className="font-heading text-lg sm:text-xl font-bold text-slate-900 leading-snug">
              {currentQuestion.prompt}
            </h2>

            {/* MCQ Options */}
            {currentQuestion.options && currentQuestion.options.length > 0 ? (
              <div className="space-y-2.5">
                {currentQuestion.options.map((option) => {
                  const isMulti = currentQuestion.question_type === "MCQ_MULTI";
                  const selectedIds =
                    answersState[currentQuestion.id]?.selectedOptionIds || [];
                  const isSelected = selectedIds.includes(option.id);

                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() =>
                        handleOptionSelect(currentQuestion.id, option.id, isMulti)
                      }
                      className={`flex w-full items-center justify-between rounded-[10px] border p-4 text-left transition-all ${
                        isSelected
                          ? "border-primary-teal bg-primary-teal/5 text-slate-900 ring-1 ring-primary-teal font-medium"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <span className="font-sans text-sm sm:text-base">
                        {option.option_text}
                      </span>
                      <div
                        className={`flex h-5 w-5 shrink-0 items-center justify-center border transition-colors ${
                          isMulti ? "rounded" : "rounded-full"
                        } ${
                          isSelected
                            ? "border-primary-teal bg-primary-teal text-white"
                            : "border-slate-300 bg-white"
                        }`}
                      >
                        {isSelected && <Check className="h-3 w-3 stroke-[3]" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              /* Short Text Question */
              <div className="space-y-2">
                <label className="font-sans text-xs font-medium text-slate-700">
                  Your Answer:
                </label>
                <input
                  type="text"
                  value={answersState[currentQuestion.id]?.textResponse || ""}
                  onChange={(e) =>
                    handleTextResponseChange(currentQuestion.id, e.target.value)
                  }
                  placeholder="Type your brief response..."
                  className="w-full rounded-[10px] border border-slate-300 p-3 text-sm focus:border-primary-teal focus:outline-hidden focus:ring-1 focus:ring-primary-teal"
                />
              </div>
            )}

            {/* Question Step Controls */}
            <div className="flex items-center justify-between border-t border-slate-100 pt-6">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentQuestionIndex((prev) => Math.max(0, prev - 1))}
                disabled={currentQuestionIndex === 0}
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Previous
              </Button>

              {/* Navigation Dot Pills */}
              <div className="hidden sm:flex items-center gap-1.5">
                {questions.map((q, idx) => {
                  const hasAnswer =
                    (answersState[q.id]?.selectedOptionIds?.length || 0) > 0 ||
                    !!answersState[q.id]?.textResponse?.trim();

                  return (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => setCurrentQuestionIndex(idx)}
                      className={`h-7 w-7 rounded-full text-xs font-bold transition-all ${
                        idx === currentQuestionIndex
                          ? "bg-primary-teal text-white ring-2 ring-primary-teal/40"
                          : hasAnswer
                          ? "bg-accent-mint text-primary-teal font-semibold"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {idx + 1}
                    </button>
                  );
                })}
              </div>

              {currentQuestionIndex < questions.length - 1 ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    setCurrentQuestionIndex((prev) =>
                      Math.min(questions.length - 1, prev + 1)
                    )
                  }
                >
                  Next
                  <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => submitAttemptMutation.mutate()}
                  isLoading={submitAttemptMutation.isPending}
                >
                  Submit Assessment
                </Button>
              )}
            </div>
          </Card>
        ) : null}
      </div>
    );
  }

  // =========================================================================
  // VIEW 3: PRE-FLIGHT INSTRUCTIONS VIEW
  // =========================================================================
  if (isQuizError || !quiz) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <Link
          href="/app/quizzes"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Quizzes
        </Link>
        <ErrorAlert
          title="Quiz Not Available"
          message={
            quizError?.message ||
            "The requested quiz assessment could not be found or you are not enrolled."
          }
          onRetry={() => refetchQuiz()}
        />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      <div>
        <Link
          href="/app/quizzes"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Quizzes
        </Link>
      </div>

      <Card className="p-6 sm:p-10 text-center space-y-6 border border-slate-200 bg-white">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent-mint/60 text-primary-teal mx-auto">
          <HelpCircle className="h-8 w-8" />
        </div>

        <div className="space-y-2">
          <Badge variant="outline" size="sm">
            Curriculum Knowledge Assessment
          </Badge>
          <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-slate-900">
            {quiz.title}
          </h1>
          {quiz.description && (
            <p className="font-sans text-sm sm:text-base text-slate-600 max-w-lg mx-auto">
              {quiz.description}
            </p>
          )}
        </div>

        {/* Assessment Parameters Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-center">
          <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
            <span className="font-mono text-xs text-slate-400 block">Time Limit</span>
            <span className="font-heading text-base font-bold text-slate-900">
              {quiz.time_limit_minutes > 0 ? `${quiz.time_limit_minutes} mins` : "Untimed"}
            </span>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
            <span className="font-mono text-xs text-slate-400 block">Pass Threshold</span>
            <span className="font-heading text-base font-bold text-slate-900">
              {quiz.pass_percentage}%
            </span>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
            <span className="font-mono text-xs text-slate-400 block">Questions</span>
            <span className="font-heading text-base font-bold text-slate-900">
              {quiz.question_count || quiz.questions?.length || 0}
            </span>
          </div>

          <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
            <span className="font-mono text-xs text-slate-400 block">Max Attempts</span>
            <span className="font-heading text-base font-bold text-slate-900">
              {quiz.max_attempts > 0 ? `${quiz.max_attempts}` : "Unlimited"}
            </span>
          </div>
        </div>

        {startAttemptMutation.isError && (
          <ErrorAlert
            message={
              (startAttemptMutation.error as any)?.message ||
              "Could not start quiz attempt. You may have exceeded your allowed attempts."
            }
          />
        )}

        <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Button
            variant="primary"
            size="lg"
            onClick={() => startAttemptMutation.mutate()}
            isLoading={startAttemptMutation.isPending}
            className="w-full sm:w-auto"
          >
            Start Quiz Assessment
          </Button>
        </div>
      </Card>
    </div>
  );
}
