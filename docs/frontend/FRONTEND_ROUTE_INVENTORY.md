# Complete Frontend Route Inventory (FRONTEND_ROUTE_INVENTORY)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Document Type**: Official Route & Navigation Inventory  
**Date**: 2026-11-15  
**Authority Reference**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Page 4]; `.ai/RULES/FRONTEND_RULES.md`  

---

## 1. Route Inventory Governance & Permitted Paths

All frontend client routes are strictly controlled. The application implements **32 defined routes** across 6 layout shells. In accordance with `FRONTEND_RULES.md` Section 3, routes must not be altered, deleted, or introduced without explicit project-owner approval.

---

## 2. Exhaustive Route Specification Table

| Route URL | Page Purpose | Access Level | Auth Required | Required Role | Required Permission | Layout Shell | Mobile Behavior | Primary Backend Dependencies | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- | :---: |
| `/` | Flagship landing page, instructor authority, curriculum previews, testimonials, direct enrollment CTAs. | Public | No | None (Visitor) | None | `(public)` | 60/40 hero stacks to 1 column; feature grid wraps; CTA pinned in header. | `GET /courses` | `APPROVED` |
| `/courses` | Public course catalog with category filters, search, pricing, and enrollment status. | Public | No | None (Visitor) | None | `(public)` | Filter bar collapses into horizontal scrolling pill bar; single-column course cards. | `GET /courses` | `APPROVED` |
| `/courses/:slug` | Course landing page, syllabus preview, pricing, instructor bio, FAQs, checkout CTA. | Public | No | None (Visitor) | None | `(public)` | Sticky bottom checkout bar with price and *"Enroll Now"* button. | `GET /courses/{id_or_slug}` | `APPROVED` |
| `/login` | Email/password login and Google OAuth entry point. Displaces prior active sessions. | Public (Guest) | No | None (Guest) | None | `(auth)` | Single centered card surface; redirects authenticated user to `/app`. | `POST /auth/login`, `POST /auth/oauth/google` | `APPROVED` |
| `/signup` | Student registration form with instant validation and verification notice. | Public (Guest) | No | None (Guest) | None | `(auth)` | Single centered card surface; strictly provisions Student role. | `POST /auth/register` | `APPROVED` |
| `/forgot-password` | Password recovery initiation request. Anti-enumeration messaging. | Public (Guest) | No | None (Guest) | None | `(auth)` | Centered card surface with back-to-login link. | `POST /auth/password-reset/request` | `APPROVED` |
| `/reset-password` | Password reset completion form with single-use token from email. | Public (Guest) | No | None (Guest) | None | `(auth)` | Password strength meter; revokes prior sessions upon success. | `POST /auth/password-reset/confirm` | `APPROVED` |
| `/verify-email` | Email verification landing page with token confirmation feedback. | Public | No | None | None | `(auth)` | Centered verification card with automatic redirect to `/login`. | `POST /auth/verify-email` | `APPROVED` |
| `/onboarding/claim` | Staff invitation claim page; allows invited instructor/staff to set initial password. | Public | No | None (Invitee) | None | `(auth)` | Displays invited email and assigned role; provisions session. | `POST /auth/onboarding/claim` | `APPROVED` |
| `/app` | Student portal home: enrolled courses carousel, upcoming tasks, resume learning CTA. | Authenticated | Yes | Student | `enrollment:view_own` | `(student)` | Responsive summary cards; bottom navigation bar (Overview active). | `GET /enrollments`, `GET /notifications` | `APPROVED` |
| `/app/courses` | Complete directory of student's enrolled courses with progress bars and certificates. | Authenticated | Yes | Student | `enrollment:view_own` | `(student)` | Single-column cards with progress rings and *"Continue"* buttons. | `GET /enrollments` | `APPROVED` |
| `/app/courses/:id` | Enrolled course syllabus overview, progress summary, section expansion. | Authenticated | Yes | Student | `enrollment:view_own` | `(student)` | Accordion sections with lesson checkmarks and duration tags. | `GET /courses/{id}`, `GET /progress/courses/{id}` | `APPROVED` |
| `/learn/:courseId/:lessonId`| Distraction-free learning player (HLS video stream, watermarked PDF, article notes). | Authenticated | Yes | Student | `media:view_protected` | Focus Player | 16:9 sticky video player on top; tabs for Curriculum and Notes below. | `POST /media/{id}/playback-token`, `GET /media/{id}/protected-pdf`, `POST /progress/lessons/{id}` | `APPROVED` |
| `/app/assignments` | Directory of course assignments across enrolled courses with due dates and statuses. | Authenticated | Yes | Student | `assignment:submit` | `(student)` | Filterable list: Pending, Submitted, Graded. Bottom nav: Tasks. | `GET /enrollments` | `APPROVED` |
| `/app/assignments/:id` | Assignment details, instructions, rubric criteria preview, submission form, grade feedback. | Authenticated | Yes | Student | `assignment:submit` | `(student)` | Multi-step submission: Instructions, Rubric, Work text & Attachments. | `GET /assignments/{id}`, `POST /assignments/{id}/submissions`, `GET /submissions/{id}` | `APPROVED` |
| `/app/quizzes` | Directory of quizzes, attempt history, scores, and pass/fail badges. | Authenticated | Yes | Student | `quiz:attempt` | `(student)` | Cards indicating attempts used, highest score, and due dates. | `GET /quiz-attempts` | `APPROVED` |
| `/app/quizzes/:id` | Quiz pre-flight instructions, attempt start, interactive exam canvas, autosave, submission. | Authenticated | Yes | Student | `quiz:attempt` | Focus Exam | Sticky server countdown timer; 1 question per screen with navigation pills. | `GET /quizzes/{id}`, `POST /quizzes/{id}/attempts`, `PATCH /quiz-attempts/{id}/autosave`, `POST /quiz-attempts/{id}/submit` | `APPROVED` |
| `/app/certificates` | Earned course completion certificates directory with download and verification links. | Authenticated | Yes | Student | None | `(student)` | Certificate preview cards with PDF download and copy-link buttons. | `GET /certificates/{course_id}` | `APPROVED` |
| `/app/orders` | Order history, payment transaction IDs, invoices, and payment receipts. | Authenticated | Yes | Student | `orders:view_own` | `(student)` | Receipt cards with payment date, currency amount, and status chip. | `GET /orders` | `APPROVED` |
| `/app/profile` | Account settings, full name update, password change, active session revocation. | Authenticated | Yes | Student | None | `(student)` | Form cards; single-active-session warning and *"Log out everywhere"* CTA. | `GET /auth/me`, `PATCH /users/{id}` | `APPROVED` |
| `/checkout/:courseId` | Direct checkout and payment initiation page with price breakdown and Razorpay modal. | Authenticated | Yes | Student | `orders:create` | `(public)` | Sticky order summary card; 1-click Razorpay checkout trigger. | `POST /orders`, `GET /orders/{id}` | `PENDING_APPROVAL` |
| `/staff` | Staff dashboard: assigned grading queues, recent reviews, pending student questions. | Authenticated | Yes | Staff | `assignment:view_all` | `(staff)` | Slide-out drawer navigation; summary metric cards. | `GET /assignments/{id}/submissions` | `APPROVED` |
| `/staff/reviews` | Master submission queue filterable by course, submission date, and status. | Authenticated | Yes | Staff | `assignment:grade` | `(staff)` | Sortable submission queue table; touch-friendly row navigation. | `GET /assignments/{id}/submissions` | `APPROVED` |
| `/staff/reviews/:id` | Split-pane grading workspace: student submission viewer on left, rubric scoring on right. | Authenticated | Yes | Staff | `assignment:grade` | `(staff)` | Full-width split canvas with sticky grading action footer. | `GET /submissions/{id}`, `POST /submissions/{id}/grade` | `APPROVED` |
| `/admin` | Administrative platform overview: active students, revenue, completion rates, shortcuts. | Authenticated | Yes | Admin | `course:view_all` | `(admin)` | Metric grid with collapsible sidebar navigation. | `GET /courses/manage`, `GET /users`, `GET /orders` | `APPROVED` |
| `/admin/courses` | Course catalog management: draft, published, and archived courses with revision badges. | Authenticated | Yes | Admin | `course:view_all` | `(admin)` | Filterable course directory with action menus (Edit, Publish, Archive). | `GET /courses/manage` | `APPROVED` |
| `/admin/courses/:id/edit`| Course builder: curriculum hierarchy tree, drag-and-drop reorder, lesson editor, media upload. | Authenticated | Yes | Admin | `course:edit` | `(admin)` | Drag-and-drop hierarchy; pre-flight publish checklist modal. | `GET /courses/{id}/revisions/{rev_id}`, `POST /courses/{id}/revisions/{rev_id}/sections`, `PUT /sections/{id}/lessons/reorder`, `POST /media/upload-intent` | `APPROVED` |
| `/admin/students` | Student roster directory: enrollment statuses, progress, manual enrollment grant. | Authenticated | Yes | Admin | `users:view_all` | `(admin)` | Searchable, paginated user table with modal enrollment grant. | `GET /users`, `GET /enrollments/all`, `POST /enrollments/manual` | `APPROVED` |
| `/admin/orders` | Commercial transactions directory: orders, payments, refunds, and revenue metrics. | Authenticated | Yes | Admin | `orders:view_all` | `(admin)` | Transaction ledger with refund action triggers for Super Admin. | `GET /orders`, `POST /orders/{id}/refund` | `APPROVED` |
| `/admin/analytics` | Aggregate student engagement, quiz score distributions, drop-off points. | Authenticated | Yes | Admin | `course:view_all` | `(admin)` | Responsive charts (completion rates, quiz pass rates, revenue). | `GET /courses/manage`, `GET /orders` | `APPROVED` |
| `/control` | Super Admin master governance console: system health, staff invites, critical settings. | Authenticated | Yes | Super Admin | Super Admin Role | `(control)` | High-security control panel with audit shortcuts and staff metrics. | `GET /audit-logs`, `GET /users` | `APPROVED` |
| `/control/staff` | Staff management: invite staff/admins, manage assigned scopes, revoke privileges. | Authenticated | Yes | Super Admin | `staff:invite` | `(control)` | Invitation modal with role assignment and token status ledger. | `POST /users/staff/invite`, `PATCH /users/{id}/roles` | `APPROVED` |
| `/control/permissions` | Granular role-permission assignment matrix (deny-overrides-allow evaluation). | Authenticated | Yes | Super Admin | `roles:assign` | `(control)` | Interactive permission matrix with checkbox toggles per role. | `GET /users`, `PATCH /users/{id}/roles` | `APPROVED` |
| `/control/security` | Platform credentials: Razorpay keys, Google OAuth Client ID, R2/S3 bucket config. | Authenticated | Yes | Super Admin | Super Admin Role | `(control)` | Redacted credential inputs (`****-****-1234`) with update forms. | `GET /auth/me` | `APPROVED` |
| `/control/settings` | Brand configuration: platform title, support email, currency rules, session timeouts. | Authenticated | Yes | Super Admin | Super Admin Role | `(control)` | Tabbed configuration forms with validation checks. | `GET /auth/me` | `APPROVED` |
| `/control/audit` | Immutable audit trail: searchable event stream with actor, action, IP, and diffs. | Authenticated | Yes | Super Admin | `audit:view` | `(control)` | High-density audit event table with expandable JSON diff viewer. | `GET /api/v1/audit-logs` | `APPROVED` |
| `/verify/certificate/:hash`| Public certificate verification page reached via QR code scan on PDF certificate. | Public | No | None (Public) | None | `(public)` | Standalone verified credential badge with student name, course, and date. | `GET /certificates/verify/{verification_hash}` | `PENDING_APPROVAL` |

---

## 3. Route Requirements Flagged for Project-Owner Approval

The following auxiliary routes support verified backend functionality and complete the student journey:

1. **`/verify-email`**: `APPROVED` (Ratified by Project Owner under Part 1.2 Authorization).
2. **`/onboarding/claim`**: `APPROVED` (Ratified by Project Owner under Part 1.2 Authorization).
3. **`/checkout/:courseId`**: Dedicated pre-payment review page displaying course price, tax, and triggering Razorpay SDK modal (Scheduled for Part 2).
4. **`/verify/certificate/:hash`**: Public destination encoded into the QR code of issued certificate PDFs (Scheduled for Part 3).
