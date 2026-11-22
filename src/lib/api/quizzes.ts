import { apiClient } from "./client";
import {
  AutosaveAnswerRequest,
  AutosaveAnswerResponse,
  BulkCSVImportResponse,
  CreateQuestionPayload,
  CreateQuizPayload,
  QuestionResponse,
  QuizAttemptListResponse,
  QuizAttemptResultResponse,
  QuizAttemptStartResponse,
  QuizResponse,
  QuizSubmitRequest,
  UpdateQuizPayload,
} from "@/types/quiz";

export const quizzesApi = {
  // ---------------------------------------------------------------------------
  // Quiz Authoring & Administration
  // ---------------------------------------------------------------------------
  /**
   * Create a quiz attached to a curriculum lesson.
   */
  async createQuiz(lessonId: string, data: CreateQuizPayload): Promise<QuizResponse> {
    return apiClient.post<QuizResponse>(
      `/lessons/${encodeURIComponent(lessonId)}/quiz`,
      data
    );
  },

  /**
   * Get quiz configured on a lesson.
   */
  async getLessonQuiz(lessonId: string): Promise<QuizResponse> {
    return apiClient.get<QuizResponse>(
      `/lessons/${encodeURIComponent(lessonId)}/quiz`
    );
  },

  /**
   * Get quiz by quiz ID.
   */
  async getQuiz(quizId: string): Promise<QuizResponse> {
    return apiClient.get<QuizResponse>(`/quizzes/${encodeURIComponent(quizId)}`);
  },

  /**
   * Update quiz configuration (passing percentage, time limit, max attempts).
   */
  async updateQuiz(quizId: string, data: UpdateQuizPayload): Promise<QuizResponse> {
    return apiClient.patch<QuizResponse>(
      `/quizzes/${encodeURIComponent(quizId)}`,
      data
    );
  },

  /**
   * Add a question to an existing quiz.
   */
  async addQuestion(quizId: string, data: CreateQuestionPayload): Promise<QuestionResponse> {
    return apiClient.post<QuestionResponse>(
      `/quizzes/${encodeURIComponent(quizId)}/questions`,
      data
    );
  },

  /**
   * Bulk import questions via CSV string payload.
   */
  async bulkImportCsv(quizId: string, csvContent: string): Promise<BulkCSVImportResponse> {
    return apiClient.post<BulkCSVImportResponse>(
      `/quizzes/${encodeURIComponent(quizId)}/questions/bulk-csv`,
      { csv_content: csvContent }
    );
  },

  /**
   * Admin view of student attempts on a quiz.
   */
  async listQuizAttempts(
    quizId: string,
    params?: { page?: number; size?: number }
  ): Promise<QuizAttemptListResponse> {
    return apiClient.get<QuizAttemptListResponse>(
      `/quizzes/${encodeURIComponent(quizId)}/attempts`,
      { params }
    );
  },

  // ---------------------------------------------------------------------------
  // Student Quiz Taking & Submissions
  // ---------------------------------------------------------------------------
  /**
   * Initialize a new quiz attempt session.
   */
  async startQuizAttempt(quizId: string): Promise<QuizAttemptStartResponse> {
    return apiClient.post<QuizAttemptStartResponse>(
      `/quizzes/${encodeURIComponent(quizId)}/attempts`
    );
  },

  /**
   * Autosave individual question response.
   */
  async autosaveAnswer(
    attemptId: string,
    data: AutosaveAnswerRequest
  ): Promise<AutosaveAnswerResponse> {
    return apiClient.patch<AutosaveAnswerResponse>(
      `/quiz-attempts/${encodeURIComponent(attemptId)}/autosave`,
      data
    );
  },

  /**
   * Finalize and submit quiz attempt for server scoring.
   */
  async submitQuizAttempt(
    attemptId: string,
    data?: QuizSubmitRequest
  ): Promise<QuizAttemptResultResponse> {
    return apiClient.post<QuizAttemptResultResponse>(
      `/quiz-attempts/${encodeURIComponent(attemptId)}/submit`,
      data || {}
    );
  },

  /**
   * Retrieve completed quiz attempt results.
   */
  async getAttemptResult(attemptId: string): Promise<QuizAttemptResultResponse> {
    return apiClient.get<QuizAttemptResultResponse>(
      `/quiz-attempts/${encodeURIComponent(attemptId)}`
    );
  },

  /**
   * List the student's own quiz attempts.
   */
  async listOwnAttempts(params?: {
    quiz_id?: string;
    page?: number;
    size?: number;
  }): Promise<QuizAttemptListResponse> {
    return apiClient.get<QuizAttemptListResponse>("/quiz-attempts", {
      params,
    });
  },
};
