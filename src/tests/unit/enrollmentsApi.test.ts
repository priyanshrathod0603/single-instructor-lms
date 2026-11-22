import { describe, it, expect, vi, beforeEach } from "vitest";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("enrollmentsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls GET /enrollments with default pagination", async () => {
    const mockResponse = {
      items: [
        {
          id: "enr-1",
          student_id: "stu-1",
          course_id: "course-1",
          status: "ACTIVE",
          granted_at: "2026-01-01T00:00:00Z",
          course_title: "Full-Stack Web Architecture",
        },
      ],
      total: 1,
      page: 1,
      size: 20,
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockResponse);

    const result = await enrollmentsApi.listOwnEnrollments();

    expect(apiClient.get).toHaveBeenCalledWith("/enrollments", {
      params: {
        page: 1,
        per_page: 20,
        status: undefined,
      },
    });
    expect(result.items).toHaveLength(1);
    expect(result.items[0].course_title).toBe("Full-Stack Web Architecture");
  });

  it("calls GET /enrollments/check/:courseId with encoded courseId", async () => {
    const mockCheck = {
      course_id: "course-uuid",
      is_enrolled: true,
      status: "ACTIVE",
      access_granted: true,
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockCheck);

    const result = await enrollmentsApi.checkEnrollment("course-uuid");

    expect(apiClient.get).toHaveBeenCalledWith("/enrollments/check/course-uuid");
    expect(result.is_enrolled).toBe(true);
    expect(result.access_granted).toBe(true);
  });
});
