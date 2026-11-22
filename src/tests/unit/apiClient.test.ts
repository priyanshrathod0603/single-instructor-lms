import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, getApiBaseUrl } from "@/lib/api/client";
import { ApiError, SESSION_REVOKED_EVENT } from "@/lib/api/errors";

describe("apiClient", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("always includes credentials: 'include' for HttpOnly session cookie handling", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ success: true, data: "ok" }),
    });
    global.fetch = mockFetch;

    await apiClient.get("/auth/me");

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].credentials).toBe("include");
  });

  it("passes Idempotency-Key for mutation requests when provided", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "order_123" }),
    });
    global.fetch = mockFetch;

    await apiClient.post("/orders/checkout", { course_id: "c1" }, { idempotencyKey: "test-idem-key" });

    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].headers["Idempotency-Key"]).toBe("test-idem-key");
  });

  it("unwraps backend error envelope and throws ApiError", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({
        "content-type": "application/json",
        "X-Request-ID": "req-12345",
      }),
      json: async () => ({
        success: false,
        error: {
          code: "VALIDATION_FAILED",
          message: "Invalid email syntax provided",
          details: { field: "email" },
          request_id: "req-12345",
        },
      }),
    });
    global.fetch = mockFetch;

    await expect(apiClient.post("/auth/register", {})).rejects.toThrow(ApiError);

    try {
      await apiClient.post("/auth/register", {});
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe("VALIDATION_FAILED");
      expect(err.message).toBe("Invalid email syntax provided");
      expect(err.status).toBe(400);
      expect(err.requestId).toBe("req-12345");
      expect(err.details).toEqual({ field: "email" });
    }
  });

  it("intercepts 401 SESSION_REVOKED and dispatches session revoked event", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        success: false,
        error: {
          code: "SESSION_REVOKED",
          message: "Your session has been terminated because a newer login occurred on another device.",
        },
      }),
    });
    global.fetch = mockFetch;

    const eventSpy = vi.fn();
    window.addEventListener(SESSION_REVOKED_EVENT, eventSpy);

    await expect(apiClient.get("/auth/me")).rejects.toThrow(ApiError);
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener(SESSION_REVOKED_EVENT, eventSpy);
  });

  it("aborts and throws TIMEOUT error when request exceeds timeoutMs", async () => {
    // Mock fetch that hangs until aborted
    global.fetch = vi.fn().mockImplementation((_url, options) => {
      return new Promise((_resolve, reject) => {
        if (options?.signal) {
          options.signal.addEventListener("abort", () => {
            const err = new Error("The operation was aborted");
            err.name = "AbortError";
            reject(err);
          });
        }
      });
    });

    await expect(
      apiClient.get("/auth/me", { timeoutMs: 20 })
    ).rejects.toThrow(ApiError);

    try {
      await apiClient.get("/auth/me", { timeoutMs: 20 });
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.code).toBe("TIMEOUT");
      expect(err.status).toBe(408);
      expect(err.message).toContain("timed out");
    }
  });

  describe("getApiBaseUrl LAN host resolution", () => {
    const originalEnv = process.env.NEXT_PUBLIC_API_URL;

    afterEach(() => {
      process.env.NEXT_PUBLIC_API_URL = originalEnv;
    });

    it("adapts localhost backend URL to match current LAN hostname in browser runtime", () => {
      delete process.env.NEXT_PUBLIC_API_URL;
      const originalLocation = window.location;
      delete (window as any).location;
      (window as any).location = new URL("http://192.168.1.103:3000");

      const resolved = getApiBaseUrl();
      expect(resolved).toBe("http://192.168.1.103:8000");

      (window as any).location = originalLocation;
    });

    it("keeps localhost when browser is on localhost", () => {
      delete process.env.NEXT_PUBLIC_API_URL;
      const originalLocation = window.location;
      delete (window as any).location;
      (window as any).location = new URL("http://localhost:3000");

      const resolved = getApiBaseUrl();
      expect(resolved).toBe("http://localhost:8000");

      (window as any).location = originalLocation;
    });

    it("preserves explicit external production backend URL", () => {
      process.env.NEXT_PUBLIC_API_URL = "https://api.courses.com";
      const originalLocation = window.location;
      delete (window as any).location;
      (window as any).location = new URL("http://192.168.1.103:3000");

      const resolved = getApiBaseUrl();
      expect(resolved).toBe("https://api.courses.com");

      (window as any).location = originalLocation;
    });
  });
});
