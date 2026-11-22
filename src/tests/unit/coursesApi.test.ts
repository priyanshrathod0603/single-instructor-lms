import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { coursesApi } from "@/lib/api/courses";
import { CourseListResponse, CourseDetail } from "@/types/course";

describe("coursesApi service", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("listCourses sends correct query params to /api/v1/courses", async () => {
    const mockListResponse: CourseListResponse = {
      items: [],
      total: 0,
      page: 1,
      per_page: 20,
      total_pages: 0,
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockListResponse,
    });
    global.fetch = mockFetch;

    const result = await coursesApi.listCourses({
      search: "distributed",
      tag: "Architecture",
      page: 2,
      per_page: 10,
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0][0];
    expect(calledUrl).toContain("/api/v1/courses");
    expect(calledUrl).toContain("search=distributed");
    expect(calledUrl).toContain("tag=Architecture");
    expect(calledUrl).toContain("page=2");
    expect(calledUrl).toContain("per_page=10");
    expect(result).toEqual(mockListResponse);
  });

  it("getCourseDetail fetches specific course by slug with URL encoding", async () => {
    const mockDetail: Partial<CourseDetail> = {
      id: "course-123",
      slug: "system-design-101",
      title: "System Design 101",
      curriculum: [],
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockDetail,
    });
    global.fetch = mockFetch;

    const result = await coursesApi.getCourseDetail("system-design-101");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const calledUrl = mockFetch.mock.calls[0][0];
    expect(calledUrl).toContain("/api/v1/courses/system-design-101");
    expect(result.title).toBe("System Design 101");
  });
});
