/**
 * TypeScript definitions for Quizzes, Questions, Attempts, and Scoring.
 * Synchronized with backend: backend/app/schemas/quiz.py
 */

export type QuestionType =
  | "MCQ_SINGLE"
  | "MCQ_MULTI"
  | "TRUE_FALSE"
  | "TEXT_SHORT";

export interface QuestionOptionResponse {
  id: string;
  option_text: string;
  is_correct?: boolean | null; // Concealed during active student attempt
  sort_order: number;
}

export interface QuestionResponse {
  id: string;
  quiz_id: string;
  question_type: QuestionType;
  prompt: string;
  points: number;
  explanation?: string | null; // Concealed during active student attempt
  sort_order: number;
  options: QuestionOptionResponse[];
}

export interface QuizResponse {
  id: string;
  lesson_id: string;
  title: string;
  description?: string | null;
  pass_percentage: number;
  time_limit_minutes: number;
  shuffle_questions: boolean;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  question_count: number;
  total_points: number;
  questions?: QuestionResponse[] | null;
}

export interface CreateQuizPayload {
  title: string;
  description?: string;
  pass_percentage?: number;
  time_limit_minutes?: number;
  shuffle_questions?: boolean;
  max_attempts?: number;
}

export interface UpdateQuizPayload {
  title?: string;
  description?: string;
  pass_percentage?: number;
  time_limit_minutes?: number;
  shuffle_questions?: boolean;
  max_attempts?: number;
}

export interface QuestionOptionInput {
  option_text: string;
  is_correct: boolean;
  sort_order?: number;
}

export interface CreateQuestionPayload {
  question_type: QuestionType;
  prompt: string;
  points?: number;
  explanation?: string;
  sort_order?: number;
  options?: QuestionOptionInput[];
}

export interface BulkCSVImportResponse {
  imported_count: number;
  question_ids: string[];
}

export interface QuizAttemptStartResponse {
  attempt_id: string;
  quiz_id: string;
  attempt_no: number;
  started_at: string;
  server_deadline?: string | null;
  time_limit_minutes: number;
  questions: QuestionResponse[];
}

export interface AutosaveAnswerRequest {
  question_id: string;
  selected_option_ids?: string[] | null;
  text_response?: string | null;
}

export interface AutosaveAnswerResponse {
  success: boolean;
  question_id: string;
  autosaved_at: string;
}

export interface QuizAnswerSubmissionInput {
  question_id: string;
  selected_option_ids?: string[] | null;
  text_response?: string | null;
}

export interface QuizSubmitRequest {
  answers?: QuizAnswerSubmissionInput[] | null;
}

export interface AnswerReviewResponse {
  question_id: string;
  prompt: string;
  question_type: QuestionType;
  points_possible: number;
  points_earned?: number | null;
  is_correct?: boolean | null;
  selected_option_ids?: string[] | null;
  text_response?: string | null;
  explanation?: string | null;
  options: QuestionOptionResponse[];
}

export interface QuizAttemptResultResponse {
  id: string;
  quiz_id: string;
  student_id: string;
  student_name?: string | null;
  attempt_no: number;
  started_at: string;
  completed_at?: string | null;
  time_limit_minutes: number;
  server_deadline?: string | null;
  status: "IN_PROGRESS" | "SUBMITTED" | "EXPIRED" | string;
  score?: number | null;
  is_passed?: boolean | null;
  pass_percentage: number;
  answers?: AnswerReviewResponse[] | null;
}

export interface QuizAttemptListResponse {
  items: QuizAttemptResultResponse[];
  total: number;
  page: number;
  size: number;
}
