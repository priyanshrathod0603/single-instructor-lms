import { describe, it, expect, vi, beforeEach } from "vitest";
import { progressApi } from "@/lib/api/progress";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("progressApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts lesson progress heartbeat with watch_position_seconds", async () => {
    const mockResponse = {
      lesson_id: "lesson-123",
      is_completed: false,
      watch_position_seconds: 120,
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await progressApi.recordLessonProgress("lesson-123", {
      watch_position_seconds: 120,
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      "/progress/lessons/lesson-123",
      { watch_position_seconds: 120 }
    );
    expect(result.watch_position_seconds).toBe(120);
    expect(result.is_completed).toBe(false);
  });

  it("fetches course progress summary", async () => {
    const mockSummary = {
      course_id: "course-456",
      completed_lessons_count: 8,
      total_lessons_count: 10,
      progress_percentage: 80.0,
      is_completed: false,
      completed_lesson_ids: ["lesson-1", "lesson-2"],
      last_activity_at: "2026-01-01T00:00:00Z",
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockSummary);

    const result = await progressApi.getCourseProgress("course-456");

    expect(apiClient.get).toHaveBeenCalledWith("/progress/courses/course-456");
    expect(result.completed_lessons_count).toBe(8);
    expect(result.progress_percentage).toBe(80.0);
  });
});
