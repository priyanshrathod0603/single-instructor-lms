# Frontend Part 1 Implementation Plan & Foundation Roadmap (FRONTEND_PART_1_IMPLEMENTATION_PLAN)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Part Scope**: Part 1 — Project Foundation, Design Tokens, Layout Shells & Authentication Flow  
**Execution Mode**: Implementation Plan (Pending Project Owner Approval)  
**Date**: 2026-11-15  

---

## 1. Part 1 Scope & Objectives

Part 1 establishes the complete technical and visual foundation for the Single-Instructor LMS client application. It transitions the project from a purely backend repository into an integrated full-stack environment by:
1. Scaffolding the Next.js 15 (App Router) + TypeScript frontend project.
2. Implementing the official **Modern Playful Minimalist** design token architecture (`UI_UX_RULES.md`).
3. Authoring core UI primitives (Button, Input, Card, Modal, Sheet, Badge, Toast, Skeleton).
4. Building the typed API client with HttpOnly cookie support and error unwrapping.
5. Implementing all 6 responsive layout shells (Public, Auth, Student, Staff, Admin, Control).
6. Implementing the complete, hardened Authentication & Session flow (Login, Register, Logout, Single-Session Displacement Modal, Google OAuth, Password Reset).
7. Proving the implementation with automated unit, responsive viewport, and E2E tests.

---

## 2. Proposed Frontend Folder Architecture

```text
/src
├── app/                                 # Next.js App Router root
│   ├── (public)/                        # Public Storefront Route Group
│   │   ├── layout.tsx                   # Public Header + Footer shell
│   │   ├── page.tsx                     # Flagship Landing Page (/)
│   │   └── courses/                     # Course Catalog (/courses, /courses/[slug])
│   ├── (auth)/                          # Authentication Route Group
│   │   ├── layout.tsx                   # Two-column auth split shell
│   │   ├── login/page.tsx               # Student/Staff Login (/login)
│   │   ├── signup/page.tsx              # Student Registration (/signup)
│   │   ├── forgot-password/page.tsx     # Password reset request (/forgot-password)
│   │   ├── reset-password/page.tsx      # Password reset confirmation (/reset-password)
│   │   ├── verify-email/page.tsx        # Email verification landing (/verify-email)
│   │   └── onboarding/claim/page.tsx    # Staff onboarding invitation claim
│   ├── (student)/                       # Student Learning Portal Route Group
│   │   ├── layout.tsx                   # 240px Sidebar + Mobile Bottom Nav Shell
│   │   ├── app/                         # Student Dashboard (/app)
│   │   ├── courses/                     # Enrolled courses (/app/courses, /app/courses/[id])
│   │   ├── assignments/                 # Student assignments (/app/assignments, /[id])
│   │   ├── quizzes/                     # Student quizzes (/app/quizzes, /[id])
│   │   ├── certificates/                # Earned certificates (/app/certificates)
│   │   ├── orders/                      # Purchase receipts (/app/orders)
│   │   └── profile/                     # Profile & active session management (/app/profile)
│   ├── learn/[courseId]/[lessonId]/     # Focus Course Player Shell (Distraction-free)
│   ├── (staff)/                         # Staff Grading Portal Route Group
│   │   ├── layout.tsx                   # Staff queue layout shell
│   │   ├── staff/page.tsx               # Staff dashboard
│   │   └── reviews/                     # Submissions queue & grading workspace
│   ├── (admin)/                         # Admin Management Route Group
│   │   ├── layout.tsx                   # Admin sidebar shell
│   │   ├── courses/                     # Course management & course builder
│   │   ├── students/                    # Student roster & manual enrollments
│   │   └── orders/                      # Financial ledger & refunds
│   ├── (control)/                       # Super Admin Master Governance Route Group
│   │   ├── layout.tsx                   # Super Admin security shell
│   │   ├── staff/page.tsx               # Staff invitation & privilege management
│   │   ├── permissions/page.tsx         # Granular permission matrix
│   │   ├── security/page.tsx            # Credentials & secret keys
│   │   └── audit/page.tsx               # Immutable audit trail
│   ├── api/                             # Internal Next.js route handlers (if needed)
│   ├── globals.css                      # Tailwind base & CSS design tokens
│   └── layout.tsx                       # Root HTML document & Providers wrapper
│
├── components/                          # Reusable UI Component Library
│   ├── ui/                              # Core Primitives (Radix + Tailwind)
│   │   ├── Button.tsx                   # Primary Teal, Accent Coral, Outline, Ghost
│   │   ├── Input.tsx                    # Accessible input with error state
│   │   ├── Textarea.tsx                 # Auto-resizing textarea
│   │   ├── Card.tsx                     # 14px rounded surface with diffuse shadow
│   │   ├── Modal.tsx                    # Desktop dialog / Mobile slide-up sheet
│   │   ├── Badge.tsx                    # Status pill (Mint, Peach, Coral)
│   │   ├── Toast.tsx                    # Sonner brand notification styling
│   │   └── Skeleton.tsx                 # Brand shimmering skeleton loader
│   ├── navigation/                      # Layout Shell Components
│   │   ├── PublicHeader.tsx             # Marketing nav + CTA
│   │   ├── PublicFooter.tsx             # Platform footer & disclaimers
│   │   ├── StudentSidebar.tsx           # Fixed 240px left sidebar
│   │   ├── StudentBottomNav.tsx         # Mobile fixed bottom nav (4 destinations)
│   │   └── StaffAdminSidebar.tsx        # High-density admin sidebar & drawer
│   ├── feedback/                        # Four-State UI Wrappers
│   │   ├── LoadingView.tsx              # Skeleton container
│   │   ├── EmptyState.tsx               # Brand illustration + CTA button
│   │   ├── ErrorAlert.tsx               # Non-blocking alert with retry
│   │   └── DisplacedSessionModal.tsx    # "You signed in on another device" dialog
│   └── auth/                            # Auth Specific Components
│       ├── LoginForm.tsx                # Email/password form
│       ├── GoogleLoginButton.tsx        # Google Identity Services button
│       └── PasswordStrengthMeter.tsx    # Visual password complexity meter
│
├── lib/                                 # Core Utilities & Infrastructure
│   ├── api/                             # API Client & Endpoint Wrappers
│   │   ├── client.ts                    # Typed fetch wrapper with cookie transmission
│   │   ├── auth.ts                      # Auth endpoint bindings
│   │   ├── courses.ts                   # Course catalog bindings
│   │   └── errors.ts                    # Backend error envelope unwrapper
│   ├── hooks/                           # Custom React Hooks
│   │   ├── useAuth.ts                   # Auth session & permission checker
│   │   ├── useResponsive.ts             # Viewport detection (matches 10 viewports)
│   │   └── useDebounce.ts               # Debounced value for autosave
│   ├── store/                           # Client-State Stores (Zustand)
│   │   ├── authStore.ts                 # Ephemeral auth state & displacement flag
│   │   └── uiStore.ts                   # Sidebar toggle, active player tab
│   └── tokens/                          # Design Token Definitions
│       └── colors.ts                    # Brand hex values & Tailwind constants
│
├── types/                               # TypeScript Interfaces (Mirroring Pydantic)
│   ├── auth.ts                          # User, Session, Token schemas
│   ├── course.ts                        # Course, Revision, Curriculum schemas
│   ├── order.ts                         # Order, Transaction, Razorpay schemas
│   └── api.ts                           # Standard response & error envelopes
│
└── tests/                               # Automated Test Suites
    ├── unit/                            # Vitest component unit tests
    ├── integration/                     # MSW integration tests
    └── e2e/                             # Playwright multi-browser & responsive tests
```

---

## 3. Part 1 Detailed Task Breakdown

| Task ID | Task Title | Dependencies | Target Files | Acceptance Criteria |
| :--- | :--- | :---: | :--- | :--- |
| **FE-TASK-101** | **Next.js & TypeScript Project Initialization** | None | `package.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs` | • Next.js 15 App Router initialized.<br>• TypeScript strict mode enabled with `@/` path aliases.<br>• Build passes cleanly with zero errors. |
| **FE-TASK-102** | **Design Token Architecture & Base Styling** | FE-TASK-101 | `tailwind.config.ts`, `src/app/globals.css`, `src/lib/tokens/colors.ts` | • Exact colors registered: Primary Deep Teal (`#006B60`), Accent Coral (`#FF8964`), Warm Cream (`#FFF8F5`), Soft Peach (`#FCE8E1`), Mint (`#DDF3EE`).<br>• Plus Jakarta Sans font configured with Google Font optimization.<br>• 60-25-10-5 color balance tokens active. |
| **FE-TASK-103** | **Core UI Primitives Library** | FE-TASK-102 | `src/components/ui/Button.tsx`, `Input.tsx`, `Card.tsx`, `Modal.tsx`, `Badge.tsx`, `Skeleton.tsx` | • Button supports Primary Teal, Accent Coral, Outline, Ghost.<br>• All touch targets $\ge 44 \times 44$px.<br>• Accessible focus indicators active.<br>• Zero external opinionated CSS bloat. |
| **FE-TASK-104** | **Typed API Client & Error Envelope Unwrapper** | FE-TASK-101 | `src/lib/api/client.ts`, `src/lib/api/errors.ts`, `src/types/api.ts` | • Automatically sets `credentials: "include"` for HttpOnly cookies.<br>• Intercepts `401 SESSION_REVOKED` and dispatches session displacement event.<br>• Parses backend error envelope `{success: false, error: {code, message, details, request_id}}`. |
| **FE-TASK-105** | **Auth State Management & Session Context** | FE-TASK-104 | `src/lib/store/authStore.ts`, `src/lib/hooks/useAuth.ts`, `src/lib/api/auth.ts` | • TanStack React Query `useAuth` hook queries `GET /api/v1/auth/me`.<br>• Evaluates `hasPermission(key)` and `hasRole(role)`.<br>• Zero session secrets written to `localStorage`. |
| **FE-TASK-106** | **Responsive Layout Shells Implementation** | FE-TASK-103, FE-TASK-105 | `src/app/(public)/layout.tsx`, `(auth)/layout.tsx`, `(student)/layout.tsx`, `src/components/navigation/*` | • Public Header & Footer responsive on 320px–1440px.<br>• Student Portal renders 240px sidebar on $\ge 1024$px; fixed bottom navigation bar on $< 768$px.<br>• Touch targets $\ge 44 \times 44$px. |
| **FE-TASK-107** | **Authentication Views & Single-Session Enforcement** | FE-TASK-104, FE-TASK-106 | `src/app/(auth)/login/page.tsx`, `signup/page.tsx`, `forgot-password/page.tsx`, `src/components/feedback/DisplacedSessionModal.tsx` | • Login authenticates via `POST /api/v1/auth/login`.<br>• Google OAuth renders Google button (`POST /api/v1/auth/oauth/google`).<br>• Single-session displacement modal displays: *"You signed in on another device"*. |
| **FE-TASK-108** | **Part 1 Automated Test Suite & Responsive Verification** | FE-TASK-101–FE-TASK-107 | `tests/unit/*`, `tests/e2e/auth.spec.ts`, `tests/e2e/responsive.spec.ts` | • Vitest unit tests pass with $\ge 85\%$ coverage.<br>• Playwright tests pass across all 10 target viewports (320px to 1440px) with zero horizontal overflow.<br>• WCAG 2.1 AA audits pass with zero violations. |

---

## 4. Execution Stop Condition & Review Protocol

> [!CAUTION]
> **MANDATORY STOP CONDITION**: Following completion of Part 0 documentation, the AI execution agent **MUST STOP**. No code files may be created, no dependencies may be installed, and no project files may be modified until the Project Owner explicitly reviews and approves this Part 1 implementation plan.
