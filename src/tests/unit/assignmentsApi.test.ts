import { describe, it, expect, vi, beforeEach } from "vitest";
import { assignmentsApi } from "@/lib/api/assignments";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("assignmentsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches assignment by assignment ID", async () => {
    const mockAssignment = {
      id: "asgn-1",
      lesson_id: "les-1",
      title: "Build Distributed Queue",
      instructions: "Implement worker threads",
      max_score: 100,
      pass_score: 70,
      allow_late: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockAssignment);

    const result = await assignmentsApi.getAssignment("asgn-1");

    expect(apiClient.get).toHaveBeenCalledWith("/assignments/asgn-1");
    expect(result.title).toBe("Build Distributed Queue");
  });

  it("submits project work with file URL and commentary", async () => {
    const mockSubmission = {
      id: "sub-1",
      assignment_id: "asgn-1",
      student_id: "stu-1",
      attempt_no: 1,
      file_url: "https://github.com/student/repo",
      text_notes: "Implemented with Redis",
      status: "SUBMITTED",
      submitted_at: "2026-01-01T00:00:00Z",
      rubric_scores: [],
      grade_overrides: [],
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockSubmission);

    const result = await assignmentsApi.submitProject("asgn-1", {
      file_url: "https://github.com/student/repo",
      text_notes: "Implemented with Redis",
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      "/assignments/asgn-1/submissions",
      {
        file_url: "https://github.com/student/repo",
        text_notes: "Implemented with Redis",
      }
    );
    expect(result.status).toBe("SUBMITTED");
  });

  it("lists the student's own submissions for an assignment", async () => {
    const mockList = {
      items: [
        {
          id: "sub-1",
          assignment_id: "asgn-1",
          student_id: "stu-1",
          attempt_no: 1,
          file_url: "https://github.com/student/repo",
          status: "GRADED",
          submitted_at: "2026-01-01T00:00:00Z",
          final_score: 90,
          rubric_scores: [],
          grade_overrides: [],
        },
      ],
      total: 1,
      page: 1,
      size: 1,
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockList);

    const result = await assignmentsApi.listOwnSubmissions("asgn-1", {
      page: 1,
      size: 1,
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/assignments/asgn-1/my-submissions",
      { params: { page: 1, size: 1 } }
    );
    expect(result.items).toHaveLength(1);
    expect(result.items[0].final_score).toBe(90);
  });
});
