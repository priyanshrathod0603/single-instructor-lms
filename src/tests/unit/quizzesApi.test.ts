import { describe, it, expect, vi, beforeEach } from "vitest";
import { quizzesApi } from "@/lib/api/quizzes";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

describe("quizzesApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts a quiz attempt session with server deadline", async () => {
    const mockAttempt = {
      attempt_id: "att-1",
      quiz_id: "quiz-1",
      attempt_no: 1,
      started_at: "2026-01-01T00:00:00Z",
      server_deadline: "2026-01-01T00:30:00Z",
      time_limit_minutes: 30,
      questions: [],
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockAttempt);

    const result = await quizzesApi.startQuizAttempt("quiz-1");

    expect(apiClient.post).toHaveBeenCalledWith("/quizzes/quiz-1/attempts");
    expect(result.attempt_id).toBe("att-1");
    expect(result.time_limit_minutes).toBe(30);
  });

  it("autosaves answer for a specific question", async () => {
    const mockAutosave = {
      success: true,
      question_id: "q-1",
      autosaved_at: "2026-01-01T00:05:00Z",
    };

    vi.mocked(apiClient.patch).mockResolvedValueOnce(mockAutosave);

    const result = await quizzesApi.autosaveAnswer("att-1", {
      question_id: "q-1",
      selected_option_ids: ["opt-1"],
    });

    expect(apiClient.patch).toHaveBeenCalledWith(
      "/quiz-attempts/att-1/autosave",
      {
        question_id: "q-1",
        selected_option_ids: ["opt-1"],
      }
    );
    expect(result.success).toBe(true);
  });

  it("submits quiz attempt and receives scoring results", async () => {
    const mockResult = {
      id: "att-1",
      quiz_id: "quiz-1",
      student_id: "stu-1",
      attempt_no: 1,
      started_at: "2026-01-01T00:00:00Z",
      time_limit_minutes: 30,
      status: "SUBMITTED",
      score: 85,
      is_passed: true,
      pass_percentage: 70,
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResult);

    const result = await quizzesApi.submitQuizAttempt("att-1");

    expect(apiClient.post).toHaveBeenCalledWith(
      "/quiz-attempts/att-1/submit",
      {}
    );
    expect(result.score).toBe(85);
    expect(result.is_passed).toBe(true);
  });
});
