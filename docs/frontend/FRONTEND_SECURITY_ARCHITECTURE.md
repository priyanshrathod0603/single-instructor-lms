# Frontend Security Architecture (FRONTEND_SECURITY_ARCHITECTURE)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Document Type**: Client-Side Security Engineering Specification  
**Date**: 2026-11-15  
**Authority Reference**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 2, 8, 14]; `.ai/RULES/SECURITY_RULES.md`  

---

## 1. Security Philosophy & Golden Invariant

The client-side application is treated as an **untrusted presentation environment**.

> [!IMPORTANT]
> **The Golden Security Invariant**: Under NO circumstances does client-side logic, routing guards, or UI button disabling serve as an authoritative security boundary. The backend authorizes 100% of state transitions and data requests via server-side session checks, role evaluation, and record-level scoping.

---

## 2. Authentication & Session Security Invariants

### 2.1 HttpOnly Session Cookies (`__Host-lms_session`)
* **Transport Mechanism**: Authenticated sessions are anchored by the secure HttpOnly cookie set by the backend upon login (`POST /api/v1/auth/login`) or Google OAuth (`POST /api/v1/auth/oauth/google`).
* **Browser Transmission**: The frontend API client configures every HTTP request with:
  ```typescript
  const apiClient = async (path: string, options: RequestInit = {}) => {
    return fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: "include", // Transmits __Host-lms_session cookie across origins
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        ...options.headers,
      },
    });
  };
  ```

### 2.2 Strict Prohibition of Tokens in `localStorage` or `sessionStorage`
* **Security Threat**: If an attacker executes arbitrary JavaScript via XSS or a malicious third-party dependency, any token residing in `localStorage` or `sessionStorage` is immediately exfiltrated.
* **Binding Policy**: The frontend **MUST NEVER** write session tokens, refresh tokens, passwords, or raw cryptographic keys into `localStorage`, `sessionStorage`, or indexedDB [Source: LMS Blueprint v2.0, Page 8; `SECURITY_RULES.md` Section 2.2].
* Short-lived 15-minute access tokens returned by login may be held strictly in ephemeral JavaScript memory (e.g., inside the React Query or Zustand memory scope).

### 2.3 Single-Active-Session Displacement Handling (`401 SESSION_REVOKED`)
* **Behavior**: When a student logs in on Device B, Device A's active session is atomically marked `status='REVOKED'` in PostgreSQL.
* **Frontend Handling Protocol**:
  1. The next background query or action from Device A triggers `HTTP 401 Unauthorized` with `error.code == "SESSION_REVOKED"`.
  2. The `apiClient` interceptor catches `SESSION_REVOKED` and raises a non-dismissible application event:
     ```typescript
     if (error.code === "SESSION_REVOKED") {
       queryClient.clear(); // Purge sensitive course & personal data from memory
       authStore.getState().setDisplaced(true); // Triggers modal dialog
     }
     ```
  3. The user is presented with a non-dismissible brand modal:
     > **"You signed in on another device"**  
     > *To protect your account integrity, your active session on this device has ended. Only one device may access learning materials at a time.*  
     > `[Log In on This Device]` (Button redirects to `/login`)

---

## 3. Defense-in-Depth Protected Routing & Navigation

### 3.1 Dual-Layer Protection Model
* **Layer 1: Client Navigation Guards (`middleware.ts` & Layout Guards)**:
  * Reads the user profile from `useAuth()` (populated via `GET /api/v1/auth/me`).
  * If unauthenticated, redirects visitor to `/login?redirect=/app/courses`.
  * If authenticated user lacks required role (e.g., Student attempting to enter `/admin`), redirects immediately to `/app` with an alert toast.
* **Layer 2: Server-Enforced RBAC (Binding Authority)**:
  * Even if an attacker manually tampers with client code, router state, or URL parameters, every protected backend endpoint evaluates `require_permissions()` and fails closed (`403 Forbidden`).

### 3.2 Permission-Aware UI Rendering
Interactive buttons, navigation tabs, and actions are rendered conditionally based on the user's verified permissions:
```typescript
export function ActionButton({ requiredPermission, onClick, children }: ActionButtonProps) {
  const { hasPermission } = useAuth();
  if (!hasPermission(requiredPermission)) {
    return null; // Omit control from DOM entirely
  }
  return <Button onClick={onClick}>{children}</Button>;
}
```

---

## 4. Protected Media & PDF Asset Security

### 4.1 Direct-to-Storage Presigned Uploads
* The client never streams multi-gigabyte video files through the backend server.
* Flow:
  1. `POST /api/v1/media/upload-intent` generates an S3/R2 presigned PUT URL.
  2. The browser executes a direct HTTP `PUT` to the cloud bucket.
  3. `POST /api/v1/media/{id}/confirm` instructs the backend to verify object headers remotely before creating the database asset record.

### 4.2 Short-Lived Signed Video Playback
* Video player (`VideoPlayer.tsx`) receives a signed HLS playback token (`POST /api/v1/media/{id}/playback-token`) with a short TTL (2 hours).
* Playback manifest (`.m3u8`) and HLS video chunks (`.ts`) are authenticated via the token; direct asset URLs are never exposed in public DOM attributes.

### 4.3 Protected Watermarked PDF Viewer
* Download suppression headers (`Content-Disposition: inline`, `Cache-Control: private, no-store`).
* The PDF viewer renders via HTML5 Canvas (e.g. `pdfjs-dist`), disabling right-click context menus, printing shortcuts (`Ctrl+P` / `Cmd+P`), and selection highlights.
* Dynamic provenance watermarks (student's email, IP address, and access timestamp) are stamped on every page server-side prior to streaming.

---

## 5. Commerce & Payment Webhook Security

### 5.1 Zero Trust on Browser Redirect
* **The Vulnerability**: Relying on frontend browser callbacks from Razorpay (`onSuccess`) to grant course access is vulnerable to client-side interception or fake payment payloads.
* **The Solution**:
  1. The client invokes the Razorpay Checkout JS modal using `order_id` and `amount` generated by the backend.
  2. Upon payment completion, Razorpay sends a server-to-server webhook (`POST /api/v1/webhooks/razorpay`) with an `X-Razorpay-Signature` HMAC header.
  3. The backend cryptographically verifies the raw bytes against `RAZORPAY_WEBHOOK_SECRET` and grants the course enrollment in PostgreSQL.
  4. The client redirects to `/order-success/:orderId` and polls `GET /api/v1/orders/{id}` until the server marks the order `PAID`.

---

## 6. Web Application Vulnerability Mitigations

| Vulnerability Vector | Client-Side Mitigation Strategy | Implementation Standard |
| :--- | :--- | :--- |
| **Cross-Site Scripting (XSS)** | React JSX default HTML escaping; all markdown/rich-text descriptions sanitized via DOMPurify before rendering; prohibition of unescaped `dangerouslySetInnerHTML`. | `DOMPurify.sanitize(content)` on all article lesson text and course descriptions. |
| **Cross-Site Request Forgery (CSRF)** | `SameSite=Lax` cookie configuration; custom `X-Requested-With: XMLHttpRequest` header sent on all API calls; backend rejects state-changing requests lacking custom headers. | Automated custom headers injected by `apiClient`. |
| **Insecure Direct Object References (IDOR)**| Frontend never constructs direct access URLs using guessed UUIDs; all entity access requests send the current session cookie; backend verifies `record.user_id == current_user.id` or elevated staff scope. | Client gracefully handles `404` and `403` by showing *"Resource not accessible"* without leaking entity existence. |
| **Clickjacking** | Response headers configured with `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'`. | Prevents embedding LMS interfaces inside unauthorized third-party iframes. |
| **Secret & Traceback Exposure** | Production builds strip `console.debug`, source maps, and stack traces; error messages displayed to users use `error.message` from standard backend envelope; raw database details or UUIDs hidden. | Centralized error toast formatter. |
| **Content Security Policy (CSP)**| Strict HTTP CSP header restricting script execution to self, Google Identity Services (`https://accounts.google.com/gsi/client`), and Razorpay Checkout (`https://checkout.razorpay.com`). | Declared in Next.js `middleware.ts` headers. |
