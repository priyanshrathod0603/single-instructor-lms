/**
 * Centralized Security Utility: Safe Application Redirect Validation.
 *
 * Mitigates:
 * - Open Redirect vulnerabilities
 * - XSS via executable URL schemes (javascript:, data:, vbscript:)
 * - Protocol-relative URL redirects (//attacker.com)
 * - Obfuscated, encoded, or malformed redirect payloads
 *
 * Strict Security Invariants:
 * 1. Only relative internal paths beginning with a single "/" are allowed.
 * 2. Protocol-relative paths ("//") and Windows UNC-like paths ("/\\", "\\") are strictly rejected.
 * 3. Executable schemes (javascript:, data:, vbscript:, blob:, file:) are strictly rejected.
 * 4. Control characters (CR, LF, TAB, NULL) and invalid URL syntax are rejected.
 * 5. Falls back to a guaranteed safe internal route (e.g. "/app") on any validation failure.
 */

const DUMMY_BASE_ORIGIN = "http://localhost";

/**
 * Validates and sanitizes a target redirect URL.
 * Returns the safe path or the provided safe fallback.
 */
export function getSafeRedirectUrl(
  untrustedUrl: string | null | undefined,
  fallbackRoute: string = "/app"
): string {
  if (!untrustedUrl || typeof untrustedUrl !== "string") {
    return fallbackRoute;
  }

  const trimmed = untrustedUrl.trim();
  if (!trimmed) {
    return fallbackRoute;
  }

  // Reject strings with ASCII control characters or whitespace within path
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1F\x7F]/.test(trimmed)) {
    return fallbackRoute;
  }

  // Reject Windows-style backslashes anywhere before query/hash
  const pathPart = trimmed.split(/[?#]/)[0];
  if (pathPart.includes("\\")) {
    return fallbackRoute;
  }

  // Must begin with a single slash, not double slash (protocol-relative)
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return fallbackRoute;
  }

  // Reject executable or alternative URI schemes if present (e.g. "/javascript:alert(1)")
  const lowerTrimmed = trimmed.toLowerCase();
  if (
    lowerTrimmed.includes("javascript:") ||
    lowerTrimmed.includes("data:") ||
    lowerTrimmed.includes("vbscript:") ||
    lowerTrimmed.includes("blob:") ||
    lowerTrimmed.includes("file:")
  ) {
    return fallbackRoute;
  }

  // Parse using URL API relative to dummy localhost origin
  try {
    const parsed = new URL(trimmed, DUMMY_BASE_ORIGIN);

    // Verify the URL did not escape to an external origin
    if (parsed.origin !== DUMMY_BASE_ORIGIN) {
      return fallbackRoute;
    }

    // Verify protocol is standard http/https
    if (parsed.protocol !== "http:") {
      return fallbackRoute;
    }

    // Pathname must strictly start with / and not //
    if (!parsed.pathname.startsWith("/") || parsed.pathname.startsWith("//")) {
      return fallbackRoute;
    }

    // Reconstruct safe relative path including query string and hash
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallbackRoute;
  }
}
