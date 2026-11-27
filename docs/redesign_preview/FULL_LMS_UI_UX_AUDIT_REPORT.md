# Full LMS UI/UX Audit Report & Redesign Proposal

**Project**: Single-Instructor Learning Management System (LMS)  
**Track**: Platform UI/UX Experience  
**Mode**: **Audit → Design Proposal → Isolated Preview Only (Zero Production Modifications)**  
**Status**: `REDESIGN STATUS: WAITING FOR OWNER REVIEW`  
**Date**: 2026-11-24  

---

## 1. Executive Summary

This document presents the complete UI/UX audit and comprehensive design system overhaul proposal for the **Single-Instructor LMS**. 

Following the successful Unslop exploration on the Admin Dashboard (`/admin`), the entire user-facing application was audited across all **46 discovered routes** spanning Public Storefront, Authentication, Student Experience, Instructor Admin Console, Staff Grading, and Super Admin Platform Governance.

### Key Audit Takeaways:
1. **Core Architectural Strengths (Preserved 100%)**:
   - Strict single-active session enforcement, robust server-side RBAC guards (`requireServerAuth`), fail-closed security, and zero-trust webhook payment reconciliation.
   - 44x44px accessible touch targets across primary buttons and mobile navigation.
   - Clean API contracts and deterministic React Query state machines.
2. **Systemic Design Deficits Identified Across the Platform**:
   - **The Rainbow Tile Pattern**: Ubiquitous across Student Dashboard, Course Detail, Admin, and Super Admin—every metric card or icon is placed in an arbitrary pastel box (`bg-teal-50`, `bg-orange-50`, `bg-purple-50`, `bg-blue-50`, `bg-amber-100`).
   - **Palette Fracture**: The brand foundation (`#FFF8F5` Warm Cream, `#006B60` Deep Teal, `#FCE8E1` Soft Peach, `#191B24` Charcoal) was overridden in multiple portals by cold, generic Tailwind `slate-50` and `slate-900`.
   - **Dead CSS Classes**: `font-heading` is applied to titles across 20+ pages despite not being defined in `tailwind.config.ts`.
   - **Excessive Weight 800**: Headings blast `font-extrabold` (weight 800) rather than relying on optical size, letter spacing, and contrast.
   - **Jittery Numbers**: Lack of `tabular-nums` causes horizontal layout drift when counts, timers, or currency update.
   - **Unnecessary Gradients & Glows**: Radial blurs (`blur-3xl`), gradient fills, and bouncy hover zooms (`hover:scale-[1.02]`, `hover:-translate-y-1`) that distract from focused learning and instruction.
   - **Duplicated Navigation**: Sections like "Management Portals" on `/admin` duplicating the persistent sidebar, consuming 33% of the desktop viewport.

---

## 2. Complete Application Discovery & Route Inventory

Across the Next.js 15 App Router architecture, exactly **46 user-facing routes** and **8 layout shells** were verified:

### Group A: Public Website (Storefront)
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/` | `src/app/(public)/page.tsx` | Main Storefront Landing Page (Hero, Featured Courses, Value Props, Process, FAQ) |
| `/courses` | `src/app/(public)/courses/page.tsx` | Masterclass Catalog with search, level/pricing filters, sort dropdown, and course cards |
| `/courses/[slug]` | `src/app/(public)/courses/[slug]/page.tsx` | Course Details & Storefront Sales Page (Syllabus accordion, preview modal, checkout CTA) |
| `/verify/certificate/[hash]` | `src/app/(public)/verify/certificate/[hash]/page.tsx` | Public Certificate Verification portal with QR verification and cryptographic hash seal |

### Group B: Authentication Shell
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/login` | `src/app/(auth)/login/page.tsx` | Student & Staff authentication with email/password and Google OAuth |
| `/signup` | `src/app/(auth)/signup/page.tsx` | Student registration with interactive PasswordStrengthMeter and Google OAuth |
| `/forgot-password` | `src/app/(auth)/forgot-password/page.tsx` | Self-service password reset initiation |
| `/reset-password` | `src/app/(auth)/reset-password/page.tsx` | Secure password reset completion via token verification |
| `/verify-email` | `src/app/(auth)/verify-email/page.tsx` | Post-registration email confirmation status screen |
| `/onboarding/claim` | `src/app/(auth)/onboarding/claim/page.tsx` | Staff & Admin invitation claim with token verification |

### Group C: Student Experience
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/app` | `src/app/(student)/app/page.tsx` | Student Learning Dashboard (Enrolled courses, quiz metrics, resume study) |
| `/app/courses` | `src/app/(student)/app/courses/page.tsx` | Enrolled Courses catalog with visual progress bars |
| `/app/courses/[id]` | `src/app/(student)/app/courses/[id]/page.tsx` | Course Syllabus & Section Navigation viewer |
| `/learn/[courseId]/[lessonId]` | `src/app/learn/[courseId]/[lessonId]/page.tsx` | Immersive Focus Player (HLS video, article reader, watermarked PDF, heartbeat) |
| `/app/assignments` | `src/app/(student)/app/assignments/page.tsx` | Student Course Assignments directory |
| `/app/assignments/[id]` | `src/app/(student)/app/assignments/[id]/page.tsx` | Assignment Rubric Submission & Feedback Canvas |
| `/app/quizzes` | `src/app/(student)/app/quizzes/page.tsx` | Student Quiz History & Attempts directory |
| `/app/quizzes/[id]` | `src/app/(student)/app/quizzes/[id]/page.tsx` | Timed Quiz Exam Canvas (autosave, radio options, timer) |
| `/app/certificates` | `src/app/(student)/app/certificates/page.tsx` | Earned Course Certificates vault with PDF download |
| `/app/orders` | `src/app/(student)/app/orders/page.tsx` | Student Order History and payment invoices |
| `/app/profile` | `src/app/(student)/app/profile/page.tsx` | Student Profile & Active Device Session revocation management |

### Group D: Admin Portal (Instructor Operations)
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/admin` | `src/app/(admin)/admin/page.tsx` | Operations Console (Course inventory, enrollments, sales, student count) |
| `/admin/courses` | `src/app/(admin)/admin/courses/page.tsx` | Course Catalog Management & Draft Revision forking |
| `/admin/courses/new` | `src/app/(admin)/admin/courses/new/page.tsx` | New Masterclass creation form |
| `/admin/courses/[id]/edit` | `src/app/(admin)/admin/courses/[id]/edit/page.tsx` | Curriculum Builder (Sections, Lessons reordering, Publish Checklist) |
| `/admin/media` | `src/app/(admin)/admin/media/page.tsx` | Media & Video Library (private upload form, transcoding status, asset grid) |
| `/admin/students` | `src/app/(admin)/admin/students/page.tsx` | Student Roster directory with lookup and session status |
| `/admin/enrollments` | `src/app/(admin)/admin/enrollments/page.tsx` | Manual Student Enrollment Grants console |
| `/admin/orders` | `src/app/(admin)/admin/orders/page.tsx` | Commercial Orders Ledger (transactions, order status, amounts) |

### Group E: Staff Portal
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/staff` | `src/app/(staff)/staff/page.tsx` | Staff Operations Dashboard & Grading Queue overview |
| `/staff/grading` | `src/app/(staff)/staff/grading/page.tsx` | Assignment Submission Grading Queue directory |
| `/staff/grading/[submissionId]` | `src/app/(staff)/staff/grading/[submissionId]/page.tsx` | Rubric Evaluation Workspace (student code inspection, criteria grading) |

### Group F: Super Admin Portal (Platform Governance)
| Route | Page File Path | Purpose |
| :--- | :--- | :--- |
| `/control` | `src/app/(control)/control/page.tsx` | Platform Governance Overview (Financial KPIs, user breakdown, quick actions) |
| `/control/users` | `src/app/(control)/control/users/page.tsx` | User Directory & Role Assignment console |
| `/control/users/[id]` | `src/app/(control)/control/users/[id]/page.tsx` | User Profile & Granular Role Governance |
| `/control/admins` | `src/app/(control)/control/admins/page.tsx` | Administrator Staffing Hub |
| `/control/staff` | `src/app/(control)/control/staff/page.tsx` | Staff Grader Management |
| `/control/sessions` | `src/app/(control)/control/sessions/page.tsx` | Security & Session Surveillance console (IP masking, emergency containment) |
| `/control/permissions` | `src/app/(control)/control/permissions/page.tsx` | Granular Role-Permissions Matrix (45 permissions) |
| `/control/courses` | `src/app/(control)/control/courses/page.tsx` | Course Governance & Curriculum stats |
| `/control/blog` | `src/app/(control)/control/blog/page.tsx` | Brand Blog CMS |
| `/control/notes` | `src/app/(control)/control/notes/page.tsx` | Notes CMS & Binary PDF replacement |
| `/control/offers` | `src/app/(control)/control/offers/page.tsx` | Offers & Promotional Campaigns management |
| `/control/payments` | `src/app/(control)/control/payments/page.tsx` | Financial Surveillance & Refund Ledger |
| `/control/settings` | `src/app/(control)/control/settings/page.tsx` | Platform Brand Settings & Master Secret Isolation |
| `/control/audit` | `src/app/(control)/control/audit/page.tsx` | Immutable Audit Logs Ledger |

---

## 3. Systematic Unslop Audit by Domain

### A. Public Website Domain
- **Problems**:
  - Hero section uses an artificial radial blur blob (`bg-gradient-to-br from-accent-mint/40 via-accent-peach/20 blur-3xl`) that adds visual slop without communicating product substance.
  - Category badge above headline includes an artificial sparkle icon (`<Sparkles className="mr-1.5 h-3.5 w-3.5" />`) reading as generic AI flair.
  - Three value-prop cards use rainbow icon containers (`bg-accent-mint/60`, `bg-accent-peach/60`, `bg-amber-100`).
  - CourseCard components use `hover:-translate-y-1 hover:shadow-elevated active:scale-[0.99]` bouncy transforms.
  - Course Detail page assigns 4 different rainbow colors to lesson types (Video: teal, Article: amber, Quiz: purple, Assignment: coral).
- **Preserved Elements**:
  - Direct single-instructor identity and authoritative copywriting.
  - Dynamic API course catalog loading with real price rendering and tags.
  - Cryptographic certificate verification seal and QR rendering.
- **Improvements**:
  - Replace blurred radial blob with clean, calm architectural whitespace and subtle hairline dividers (`border-[#E6E2DC]`).
  - Hero headline: Refined typography at weight 600 with high-contrast tabular styling.
  - Course cards: Quiet, dignified editorial cards with fine 1px hairlines, crisp thumbnail framing, and calm hover highlight without bouncy zoom.

### B. Authentication Domain
- **Problems**:
  - Left panel in `AuthLayout` contains decorative floating circles (`rounded-full bg-white/5`) that look like generic SaaS stock illustration.
  - Card on the right uses heavy drop shadow (`shadow-lg border-slate-200`).
  - Shouting headline: `font-heading font-extrabold`.
- **Preserved Elements**:
  - Google OAuth integration and server-side redirect safety (`getSafeRedirectUrl`).
  - Interactive client-side PasswordStrengthMeter with real-time entropy calculation.
  - Form validation via Zod schemas and clean error banners (`ErrorAlert`).
- **Improvements**:
  - Quiet, dignified split layout: The left storytelling panel uses deep primary teal (`#006B60`) with clean typography and hairline borders rather than floating bubbles.
  - Form card uses subtle 1px border (`border-[#E6E2DC]`), crisp inputs (`rounded-md h-11`), and clear focus rings.

### C. Student Experience Domain
- **Problems**:
  - Greeting headline: `Welcome back, Alex! 👋` with an emoji (Unslop sign: greeting headline with wave emoji).
  - Metric cards in `/app` use 3 pastel backgrounds (`bg-accent-mint/60`, `bg-accent-peach/60`, `bg-amber-100`).
  - Focus Player (`/learn/[courseId]/[lessonId]`): Header uses generic `bg-white/95` and `bg-slate-50` backdrop rather than the warm brand environment.
  - CurriculumSidebar uses pill badges for completed states.
- **Preserved Elements**:
  - HLS video player with adaptive bitrate selection and 10s progress heartbeat.
  - Dynamic watermarked PDF viewer with real-time student identity overlay.
  - Timed quiz autosave and question bank navigation.
  - Assignment rubric evaluation view.
- **Improvements**:
  - Student Dashboard: Title becomes `Learning Overview`, with quiet, data-focused metric cards showing enrolled courses, completed lessons, and quiz scores with `tabular-nums`.
  - Immersive Focus Player: True dark studio theater mode for video streaming or crisp distraction-free reader mode for articles and PDFs.
  - Refined lesson completion markers using subtle checkmarks rather than loud rainbow pills.

### D. Instructor Admin & Staff Domain
- **Problems**:
  - Previously featured the 4-color rainbow card pattern and duplicated "Management Portals" column (already redesigned in our local checkpoint experiment).
  - CurriculumBuilder in `/admin/courses/[id]/edit` has dense, cluttered section cards with excessive borders.
  - Media Library `/admin/media` uses heavy upload dropzone borders.
- **Preserved Elements**:
  - Deep revision cloning, immutable published snapshots, and relational publish checklist modal.
  - Direct presigned S3/GCS media upload pipeline and HLS transcode job tracking.
  - Rubric grading submission evaluation.
- **Improvements**:
  - Maintain the calm, authoritative Unslop Admin Dashboard approved in the experiment.
  - Clean up CurriculumBuilder with structured drag-and-drop handles, quiet action icons, and inline lesson type tags.

### E. Super Admin Platform Governance Domain
- **Problems**:
  - OverviewMetricsGrid uses rainbow squares (`bg-teal-50`, `bg-blue-50`, `bg-purple-50`, `bg-emerald-50`).
  - Metrics cards use uppercase shouting labels: `VERIFIED REVENUE`, `STUDENT & USER ROSTER`, `ACTIVE CURRICULUM`, `SECURITY & SESSION ENGINE`.
  - Excessive font weight (weight 800) on numbers.
- **Preserved Elements**:
  - Sole Super Admin row-level database serialization lock.
  - Emergency platform-wide session containment and IP masking.
  - 45 canonical role permissions matrix.
  - Real database financial aggregation without rounding drift.
- **Improvements**:
  - High-density, high-authority telemetry console.
  - Clean tabular figures with monospace financial numbers (`tabular-nums font-mono`).
  - Sentence case metric labels with quiet neutral hairlines.

---

## 4. Proposed Design Direction (The Unslop 5-Line Framework)

* **Product**: A proprietary, direct-to-student educational platform where an expert instructor publishes masterclasses, mentors students, and tracks commercial operations without marketplace clutter.
* **Character**: `calm, exact, authoritative` (no shouting weights, no rainbow tiles, no marketing hype).
* **World**: An instructor's architectural studio and publishing atelier—warm cream surfaces, quiet deep teal accents, crisp tabular typography, and fine hairline borders that feel like high-end stationery.
* **Moments**:
  1. **The Immersive Focus Player**: A distraction-free learning canvas where the student's eyes focus entirely on high-bitrate video, watermarked code walkthroughs, and rubric evaluations.
  2. **The Course Curriculum Matrix**: An elegant, high-density editorial inventory showing draft revisions, published snapshots, and verified commercial tuition.
* **Signature**: The discreet **Studio Architectural Telemetry Bar** (`Single-Instructor Direct · Atomic 1-Active Session · HLS Multi-Res Streaming`) providing immediate visual confirmation of platform integrity.

---

## 5. Design System Proposal

### 1. Color Palette Tokens
| Role | Hex | Semantic Use |
| :--- | :--- | :--- |
| **Workspace Canvas** | `#FAF7F2` | Primary page background across admin, student, and storefront. Soft, warm, prevents glare. |
| **Pure Surface** | `#FFFFFF` | Card backgrounds, dialog containers, form panels. Crisp and elevated. |
| **Deep Primary Teal** | `#006B60` | Sole brand accent: primary action buttons, active sidebar items, progress fills. |
| **Deep Teal Hover** | `#00534B` | Interactive state for primary brand buttons. |
| **Warm Charcoal** | `#191B24` | Primary text, titles, big metric figures. High legibility, softer than `#000000`. |
| **Secondary Slate** | `#66666B` | Subtitles, descriptive copy, inactive navigation icons. |
| **Muted Metadata** | `#929292` | Captions, timestamps, table column headers, helper notes. |
| **Hairline Border** | `#E6E2DC` | 1px border hairlines, dividers, table row separations. |
| **Warm Peach Subtle** | `#FCE8E1` | Secondary tag background, subtle alert container. |
| **Positive Emerald** | `#16a34a` | Status published, passed quizzes, verified payments (`bg-emerald-50 text-emerald-800`). |
| **Warning Amber** | `#d97706` | Draft revisions, pending review, expiring sessions (`bg-amber-50 text-amber-800`). |
| **Negative Rose** | `#dc2626` | Revoked sessions, failed uploads, errors (`bg-rose-50 text-rose-800`). |

### 2. Typography Scale & Weights
- **Interface Font**: Plus Jakarta Sans (`var(--font-plus-jakarta)`), backed by system sans-serif.
- **Monospace Font**: JetBrains Mono / Geist Mono for currency, code, slugs, hashes, and tabular numbers.
- **Weight Restraint**: Maximum weight 600 (`font-semibold`) for headers; weight 500 (`font-medium`) for metrics; weight 400 (`font-normal`) for body. Weight 800 (`font-extrabold`) is prohibited.
- **Hierarchy**:
  - `Hero Display`: 36px–44px (line height 1.15, -0.02em tracking, font-semibold)
  - `Page Title`: 24px–28px (line height 1.25, -0.01em tracking, font-semibold)
  - `Section / Card Title`: 16px–18px (line height 1.3, font-semibold)
  - `Body / Form Text`: 14px–15px (line height 1.5, font-normal)
  - `Meta / Captions`: 12px (line height 1.4, font-medium, tabular)

### 3. Spacing & Geometric Grid
- **Scale**: Strict multiples of 4px: `4px, 8px, 12px, 16px, 20px, 24px, 32px, 48px, 64px`.
- **Card Padding**: Standardized `p-5 sm:p-6`.
- **Section Rhythm**: `space-y-6 sm:space-y-8` between major functional sections.
- **Nested Radii Math**: $R_{\text{inner}} = R_{\text{outer}} - \text{padding}$.
  - Cards: `rounded-xl` (14px)
  - Controls & Buttons: `rounded-md` (8px–10px)
  - Small Tags: `rounded-md` (6px)
  - *No arbitrary 9999px pills on cards or metric headers.*

---

## 6. Page-by-Page Redesign Plan (All 46 Routes)

### Group A: Public Website
1. **Homepage (`/`)**:
   - *Current Problems*: Distracting radial blur blob, sparkle icon badge, rainbow cards, bouncy hover zoom.
   - *Proposed Changes*: Remove radial blur blob; replace with calm warm cream canvas (`#FAF7F2`); display quiet editorial typography; remove rainbow icon boxes; render clean masterclass preview cards with 1px hairline borders.
   - *Responsive*: Hero stacks gracefully on mobile with left-aligned headline and full-width CTA buttons.
2. **Course Catalog (`/courses`)**:
   - *Current Problems*: Heavy border filters, loud tag pills, jarring hover scale on cards.
   - *Proposed Changes*: Clean search input with subtle focus ring; filter chips using calm neutral borders; 3-column card grid with quiet thumbnail framing and tabular price display.
   - *Responsive*: 1-column on mobile, 2-column on tablet, 3-column on desktop.
3. **Course Details (`/courses/[slug]`)**:
   - *Current Problems*: Rainbow icons for lesson types (video, article, quiz, assignment); loud sticky checkout box.
   - *Proposed Changes*: Harmonize lesson icons to quiet text secondary; clean curriculum accordion with duration in mono `tabular-nums`; refined sticky enrollment summary card with clear guarantee.
4. **Certificate Verification (`/verify/certificate/[hash]`)**:
   - *Current Problems*: Cluttered badge layout, low visual authority for a cryptographic certificate.
   - *Proposed Changes*: High-craft diploma framing; official cryptographic seal in deep teal; monospace hash display with 1-click copy; direct verification confirmation.

### Group B: Authentication
5. **Login (`/login`)**:
   - *Current Problems*: Split screen has floating decorative bubbles on the left; form card has heavy drop shadows.
   - *Proposed Changes*: Editorial brand storytelling panel in deep teal `#006B60`; card uses fine 1px hairline and quiet Google OAuth button; inputs at 44px height.
6. **Signup (`/signup`)**:
   - *Current Problems*: PasswordStrengthMeter has harsh neon bars; form feels crowded on mobile.
   - *Proposed Changes*: Subtle segment bars for password entropy; clear helper text; quiet checkbox for terms.
7. **Forgot Password (`/forgot-password`)**:
   - *Current Problems*: Overly large empty space surrounding a single input field.
   - *Proposed Changes*: Centered compact card with clear recovery instructions and immediate feedback state.
8. **Reset Password (`/reset-password`)**:
   - *Current Problems*: Generic template look, duplicate card styling.
   - *Proposed Changes*: Consistent auth shell with real-time password confirmation validation.
9. **Verify Email (`/verify-email`)**:
   - *Current Problems*: Spinning circle in empty card.
   - *Proposed Changes*: Dignified verification state with clear next-step actions.
10. **Onboarding Claim (`/onboarding/claim`)**:
    - *Current Problems*: Disconnected from staff workflow.
    - *Proposed Changes*: Professional role welcome banner (Staff/Admin) with password creation.

### Group C: Student Experience
11. **Student Dashboard (`/app`)**:
    - *Current Problems*: `Welcome back, Alex! 👋` greeting headline; rainbow metric tiles (`mint`, `peach`, `amber`).
    - *Proposed Changes*: Headline changed to `Learning Overview`; quiet white metric cards with tabular counts; "Continue Learning" course cards with progress bars in deep teal.
12. **Enrolled Courses (`/app/courses`)**:
    - *Current Problems*: Redundant card formatting, unequal card heights.
    - *Proposed Changes*: High-density progress grid showing percent complete, remaining lessons, and direct "Resume" button.
13. **Course Learning Path (`/app/courses/[id]`)**:
    - *Current Problems*: Visual clutter in section list.
    - *Proposed Changes*: Clean curriculum timeline with completed lesson indicators.
14. **Focus Learning Player (`/learn/[courseId]/[lessonId]`)**:
    - *Current Problems*: Header uses generic slate-50; player lacks theater/reading contrast.
    - *Proposed Changes*: Dedicated high-immersion canvas; dark framing for video streaming; distraction-free typography for articles; embedded PDF watermarking with clean toolbar.
15. **Assignments (`/app/assignments`)**:
    - *Current Problems*: Status badges are loud rainbow pills.
    - *Proposed Changes*: Clean tabular list with due dates, submission status, and score pill.
16. **Assignment Submission Canvas (`/app/assignments/[id]`)**:
    - *Current Problems*: Rubric criteria format is hard to read on mobile.
    - *Proposed Changes*: Two-panel desktop split (rubric criteria on left, submission editor on right); stacked layout on mobile.
17. **Quizzes (`/app/quizzes`)**:
    - *Current Problems*: Inconsistent attempt history table.
    - *Proposed Changes*: Tabular scorecard with score percentage, duration, and pass/fail indicator.
18. **Quiz Exam Canvas (`/app/quizzes/[id]`)**:
    - *Current Problems*: Timer flashes and causes anxiety; radio buttons lack clean active states.
    - *Proposed Changes*: Calm fixed timer bar in header; spacious radio options with keyboard shortcut navigation; clear autosave indicator.
19. **Certificates Vault (`/app/certificates`)**:
    - *Current Problems*: Empty space when only 1-2 certificates exist.
    - *Proposed Changes*: Elegant certificate cards with preview thumbnail, issue date, and 1-click PDF download / public link.
20. **Student Orders (`/app/orders`)**:
    - *Current Problems*: Generic table layout.
    - *Proposed Changes*: Crisp invoice ledger with transaction IDs, INR pricing in mono, and payment receipt download.
21. **Student Profile (`/app/profile`)**:
    - *Current Problems*: Single-active session warning looks like an error alert.
    - *Proposed Changes*: Clear device security card showing current active session (IP, browser, last active) with 1-click revocation.

### Group D: Instructor Admin Portal
22. **Admin Operations Console (`/admin`)**:
    - *Audit Baseline*: Implemented in our verified Unslop experiment.
    - *Approved Design*: Quiet metrics, truthful sales telemetry, high-density course matrix, studio quick jump, architecture health.
23. **Course Management (`/admin/courses`)**:
    - *Current Problems*: Action buttons are crammed into table cells.
    - *Proposed Changes*: Clean directory with status filter tabs (All, Published, Draft, Archived); direct "Fork Revision" action.
24. **Create Course (`/admin/courses/new`)**:
    - *Current Problems*: Input fields lack helpful contextual hints.
    - *Proposed Changes*: Stepped form (Basic Details, Slug auto-generation, Pricing) with real-time preview card.
25. **Curriculum Builder (`/admin/courses/[id]/edit`)**:
    - *Current Problems*: Heavy nested boxes, unclear drag handles.
    - *Proposed Changes*: Streamlined section hierarchy; clean lesson rows with type badges and quick edit modals; top publishing checklist pill.
26. **Media Library (`/admin/media`)**:
    - *Current Problems*: Upload form and grid compete for attention.
    - *Proposed Changes*: Compact top uploader with progress feedback; asset grid showing transcoding status (`QUEUED`, `PROCESSING`, `READY`) with playback preview.
27. **Student Roster (`/admin/students`)**:
    - *Current Problems*: Wide table with awkward horizontal scrolling on small screens.
    - *Proposed Changes*: Responsive student cards on mobile, clean table on desktop with search and enrollment counts.
28. **Enrollment Grants (`/admin/enrollments`)**:
    - *Current Problems*: Modal form lacks clear course selector.
    - *Proposed Changes*: Fast student/course selector with instant grant action and revocation confirmation.
29. **Orders Ledger (`/admin/orders`)**:
    - *Current Problems*: Misaligned currency figures.
    - *Proposed Changes*: Monospace tabular INR formatting, clear payment gateway ID links, and status indicators.

### Group E: Staff Portal
30. **Staff Operations (`/staff`)**:
    - *Current Problems*: Blank greeting and empty stats.
    - *Proposed Changes*: Pending grading queue summary, recent feedback ledger, and assignment due dates.
31. **Grading Directory (`/staff/grading`)**:
    - *Current Problems*: Status filters are unstyled select inputs.
    - *Proposed Changes*: Clean filter tabs (Needs Grading, Graded, Overdue) with submission date sorting.
32. **Grading Workspace (`/staff/grading/[submissionId]`)**:
    - *Current Problems*: Student text and rubric scores are crowded.
    - *Proposed Changes*: Split screen: Student code submission on left (monospaced syntax styling), interactive rubric slider on right with auto-calculating score.

### Group F: Super Admin Platform Governance
33. **Super Admin Overview (`/control`)**:
    - *Current Problems*: Rainbow stat tiles, uppercase labels, heavy drop shadows.
    - *Proposed Changes*: High-authority governance console; calm neutral cards; monospace financial metrics; quick emergency actions.
34. **User Governance (`/control/users` & `[id]`)**:
    - *Current Problems*: Role editing dropdown looks like a generic select.
    - *Proposed Changes*: User inspection drawer with active session count, role badges, and audited role changes.
35. **Admin Hub (`/control/admins`) & Staff (`/control/staff`)**:
    - *Current Problems*: Redundant pages with identical layouts.
    - *Proposed Changes*: Unified invitation drawer with temporary token generator and active assignment roster.
36. **Security & Session Surveillance (`/control/sessions`)**:
    - *Current Problems*: IP masking eyeball icon jumps layout; containment modal lacks clear danger indicator.
    - *Proposed Changes*: High-contrast security surveillance grid; red border containment banner; audited single-session termination.
37. **Permissions Matrix (`/control/permissions`)**:
    - *Current Problems*: Massive checkbox table that overflows viewports.
    - *Proposed Changes*: Grouped accordion permissions by domain (Media, Curriculum, Commerce, Governance) with role badges.
38. **Course Governance (`/control/courses`)**:
    - *Current Problems*: Lacks curriculum stats.
    - *Proposed Changes*: Comprehensive course audit table with section/lesson counts, active revision ID, and force-publish overrides.
39. **Blog CMS (`/control/blog`) & Notes CMS (`/control/notes`)**:
    - *Current Problems*: File upload input is raw browser unstyled.
    - *Proposed Changes*: Clean Markdown editor preview and binary PDF replacement dropzone with cryptographic hash check.
40. **Offers & Discounts (`/control/offers`)**:
    - *Current Problems*: Coupon code input lacks automatic uppercase formatting.
    - *Proposed Changes*: Monospace coupon tag formatting, active date range pickers, and live usage counters.
41. **Payment Surveillance (`/control/payments`)**:
    - *Current Problems*: Mixed integer and float formatting.
    - *Proposed Changes*: Strict integer paise display with zero rounding drift; clear gross vs. net vs. refund breakdown.
42. **Platform Settings (`/control/settings`)**:
    - *Current Problems*: Master secret isolation notice looks like a generic warning.
    - *Proposed Changes*: Official security certificate banner confirming cryptographic secrets are isolated in environment variables.
43. **Audit Logs (`/control/audit`)**:
    - *Current Problems*: Raw JSON metadata dumped into table cells.
    - *Proposed Changes*: Expandable JSON viewer with copy payload button, actor identity badge, and timestamp in local time.

---

## 7. Change Impact & Safety Report

- **Production UI Files Modified**: **0 files modified** during this audit phase. (The local checkpoint experiment on `/admin` remains safely preserved).
- **Production Routing Modified**: **0 routes altered**.
- **Backend / Database Impact**: **Zero migrations, zero schema changes, zero API alterations**.
- **Dependencies Installed**: **Zero dependencies installed**.
- **Artifacts Created for Review**:
  - `docs/redesign_preview/FULL_LMS_UI_UX_AUDIT_REPORT.md` (This document)
  - `docs/redesign_preview/index.html` (Interactive Isolated Preview Gallery)
  - `docs/redesign_preview/screenshots/` (High-resolution Before/After screenshots across Desktop and Mobile)
  - `docs/redesign_preview/lms_full_redesign_preview.mp4` (Official 1920x1080 Comparison Video)

---

## 8. Final Approval Status

**REDESIGN STATUS: WAITING FOR OWNER REVIEW**

The complete redesign specification, visual gallery, and Before/After video artifact are ready for your inspection. No further changes will be made until explicit approval is granted.
