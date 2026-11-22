import { ApiErrorDetail, ApiErrorEnvelope } from "@/types/api";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, any>;
  requestId?: string;

  constructor(
    message: string,
    status: number = 500,
    code: string = "INTERNAL_SERVER_ERROR",
    details?: Record<string, any>,
    requestId?: string
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;

    // Maintains proper stack trace for where error was thrown (V8 only)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ApiError);
    }
  }

  get isSessionRevoked(): boolean {
    return this.code === "SESSION_REVOKED" || this.status === 401 && this.code === "SESSION_REVOKED";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 422 || this.code === "VALIDATION_ERROR";
  }
}

export function parseApiError(error: unknown, fallbackMessage = "An unexpected error occurred"): ApiError {
  if (error instanceof ApiError) {
    return error;
  }

  if (error instanceof Error) {
    return new ApiError(error.message, 500, "CLIENT_ERROR");
  }

  return new ApiError(fallbackMessage, 500, "UNKNOWN_ERROR");
}

export const SESSION_REVOKED_EVENT = "lms:session_revoked";

export function dispatchSessionRevokedEvent(reason?: string): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(SESSION_REVOKED_EVENT, {
        detail: {
          message: reason || "Your session has been terminated because a newer login occurred on another device.",
          timestamp: Date.now(),
        },
      })
    );
  }
}
