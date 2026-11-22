# Frontend Engineering Rules & Component Protection (FRONTEND_RULES)

## 1. Frontend Architectural Baseline & Scope

This document governs all client-side code, component structures, pages, routing, state management, and design system implementations within the Single-Instructor LMS.

All frontend activities must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md) and the approved visual design system in [.ai/RULES/UI_UX_RULES.md](file:///Users/priyansh/lms/.ai/RULES/UI_UX_RULES.md).

---

## 2. Component & Page Protection Rules

### Mandatory Inspection Before Any Edit
Before modifying any component or page, the AI agent **MUST**:
1. Search the codebase for all occurrences and imports of the component.
2. Inspect the component's existing props, internal state, and event handlers.
3. Identify parent and child component dependencies.
4. Verify whether the component is shared across student, staff, or admin portals.

### Absolute Restrictions:
* **NEVER** replace an existing component with a third-party library or arbitrary new component without explicit owner approval.
* **NEVER** alter an existing component's public props interface in a backward-incompatible way.
* **NEVER** remove or comment out existing interactive controls, buttons, tooltips, or shortcuts.
* **NEVER** change existing page routes or URL parameter schemes without explicit approval.

---

## 3. Page & Route Inventory Protection

All client routing must align with the official Route Inventory [Source: LMS Blueprint v2.0, Page 4]:

| Portal Area | Permitted Routes | Routing Rules & Access Guardrails |
| :--- | :--- | :--- |
| **Public** | `/`, `/courses`, `/courses/:slug` | Publicly accessible; no auth cookies required; marketing layouts. |
| **Auth** | `/login`, `/signup`, `/forgot-password`, `/reset-password` | Public entry points; redirect authenticated users to `/app` or `/control`. |
| **Student** | `/app`, `/app/courses`, `/app/courses/:id`, `/learn/:courseId/:lessonId`, `/app/assignments`, `/app/quizzes`, `/app/certificates`, `/app/orders`, `/app/profile` | Strictly requires authenticated session with `Student` role; protected learning player. |
| **Staff** | `/staff`, `/staff/reviews/:id`, `/staff/tickets/:id` | Requires authenticated `Staff` role and assigned record scope. |
| **Admin** | `/admin`, `/admin/courses`, `/admin/courses/:id/edit`, `/admin/students`, `/admin/orders`, `/admin/analytics` | Requires `Admin` role with module-level permissions. |
| **Super Admin** | `/control`, `/control/staff`, `/control/permissions`, `/control/security`, `/control/settings`, `/control/audit` | Restricted to platform owner; full system governance. |

* **Prohibited**: Do NOT invent new ad-hoc routes or dismantle route guards.

---

## 4. State Management & API Integration Protection

* **Client State Boundary**: Client state (e.g., Zustand, Redux, React Context) is strictly ephemeral and presentation-focused.
* **Server Authority**: The client state is **NEVER** authoritative for security, permissions, prices, exam countdown timers, or completion thresholds.
* **API Integration Preservation**:
  * All frontend network calls must target the versioned `/api/v1/` endpoint inventory.
  * Never alter request payloads or expected response formats unless an API contract modification has been explicitly approved.
  * Always pass the required `Idempotency-Key` header on checkout, refund, final assignment submission, and quiz submission.

---

## 5. Form Handling & Input Preservation Protocol

* **Input Preservation on Error (Mandatory)**:
  * When a form submission fails due to validation errors, network interruption, or server `400/422` responses, the UI **MUST NEVER** clear or reset the form.
  * All user-typed text, option selections, and draft inputs must be preserved in state so the user does not lose work [Source: LMS Blueprint v2.0, Page 3].
* **Autosave with Visual Feedback**:
  * Assignment text, quiz responses, and course builder drafts must implement debounced autosaving with visible save timestamps and dirty state indicators [Source: LMS Blueprint v2.0, Pages 5, 7].

---

## 6. Complete UI State Coverage (Mandatory States)

Every interactive component, table, and data-driven view must implement all four fundamental UI states:

1. **Loading State**:
   * Use smooth skeleton loaders or subtle spinners adhering to brand colors (`Primary Deep Teal` or `Mint`).
   * Avoid jarring layout shifts (Cumulative Layout Shift prevention).
2. **Empty State**:
   * Display a clean, friendly illustration or icon with a helpful headline and primary call-to-action button (e.g., *"No assignments pending — explore your courses"*).
3. **Error State**:
   * Render non-blocking error banners or field-level alerts.
   * Parse and display the standard error message from `{error: {message, details}}` without leaking stack traces or internal IDs.
4. **Success State**:
   * Provide immediate, non-intrusive confirmation feedback (e.g., toast notification, subtle checkmark transition).

---

## 7. Responsive Behavior & Accessibility Standards

### Layout Shell Specifications [Source: LMS Blueprint v2.0, Page 3]:
* **Desktop ($\ge 1024$px)**: Fixed 240px left navigation sidebar, persistent top utility bar (breadcrumbs, search, notifications, profile), scrollable main content canvas.
* **Tablet ($768$px to $1023$px)**: Collapsible left navigation sidebar with overlay or hamburger trigger.
* **Mobile ($< 768$px)**:
  * Student Portal: Fixed bottom navigation bar for high-frequency views (Overview, Courses, Tasks, Profile).
  * Staff / Admin Portal: Slide-out drawer navigation with accessible touch targets ($\ge 44 \times 44$px).

### Accessibility (WCAG 2.1 AA Compliance):
* **Keyboard Navigation**: All interactive elements (buttons, inputs, dropdowns, modal dialogs) must be fully navigable using `Tab`, `Enter`, `Space`, and arrow keys.
* **Focus Rings**: Never remove `:focus` or `:focus-visible` outlines. Use a visible focus indicator using `Primary Deep Teal` (`#006B60`) or `Accent Coral` (`#FF8964`).
* **Non-Color Status Indicators**: Never convey state (e.g., Late submission, Overdue quiz, Draft course) solely through color. Always accompany colors with distinct text labels, badges, or icons [Source: LMS Blueprint v2.0, Page 3].
* **Semantic HTML**: Use proper `<main>`, `<nav>`, `<header>`, `<section>`, and `<article>` tags with descriptive `aria-label` attributes where appropriate.

---

## 8. Verification & Review Before Reporting

Before reporting any frontend task as complete, the AI agent must verify:
1. The component renders correctly without console errors or hydration warnings.
2. All 4 UI states (Loading, Empty, Error, Success) are present and visually tested.
3. Form input is preserved on failed submission.
4. Layout responds cleanly across desktop (1024px+), tablet (768px), and mobile (375px) breakpoints.
5. All design tokens strictly match [.ai/RULES/UI_UX_RULES.md](file:///Users/priyansh/lms/.ai/RULES/UI_UX_RULES.md).
