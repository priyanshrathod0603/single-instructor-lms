import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { coursesApi } from "@/lib/api/courses";
import { mediaApi } from "@/lib/api/media";
import { assignmentsApi } from "@/lib/api/assignments";
import { quizzesApi } from "@/lib/api/quizzes";
import { enrollmentsApi } from "@/lib/api/enrollments";
import { ordersApi } from "@/lib/api/orders";
import { usersApi } from "@/lib/api/users";
import { auditApi } from "@/lib/api/audit";

describe("Admin & Instructor API Clients Integration", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("coursesApi.listManageCourses queries /courses/manage with pagination", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ items: [], total: 0, page: 1, per_page: 20, total_pages: 0 }),
    });
    global.fetch = mockFetch;

    await coursesApi.listManageCourses({ page: 2, per_page: 10 });
    const url = new URL(mockFetch.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/courses/manage");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("per_page")).toBe("10");
  });

  it("coursesApi.reorderSections calls PUT /courses/{id}/revisions/{revId}/sections/reorder", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [],
    });
    global.fetch = mockFetch;

    await coursesApi.reorderSections("c1", "r1", [{ id: "s1", sort_order: 1 }]);
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/courses/c1/revisions/r1/sections/reorder");
    expect(opts.method).toBe("PUT");
    expect(JSON.parse(opts.body)).toEqual({ items: [{ id: "s1", sort_order: 1 }] });
  });

  it("coursesApi.getPublishChecklist queries /courses/{id}/publish-checklist", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ can_publish: true, revision_id: "r1", revision_no: 1, blockers: [], warnings: [] }),
    });
    global.fetch = mockFetch;

    await coursesApi.getPublishChecklist("c1", "r1");
    const url = new URL(mockFetch.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/courses/c1/publish-checklist");
    expect(url.searchParams.get("revision_id")).toBe("r1");
  });

  it("mediaApi.listMediaAssets queries /media with pagination", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ items: [], total: 0, page: 1, per_page: 20, total_pages: 0 }),
    });
    global.fetch = mockFetch;

    await mediaApi.listMediaAssets({ page: 1, per_page: 20, mime_type: "video/mp4" });
    const url = new URL(mockFetch.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/media");
    expect(url.searchParams.get("mime_type")).toBe("video/mp4");
  });

  it("mediaApi.deleteMediaAsset calls DELETE /media/{id}", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      json: async () => ({}),
    });
    global.fetch = mockFetch;

    await mediaApi.deleteMediaAsset("m1");
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/media/m1");
    expect(opts.method).toBe("DELETE");
  });

  it("assignmentsApi.gradeSubmission posts to /submissions/{id}/grade", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "s1", status: "GRADED" }),
    });
    global.fetch = mockFetch;

    await assignmentsApi.gradeSubmission("s1", {
      scores: [{ criteria_id: "crit_1", points_awarded: 10, feedback: "Great work!" }],
      feedback: "Overall excellent",
    });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/submissions/s1/grade");
    expect(opts.method).toBe("POST");
  });

  it("quizzesApi.bulkImportCsv sends csv_content payload to /quizzes/{id}/questions/bulk-csv", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ imported_count: 5, question_ids: ["q1", "q2"] }),
    });
    global.fetch = mockFetch;

    await quizzesApi.bulkImportCsv("quiz_1", "type,prompt,points\nMCQ_SINGLE,Sample,1");
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/quizzes/quiz_1/questions/bulk-csv");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ csv_content: "type,prompt,points\nMCQ_SINGLE,Sample,1" });
  });

  it("enrollmentsApi.grantManualEnrollment posts to /enrollments/grant-manual", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "e1", status: "ACTIVE" }),
    });
    global.fetch = mockFetch;

    await enrollmentsApi.grantManualEnrollment({
      student_id: "u1",
      course_id: "c1",
      reason: "Scholarship grant",
    });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/enrollments/grant-manual");
    expect(opts.method).toBe("POST");
  });

  it("ordersApi.processRefund posts to /orders/{id}/refund", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "ref_1", status: "PROCESSED" }),
    });
    global.fetch = mockFetch;

    await ordersApi.processRefund("ord_1", { reason: "Requested by student within 7 days" });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/orders/ord_1/refund");
    expect(opts.method).toBe("POST");
  });

  it("usersApi.updateStatus patches /users/{id}/status", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "u1", is_active: false }),
    });
    global.fetch = mockFetch;

    await usersApi.updateStatus("u1", { is_active: false, reason: "Account review" });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/users/u1/status");
    expect(opts.method).toBe("PATCH");
  });

  it("auditApi.listAuditLogs queries /audit-logs with filters", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ items: [], total: 0, page: 1, per_page: 20, total_pages: 0 }),
    });
    global.fetch = mockFetch;

    await auditApi.listAuditLogs({ action: "USER_LOGIN", page: 1 });
    const url = new URL(mockFetch.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/audit-logs");
    expect(url.searchParams.get("action")).toBe("USER_LOGIN");
  });
});
