# Frontend Technology Decision Report (FRONTEND_TECHNOLOGY_DECISION_REPORT)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Document Type**: Technical Stack Evaluation & Decision Matrix  
**Date**: 2026-11-15  
**Authority Reference**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 1–16]; `.ai/CORE/PRIORITY_HIERARCHY.md`; `.ai/RULES/GLOBAL_RULES.md`  

---

## 1. Classification Standards

In accordance with the 8-tier Priority Hierarchy (`.ai/CORE/PRIORITY_HIERARCHY.md`), all technical specifications are categorized as:
* `[APPROVED]`: Formally mandated by project owner or binding project rules (`FRONTEND_RULES.md`, `UI_UX_RULES.md`).
* `[VERIFIED]`: Empirically confirmed from filesystem and backend contracts.
* `[PROPOSED]`: Recommended based on Blueprint v2.0 specifications, requiring owner sign-off.
* `[PENDING_APPROVAL]`: Architectural branch point awaiting owner direction before implementation.

---

## 2. Technology Evaluation & Decision Matrix

| Architectural Layer | Recommended Technology | Classification | Justification & Architectural Alignment | Alternative Considered & Rejection Rationale |
| :--- | :--- | :---: | :--- | :--- |
| **Frontend Framework** | **Next.js 15 (App Router)** | `[PROPOSED]` | Proposed in Blueprint v2.0 [Page 2]. Combines Server-Side Rendering (SSR) for public marketing SEO (`/`, `/courses`, `/courses/:slug`) with Client-Side Rendering (CSR) for interactive student, staff, and admin dashboards. | **Vite React SPA**: Fast client-only build, but lacks built-in SSR for SEO and OpenGraph preview cards for course sales. |
| **Programming Language**| **TypeScript 5.x** | `[APPROVED]` | Mandated by Blueprint v2.0 [Page 2]. Guarantees end-to-end type safety, strict null checking, and exact interface mirrors for backend Pydantic schemas. | **JavaScript (ES6+)**: Rejected due to lack of compile-time contract enforcement and high risk of runtime schema mismatches. |
| **Build & Dev Tooling** | **Turbopack / Next CLI** | `[PROPOSED]` | Built into Next.js 15. Sub-second Fast Refresh, optimized tree-shaking, and zero-config TypeScript compilation. | **Webpack 5**: Slower dev server startup; complex manual configuration. |
| **Styling Engine** | **Tailwind CSS v3.4 / v4** | `[APPROVED]` | Mandated by `FRONTEND_RULES.md` and `UI_UX_RULES.md`. Implements the exact approved design tokens (`Primary Deep Teal` `#006B60`, `Accent Coral Orange` `#FF8964`, `Warm Cream` `#FFF8F5`) via CSS variables. | **CSS Modules / Styled Components**: Higher runtime overhead, fragmentation of design tokens, harder to enforce the strict 60-25-10-5 rule. |
| **Component Architecture**| **Radix UI Primitives + Custom Tailwind** | `[PROPOSED]` | Headless, unstyled accessible primitives (Dialog, Dropdown, Tabs, Tooltip, Accordion) styled strictly with brand tokens. Complies with WCAG 2.1 AA keyboard navigation and screen reader requirements without introducing generic third-party visual bloat. | **Material UI / Ant Design**: Rejected because they enforce third-party design languages that violate `UI_UX_RULES.md` ("Modern Playful Minimalist"). |
| **Motion & Micro-interactions**| **Motion (`motion` ^14.14.0)** | `[VERIFIED]` | Officially installed in repository. Integrates Emil Kowalski motion philosophy (`review-animations`, `gestures`, `spring`, `apple-design`). Smooth, 60fps interruptible animations on composite properties (`transform`, `opacity`). | **GSAP**: Heavier bundle size; motion library is already installed and integrated with workspace skills. |
| **Routing Architecture**| **Next.js App Router Route Groups** | `[PROPOSED]` | Organizes portals into isolated layout shells: `(public)`, `(auth)`, `(student)`, `(staff)`, `(admin)`, `(control)`. Maps 1:1 to approved route inventory [Blueprint v2.0, Page 4]. | **Pages Router**: Legacy architecture; lacks nested layout preservation and granular server component boundaries. |
| **Server-State Management**| **TanStack React Query v5** | `[PROPOSED]` | Automatic request deduplication, background revalidation, optimistic updates (autosave answers, progress heartbeats), and query cache invalidation upon single-session displacement. | **RTK Query / SWR**: React Query has deeper integration with mutation lifecycles, optimistic locks, and TypeScript inference. |
| **Client-State Management**| **Zustand v5** | `[PROPOSED]` | Lightweight (1.2kb), unopinionated store for strictly ephemeral presentation state (sidebar open/collapse, video player mute/volume, dirty form tracking). Never authoritative for security, permissions, or countdown timers. | **Redux Toolkit**: Excessive boilerplate for purely client-side presentation state. |
| **Form Handling** | **React Hook Form** | `[PROPOSED]` | High performance uncontrolled form state, minimal re-renders. Implements mandatory Input Preservation on Error protocol (`FRONTEND_RULES.md` Section 5). | **Formik**: Performance bottlenecks with large dynamic forms (e.g., course curriculum reordering and rubric scoring). |
| **Schema Validation** | **Zod v3** | `[PROPOSED]` | Schema definitions match backend Pydantic models. Validates form inputs client-side before submission while preserving typed user input on server 400/422 errors. | **Yup / Joi**: Zod provides superior static TypeScript type inference and smaller bundle footprints. |
| **API Client** | **Typed Fetch Wrapper (`apiClient`)** | `[PROPOSED]` | Native `fetch` wrapper configured with `credentials: "include"`, automatic `X-Request-ID` correlation, `Idempotency-Key` headers on state transitions, and unified error unwrapping. | **Axios**: Adds unnecessary bundle weight when native `fetch` with interceptors covers all browser and SSR requirements. |
| **Authentication Architecture**| **HttpOnly Cookie (`__Host-lms_session`)** | `[APPROVED]` | Mandated by `SECURITY_RULES.md` and ADR-002. Zero long-lived tokens in `localStorage`. Intercepts `401 SESSION_REVOKED` for single-active-session displacement. | **Bearer token in localStorage**: Explicitly forbidden by `SECURITY_RULES.md` due to XSS vulnerability. |
| **Error Handling** | **Global React Error Boundary + Toast/Alerts** | `[APPROVED]` | Unwraps standard backend error envelope `{success: false, error: {code, message, details, request_id}}`. Non-blocking field-level alerts and Sonner toasts. | **Alert popups / Raw alerts**: Clunky UX that violates `FRONTEND_RULES.md`. |
| **Testing Architecture** | **Vitest + RTL + Playwright** | `[PROPOSED]` | Vitest + React Testing Library for fast component unit tests; Playwright for multi-browser E2E and 10-viewport responsive testing; `@axe-core/playwright` for WCAG 2.1 AA compliance audits. | **Cypress / Jest**: Slower execution; Playwright provides superior multi-viewport and mobile device emulation. |
| **Build & Deployment** | **Standalone Docker Image** | `[PROPOSED]` | Node.js Alpine container with Next.js standalone output. Predictable, reproducible deployment matching backend Docker infrastructure. | **Static HTML Export**: Incompatible with dynamic SSR course catalog and video token generation. |

---

## 3. Deep Dive: Key Architectural Recommendations

### 3.1 Next.js 15 App Router vs. Vite React SPA
* **The Challenge**: The Single-Instructor LMS contains both public, SEO-critical storefront pages (`/`, `/courses`, `/courses/:slug`) and authenticated, highly interactive portal applications (`/app`, `/staff`, `/admin`, `/control`).
* **The Recommendation**: **Next.js 15 (App Router)**.
  1. **Public Marketing Pages**: Rendered via Incremental Static Regeneration (ISR) or SSR. Search engines and social media crawlers receive fully rendered HTML and dynamic OpenGraph meta tags, maximizing course conversion.
  2. **Authenticated Portals**: Marked as client components (`"use client"`), functioning with the exact responsiveness and speed of a Single Page Application (SPA).
  3. **Layout Shell Isolation**: Route groups (`(public)`, `(auth)`, `(student)`, `(admin)`) allow completely independent layout trees without re-rendering common chrome.

### 3.2 Radix UI + Custom Tailwind Tokens
* **The Challenge**: `UI_UX_RULES.md` strictly prohibits generic third-party SaaS dashboard templates, arbitrary colors, or unapproved styling.
* **The Recommendation**: **Radix UI Primitives**.
  * Radix provides 100% unstyled, accessible logic for modals, sheets, dropdowns, and tabs.
  * Styling is applied exclusively through Tailwind utility classes referencing approved design tokens (`bg-primary-deep-teal`, `text-accent-coral`, `bg-warm-cream`).
  * Guarantees full compliance with WCAG 2.1 AA keyboard focus rings, ARIA roles, and screen-reader accessibility without inheriting any third-party aesthetic defaults.

### 3.3 State Management Split: Server Cache vs. Ephemeral UI State
* **Server Authority**: The backend is the single source of truth for all business state.
* **TanStack React Query v5**: Owns all asynchronous data fetched from `/api/v1/`. Manages caching, stale-while-revalidate, retry backoff, and optimistic updates.
* **Zustand v5**: Strictly restricted to non-persistent, ephemeral UI state:
  * Mobile drawer open/closed state.
  * Course player curriculum sidebar toggle.
  * Audio/video volume and playback speed preferences.
  * Active unsaved draft indicators.

---

## 4. Technology Decisions Requiring Owner Sign-Off

The following choices are proposed for formal confirmation prior to frontend code generation:

1. **Framework Confirmation**: Confirm **Next.js 15 (App Router)** with TypeScript as the official frontend framework [Matches Blueprint v2.0 Page 2].
2. **Component Library Approach**: Confirm headless **Radix UI primitives** styled with approved Tailwind tokens (avoiding pre-styled opinionated libraries like Ant Design or MUI).
3. **HTTP Client Standard**: Confirm native **Fetch API wrapper** (`apiClient`) with interceptors vs. third-party `axios`.
4. **Toast Library**: Confirm **Sonner** (`ask-sonner` skill installed) styled with brand tokens (`Warm Cream` background, `Deep Teal` borders).

---

## 5. Summary Status

* **Technology Recommendation Status**: `PROPOSED — READY FOR OWNER REVIEW`
* **Violations of Governance**: None. All recommendations strictly uphold `GLOBAL_RULES.md`, `FRONTEND_RULES.md`, and `UI_UX_RULES.md`.
