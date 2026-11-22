import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { controlApi } from "@/lib/api/control";

describe("Super Admin Control API Client (SA-01)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("controlApi.getOverview calls GET /control/overview and returns structured data", async () => {
    const mockOverviewData = {
      user_metrics: {
        total_students: 42,
        total_admins: 1,
        total_staff: 3,
        total_super_admins: 1,
        active_users: 45,
      },
      course_metrics: {
        total_courses: 5,
        published_courses: 3,
        draft_courses: 1,
        archived_courses: 1,
      },
      enrollment_metrics: {
        total_enrollments: 120,
        active_enrollments: 115,
      },
      financial_metrics: {
        verified_revenue_paise: 5990000,
        verified_revenue_inr: 59900.0,
        successful_transactions: 12,
        refunded_amount_paise: 0,
        refunded_amount_inr: 0.0,
        net_revenue_paise: 5990000,
        net_revenue_inr: 59900.0,
        currency: "INR",
      },
      security_metrics: {
        total_audit_events: 250,
        security_events_count: 14,
        active_staff_count: 3,
        security_model: "Tier 1 Hardened: Single Active Session & Signed JWTs",
      },
      registration_trends: [
        { date: "2026-11-01", count: 2 },
        { date: "2026-11-02", count: 5 },
      ],
      enrollment_trends: [
        { date: "2026-11-01", count: 1 },
        { date: "2026-11-02", count: 3 },
      ],
      recent_activity: [
        {
          id: "audit-1",
          actor_type: "SUPER_ADMIN",
          action: "STAFF_INVITED",
          resource_type: "user",
          resource_id: "u-123",
          created_at: "2026-11-16T10:00:00Z",
        },
      ],
      generated_at: "2026-11-16T12:00:00Z",
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockOverviewData,
    });
    global.fetch = mockFetch;

    const result = await controlApi.getOverview();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/overview");
    expect(opts.method).toBe("GET");
    expect(result.user_metrics.total_students).toBe(42);
    expect(result.financial_metrics.net_revenue_paise).toBe(5990000);
    expect(result.recent_activity.length).toBe(1);
  });

  it("controlApi.listSessions calls GET /control/sessions with params", async () => {
    const mockResponse = {
      items: [
        {
          id: "sess-1",
          user_id: "u-1",
          status: "ACTIVE",
          last_active_at: "2026-11-16T12:00:00Z",
          expires_at: "2026-11-23T12:00:00Z",
          created_at: "2026-11-16T10:00:00Z",
          user: {
            id: "u-1",
            email: "student@example.com",
            full_name: "Student One",
            roles: ["STUDENT"],
            is_active: true,
          },
        },
      ],
      total: 1,
      page: 1,
      per_page: 15,
      pages: 1,
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockResponse,
    });
    global.fetch = mockFetch;

    const result = await controlApi.listSessions({ status: "ACTIVE", page: 1 });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, opts] = mockFetch.mock.calls[0];
    const parsedUrl = new URL(url);
    expect(parsedUrl.pathname).toBe("/api/v1/control/sessions");
    expect(parsedUrl.searchParams.get("status")).toBe("ACTIVE");
    expect(opts.method).toBe("GET");
    expect(result.items.length).toBe(1);
    expect(result.items[0].id).toBe("sess-1");
  });

  it("controlApi.getSession calls GET /control/sessions/{id}", async () => {
    const mockDetail = {
      id: "sess-1",
      user_id: "u-1",
      status: "ACTIVE",
      last_active_at: "2026-11-16T12:00:00Z",
      expires_at: "2026-11-23T12:00:00Z",
      created_at: "2026-11-16T10:00:00Z",
      correlated_events: [],
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockDetail,
    });
    global.fetch = mockFetch;

    const result = await controlApi.getSession("sess-1");
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/sessions/sess-1");
    expect(opts.method).toBe("GET");
    expect(result.id).toBe("sess-1");
  });

  it("controlApi.revokeSession calls POST /control/sessions/{id}/revoke", async () => {
    const mockRevoked = {
      id: "sess-1",
      user_id: "u-1",
      status: "REVOKED",
      last_active_at: "2026-11-16T12:00:00Z",
      expires_at: "2026-11-23T12:00:00Z",
      created_at: "2026-11-16T10:00:00Z",
      revocation_reason: "Manual admin revocation",
      correlated_events: [],
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockRevoked,
    });
    global.fetch = mockFetch;

    const result = await controlApi.revokeSession("sess-1", {
      reason: "Manual admin revocation",
    });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/sessions/sess-1/revoke");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ reason: "Manual admin revocation" });
    expect(result.status).toBe("REVOKED");
  });

  it("controlApi.revokeUserSessions calls POST /control/users/{id}/revoke-sessions", async () => {
    const mockResponse = {
      user_id: "u-1",
      revoked_sessions_count: 2,
      message: "Successfully revoked 2 active sessions for user.",
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockResponse,
    });
    global.fetch = mockFetch;

    const result = await controlApi.revokeUserSessions("u-1", {
      reason: "Security audit",
    });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/users/u-1/revoke-sessions");
    expect(opts.method).toBe("POST");
    expect(result.revoked_sessions_count).toBe(2);
  });

  it("controlApi.revokeOtherSessions calls POST /control/sessions/revoke-others", async () => {
    const mockResponse = {
      revoked_sessions_count: 5,
      caller_session_id: "caller-sess-id",
      caller_session_preserved: true,
      message: "Emergency platform containment executed. Revoked 5 other active session(s).",
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockResponse,
    });
    global.fetch = mockFetch;

    const result = await controlApi.revokeOtherSessions({
      reason: "Emergency containment",
    });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/sessions/revoke-others");
    expect(opts.method).toBe("POST");
    expect(result.caller_session_preserved).toBe(true);
    expect(result.revoked_sessions_count).toBe(5);
  });

  it("controlApi.getSecurityMetrics calls GET /control/security/metrics", async () => {
    const mockMetrics = {
      active_sessions_total: 10,
      active_sessions_by_role: { STUDENT: 8, ADMIN: 2 },
      sessions_revoked_24h: 3,
      sessions_displaced_24h: 1,
      sessions_expired_24h: 0,
      failed_logins_24h: 4,
      rate_limit_breaches_24h: 0,
      suspended_accounts_total: 2,
      generated_at: "2026-11-16T12:00:00Z",
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockMetrics,
    });
    global.fetch = mockFetch;

    const result = await controlApi.getSecurityMetrics();
    const [url, opts] = mockFetch.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/v1/control/security/metrics");
    expect(opts.method).toBe("GET");
    expect(result.active_sessions_total).toBe(10);
    expect(result.sessions_revoked_24h).toBe(3);
  });

  // ===========================================================================
  // SA-04: Course Governance, Blog CMS, and Notes CMS Tests
  // ===========================================================================

  describe("SA-04 Content & Course Governance APIs", () => {
    it("controlApi.listGovernedCourses calls GET /control/courses", async () => {
      const mockCourses = {
        items: [
          {
            id: "course-1",
            slug: "full-stack-bootcamp",
            title: "Full-Stack Bootcamp",
            status: "PUBLISHED",
            price_inr: 499900,
            is_free: false,
            tags: ["React", "FastAPI"],
            total_sections: 5,
            total_lessons: 30,
            total_duration_seconds: 14400,
            has_quiz: true,
            has_assignment: true,
            enrolled_students_count: 42,
            created_at: "2026-11-16T10:00:00Z",
            updated_at: "2026-11-16T12:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 10,
        pages: 1,
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockCourses,
      });
      global.fetch = mockFetch;

      const res = await controlApi.listGovernedCourses({ status: "PUBLISHED", page: 1 });
      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/control/courses");
      expect(new URL(url).searchParams.get("status")).toBe("PUBLISHED");
      expect(opts.method).toBe("GET");
      expect(res.total).toBe(1);
      expect(res.items[0].title).toBe("Full-Stack Bootcamp");
    });

    it("controlApi.getGovernedCourse calls GET /control/courses/{id}", async () => {
      const mockCourse = {
        id: "course-1",
        slug: "full-stack-bootcamp",
        title: "Full-Stack Bootcamp",
        status: "PUBLISHED",
        price_inr: 499900,
        is_free: false,
        tags: [],
        total_sections: 5,
        total_lessons: 30,
        total_duration_seconds: 14400,
        has_quiz: true,
        has_assignment: true,
        enrolled_students_count: 42,
        created_at: "2026-11-16T10:00:00Z",
        updated_at: "2026-11-16T12:00:00Z",
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockCourse,
      });
      global.fetch = mockFetch;

      const res = await controlApi.getGovernedCourse("course-1");
      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/control/courses/course-1");
      expect(opts.method).toBe("GET");
      expect(res.id).toBe("course-1");
    });

    it("controlApi.updateCourseStatus calls PATCH /control/courses/{id}/status", async () => {
      const mockUpdated = {
        id: "course-1",
        status: "ARCHIVED",
        title: "Archived Course",
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockUpdated,
      });
      global.fetch = mockFetch;

      const res = await controlApi.updateCourseStatus("course-1", {
        status: "ARCHIVED",
        reason: "Course retired",
      });
      const [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/control/courses/course-1/status");
      expect(opts.method).toBe("PATCH");
      expect(JSON.parse(opts.body)).toEqual({
        status: "ARCHIVED",
        reason: "Course retired",
      });
      expect(res.status).toBe("ARCHIVED");
    });

    it("controlApi.listBlogPosts and getBlogCategories call blog endpoints", async () => {
      const mockList = {
        items: [
          {
            id: "blog-1",
            title: "Getting Started with Python",
            slug: "getting-started-python",
            content: "Hello world",
            category: "Tutorials",
            status: "PUBLISHED",
            author_id: "u-1",
            created_at: "2026-11-16T10:00:00Z",
            updated_at: "2026-11-16T10:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 10,
        pages: 1,
      };

      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockList,
      });
      global.fetch = mockFetch;

      const res = await controlApi.listBlogPosts({ category: "Tutorials" });
      let [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/control/blog");
      expect(new URL(url).searchParams.get("category")).toBe("Tutorials");
      expect(res.total).toBe(1);

      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ["Tutorials", "Guides"],
      });
      global.fetch = mockFetch;

      const cats = await controlApi.getBlogCategories();
      [url, opts] = mockFetch.mock.calls[0];
      expect(new URL(url).pathname).toBe("/api/v1/control/blog/categories");
      expect(cats).toEqual(["Tutorials", "Guides"]);
    });

    it("controlApi CRUD methods for Blog Posts execute expected HTTP verbs", async () => {
      const postItem = {
        id: "blog-2",
        title: "Advanced TypeScript",
        slug: "advanced-typescript",
        content: "Types and Generics",
        category: "Advanced",
        status: "DRAFT",
        author_id: "u-1",
        created_at: "2026-11-16T10:00:00Z",
        updated_at: "2026-11-16T10:00:00Z",
      };

      // Create
      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => postItem,
      });
      global.fetch = mockFetch;

      let res = await controlApi.createBlogPost({
        title: "Advanced TypeScript",
        content: "Types and Generics",
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("POST");
      expect(res.title).toBe("Advanced TypeScript");

      // Update
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ...postItem, title: "Advanced TS v2" }),
      });
      global.fetch = mockFetch;

      res = await controlApi.updateBlogPost("blog-2", { title: "Advanced TS v2" });
      expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
      expect(res.title).toBe("Advanced TS v2");

      // Status
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ...postItem, status: "PUBLISHED" }),
      });
      global.fetch = mockFetch;

      res = await controlApi.changeBlogStatus("blog-2", "PUBLISHED");
      expect(mockFetch.mock.calls[0][1].method).toBe("PATCH");
      expect(res.status).toBe("PUBLISHED");

      // Delete
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
        text: async () => "",
      });
      global.fetch = mockFetch;

      await controlApi.deleteBlogPost("blog-2");
      expect(mockFetch.mock.calls[0][1].method).toBe("DELETE");
    });

    it("controlApi CRUD and PDF replacement methods for Notes execute cleanly", async () => {
      const noteItem = {
        id: "note-1",
        title: "React Cheatsheet",
        slug: "react-cheatsheet",
        category: "Cheat Sheets",
        pdf_url: "https://storage.example.com/react.pdf",
        file_size_bytes: 1048576,
        status: "DRAFT",
        author_id: "u-1",
        created_at: "2026-11-16T10:00:00Z",
        updated_at: "2026-11-16T10:00:00Z",
      };

      // Create Note
      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => noteItem,
      });
      global.fetch = mockFetch;

      let res = await controlApi.createNote({
        title: "React Cheatsheet",
        category: "Cheat Sheets",
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("POST");
      expect(res.title).toBe("React Cheatsheet");

      // Replace PDF
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          ...noteItem,
          pdf_url: "https://storage.example.com/react-v2.pdf",
          file_size_bytes: 2097152,
        }),
      });
      global.fetch = mockFetch;

      res = await controlApi.replaceNotePdf("note-1", {
        pdf_url: "https://storage.example.com/react-v2.pdf",
        file_size_bytes: 2097152,
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("POST");
      expect(res.file_size_bytes).toBe(2097152);

      // Status
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ...noteItem, status: "PUBLISHED" }),
      });
      global.fetch = mockFetch;

      res = await controlApi.changeNoteStatus("note-1", "PUBLISHED");
      expect(mockFetch.mock.calls[0][1].method).toBe("PATCH");
      expect(res.status).toBe("PUBLISHED");

      // Delete
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
        text: async () => "",
      });
      global.fetch = mockFetch;

      await controlApi.deleteNote("note-1");
      expect(mockFetch.mock.calls[0][1].method).toBe("DELETE");
    });
  });

  describe("SA-05: Complete Commercial Governance API", () => {
    it("manages promotional offers (list, get, create, update, status, delete)", async () => {
      const mockOffer = {
        id: "offer-1",
        name: "Diwali Promo",
        code: "DIWALI50",
        discount_type: "PERCENTAGE",
        discount_value: 50,
        status: "ACTIVE",
      };

      // 1. List Offers
      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ items: [mockOffer], total: 1, page: 1, per_page: 10, pages: 1 }),
      });
      global.fetch = mockFetch;

      const listRes = await controlApi.listOffers({ status: "ACTIVE" });
      expect(mockFetch.mock.calls[0][1].method).toBe("GET");
      expect(listRes.items.length).toBe(1);

      // 2. Get Offer
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockOffer,
      });
      global.fetch = mockFetch;

      const getRes = await controlApi.getOffer("offer-1");
      expect(getRes.code).toBe("DIWALI50");

      // 3. Create Offer
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockOffer,
      });
      global.fetch = mockFetch;

      const createRes = await controlApi.createOffer({
        name: "Diwali Promo",
        code: "DIWALI50",
        discount_type: "PERCENTAGE",
        discount_value: 50,
        valid_from: "2026-11-01T00:00:00Z",
        valid_to: "2026-12-01T00:00:00Z",
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("POST");
      expect(createRes.code).toBe("DIWALI50");

      // 4. Update Offer
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ...mockOffer, name: "Diwali Super Promo" }),
      });
      global.fetch = mockFetch;

      const updateRes = await controlApi.updateOffer("offer-1", {
        name: "Diwali Super Promo",
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
      expect(updateRes.name).toBe("Diwali Super Promo");

      // 5. Change Offer Status
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ ...mockOffer, status: "INACTIVE" }),
      });
      global.fetch = mockFetch;

      const statusRes = await controlApi.changeOfferStatus("offer-1", "INACTIVE");
      expect(mockFetch.mock.calls[0][1].method).toBe("PATCH");
      expect(statusRes.status).toBe("INACTIVE");

      // 6. Delete Offer
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        headers: new Headers(),
        text: async () => "",
      });
      global.fetch = mockFetch;

      await controlApi.deleteOffer("offer-1");
      expect(mockFetch.mock.calls[0][1].method).toBe("DELETE");
    });

    it("fetches payment overview metrics and lists transactions", async () => {
      // 1. Overview Metrics
      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          gross_revenue_paise: 5000000,
          net_collected_paise: 4500000,
          refunded_amount_paise: 500000,
          successful_payments_count: 10,
          pending_orders_count: 2,
          failed_payments_count: 1,
          currency: "INR",
        }),
      });
      global.fetch = mockFetch;

      const metrics = await controlApi.getPaymentOverview();
      expect(mockFetch.mock.calls[0][1].method).toBe("GET");
      expect(metrics.net_collected_paise).toBe(4500000);

      // 2. List Transactions
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          items: [
            {
              id: "tx-1",
              razorpay_payment_id: "pay_123",
              amount_inr: 500000,
              status: "SUCCESS",
            },
          ],
          total: 1,
          page: 1,
          per_page: 10,
          pages: 1,
        }),
      });
      global.fetch = mockFetch;

      const txList = await controlApi.listTransactions({ status: "SUCCESS" });
      expect(txList.items[0].razorpay_payment_id).toBe("pay_123");

      // 3. Get Single Transaction
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          id: "tx-1",
          razorpay_payment_id: "pay_123",
          amount_inr: 500000,
          status: "SUCCESS",
        }),
      });
      global.fetch = mockFetch;

      const singleTx = await controlApi.getTransaction("tx-1");
      expect(singleTx.id).toBe("tx-1");
    });

    it("gets and updates platform information and settings", async () => {
      const mockSettings = {
        platform_name: "Apex LMS",
        brand_name: "Apex Academy",
        version: "v2.0.0",
        environment: "development",
        currency: "INR",
        frontend_url: "http://localhost:3000",
        cdn_stream_base_url: "https://video.apex.local",
        email_provider: "CONSOLE",
        storage_provider: "LOCAL",
      };

      // 1. Get Platform Settings
      let mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => mockSettings,
      });
      global.fetch = mockFetch;

      const getRes = await controlApi.getPlatformSettings();
      expect(mockFetch.mock.calls[0][1].method).toBe("GET");
      expect(getRes.platform_name).toBe("Apex LMS");

      // 2. Update Platform Settings
      mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({
          ...mockSettings,
          platform_name: "Apex Elite LMS",
        }),
      });
      global.fetch = mockFetch;

      const updateRes = await controlApi.updatePlatformSettings({
        platform_name: "Apex Elite LMS",
      });
      expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
      expect(updateRes.platform_name).toBe("Apex Elite LMS");
    });
  });
});
