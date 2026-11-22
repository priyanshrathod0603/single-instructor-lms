import { ApiError, dispatchSessionRevokedEvent } from "./errors";
import { ApiErrorEnvelope } from "@/types/api";

export function getApiBaseUrl(): string {
  const configuredUrl =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // In browser runtime, if configured URL points to loopback/localhost but the page
  // was loaded via a LAN IP or custom host, dynamically adapt hostname to match.
  if (typeof window !== "undefined" && window.location) {
    try {
      const parsed = new URL(configuredUrl, window.location.origin);
      if (
        (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") &&
        window.location.hostname !== "localhost" &&
        window.location.hostname !== "127.0.0.1"
      ) {
        parsed.hostname = window.location.hostname;
        return parsed.origin;
      }
      return parsed.origin;
    } catch {
      return configuredUrl;
    }
  }

  return configuredUrl;
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
  idempotencyKey?: string;
  timeoutMs?: number;
}

export function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined>): string {
  let fullUrl: string;
  if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
    fullUrl = endpoint;
  } else {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    // If endpoint doesn't start with /api/v1, prefix it unless it's a health endpoint like /healthz
    const path = cleanEndpoint.startsWith("/api/v1") || cleanEndpoint.startsWith("/healthz")
      ? cleanEndpoint
      : `/api/v1${cleanEndpoint}`;
    const baseUrl = getApiBaseUrl();
    fullUrl = `${baseUrl.replace(/\/$/, "")}${path}`;
  }

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      fullUrl += `${fullUrl.includes("?") ? "&" : "?"}${queryString}`;
    }
  }

  return fullUrl;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const {
    params,
    idempotencyKey,
    timeoutMs = 15000,
    headers = {},
    signal: callerSignal,
    ...fetchOptions
  } = options;

  const url = buildUrl(endpoint, params);
  const isMutation = ["POST", "PUT", "PATCH", "DELETE"].includes(
    (fetchOptions.method || "GET").toUpperCase()
  );

  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string>),
  };

  if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData) && !requestHeaders["Content-Type"]) {
    requestHeaders["Content-Type"] = "application/json";
  }

  if (isMutation && idempotencyKey) {
    requestHeaders["Idempotency-Key"] = idempotencyKey;
  }

  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(new Error("Request timed out")), timeoutMs)
      : null;

  if (callerSignal) {
    if (callerSignal.aborted) {
      controller.abort(callerSignal.reason);
    } else {
      callerSignal.addEventListener("abort", () => controller.abort(callerSignal.reason), {
        once: true,
      });
    }
  }

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: requestHeaders,
      credentials: "include", // CRITICAL: transmit HttpOnly session cookies
    });

    const contentType = response.headers.get("content-type");
    const isJson = contentType && contentType.includes("application/json");

    if (!response.ok) {
      let errorData: any = null;
      if (isJson) {
        try {
          errorData = await response.json();
        } catch {
          // ignore json parse error
        }
      }

      // Backend standard error envelope: { success: false, error: { code, message, details, request_id } }
      if (errorData && errorData.error) {
        const errorDetail = errorData.error;
        const apiError = new ApiError(
          errorDetail.message || `HTTP ${response.status} Error`,
          response.status,
          errorDetail.code || "API_ERROR",
          errorDetail.details,
          errorDetail.request_id || response.headers.get("X-Request-ID") || undefined
        );

        // Check for single-active-session displacement
        if (apiError.isSessionRevoked) {
          dispatchSessionRevokedEvent(apiError.message);
        }

        throw apiError;
      }

      // Fallback for non-standard error responses
      const message =
        (typeof errorData === "string" ? errorData : errorData?.message) ||
        `Request failed with status ${response.status}`;
      const fallbackCode = response.status === 401 ? "UNAUTHORIZED" : "HTTP_ERROR";
      const apiError = new ApiError(
        message,
        response.status,
        fallbackCode,
        undefined,
        response.headers.get("X-Request-ID") || undefined
      );

      if (response.status === 401 && (errorData?.code === "SESSION_REVOKED" || message.toLowerCase().includes("session"))) {
        dispatchSessionRevokedEvent(message);
      }

      throw apiError;
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    if (isJson) {
      return (await response.json()) as T;
    }

    return (await response.text()) as unknown as T;
  } catch (err: unknown) {
    if (controller.signal.aborted) {
      if (callerSignal?.aborted) {
        throw new ApiError("Request was cancelled", 0, "ABORTED");
      }
      throw new ApiError("Network request timed out. Please try again.", 408, "TIMEOUT");
    }
    if (err instanceof ApiError) {
      throw err;
    }
    // Network errors or fetch failures
    const networkError = new ApiError(
      err instanceof Error ? err.message : "Network request failed",
      0,
      "NETWORK_ERROR"
    );
    throw networkError;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "GET" }),

  post: <T>(endpoint: string, data?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: "POST",
      body:
        data !== undefined
          ? data instanceof FormData
            ? data
            : JSON.stringify(data)
          : undefined,
    }),

  put: <T>(endpoint: string, data?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: "PUT",
      body:
        data !== undefined
          ? data instanceof FormData
            ? data
            : JSON.stringify(data)
          : undefined,
    }),

  patch: <T>(endpoint: string, data?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: "PATCH",
      body:
        data !== undefined
          ? data instanceof FormData
            ? data
            : JSON.stringify(data)
          : undefined,
    }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "DELETE" }),
};
