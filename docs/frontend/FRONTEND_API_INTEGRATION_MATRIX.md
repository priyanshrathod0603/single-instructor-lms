# Frontend API Integration Matrix (FRONTEND_API_INTEGRATION_MATRIX)

**Project**: Single-Instructor Learning Management System (LMS)  
**Lifecycle Phase**: Phase 2 — Frontend Development  
**Document Type**: Complete API Contract & Consumer Integration Matrix  
**Date**: 2026-11-15  
**Verification Baseline**: 75 verified backend endpoints across 15 routers in `backend/app/api/v1/`  
**Execution Mode**: Empirical Mapping (Zero Invented Endpoints)  

---

## 1. Overview & Standard Envelope Conventions

All API calls originate from the client using the versioned prefix `/api/v1/`.

### Success Response Format:
```json
{
  "data": { ... },
  "pagination": { "next_cursor": "...", "has_more": true, "page_size": 20 }
}
```

### Error Response Format:
```json
{
  "success": false,
  "error": {
    "code": "STRING_ERROR_CODE",
    "message": "Human-readable description",
    "details": {},
    "request_id": "req-uuid"
  }
}
```

---

## 2. Exhaustive API Integration Matrix (All 75 Verified Endpoints)

| # | HTTP Method | Endpoint Path | Auth Req. | Permission / Role Req. | Request Schema (Pydantic / Payload) | Response Schema / Output | Error Codes Handled | Frontend Consumer Component | Status |
| :-: | :--- | :--- | :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| 1 | `POST` | `/api/v1/auth/register` | No | None (Public) | `UserRegisterRequest` (`email`, `password`, `full_name`) | `MessageResponse` (`message`) | `400 INVALID_INPUT`, `409 EMAIL_EXISTS`, `429 RATE_LIMIT_EXCEEDED` | `SignupForm` (`/signup`) | `VERIFIED` |
| 2 | `POST` | `/api/v1/auth/login` | No | None (Public) | `UserLoginRequest` (`email`, `password`) | `LoginResponse` (`user`, `access_token`, `token_type`, `expires_in`) + Sets `__Host-lms_session` cookie | `400 INVALID_INPUT`, `401 INVALID_CREDENTIALS`, `403 ACCOUNT_SUSPENDED`, `429 RATE_LIMIT_EXCEEDED` | `LoginForm` (`/login`) | `VERIFIED` |
| 3 | `POST` | `/api/v1/auth/logout` | Yes | Authenticated Session | None (Cookie transmitted) | `MessageResponse` (`message`) + Clears `__Host-lms_session` cookie | `401 NOT_AUTHENTICATED` | `UserDropdown`, `LogoutButton` | `VERIFIED` |
| 4 | `GET` | `/api/v1/auth/me` | Yes | Authenticated Session | None | `UserResponse` (`id`, `email`, `full_name`, `roles`, `is_active`, `is_verified`) | `401 NOT_AUTHENTICATED`, `401 SESSION_REVOKED` | `AuthProvider`, `UserProfileCard` (`/app/profile`) | `VERIFIED` |
| 5 | `POST` | `/api/v1/auth/refresh` | Yes | Active Session Cookie | None | `dict` (`access_token`, `token_type`, `expires_in: 900`) | `401 SESSION_REVOKED`, `401 SESSION_EXPIRED` | `apiClient` token refresher | `VERIFIED` |
| 6 | `POST` | `/api/v1/auth/verify-email` | No | None (Public) | `VerifyEmailRequest` (`token`) | `MessageResponse` (`message`) | `400 TOKEN_EXPIRED`, `400 INVALID_TOKEN` | `VerifyEmailPage` (`/verify-email`) | `VERIFIED` |
| 7 | `POST` | `/api/v1/auth/resend-verification` | No | None (Public) | `ResendVerificationRequest` (`email`) | `MessageResponse` (`message`) | `429 RATE_LIMIT_EXCEEDED` | `ResendVerificationModal` | `VERIFIED` |
| 8 | `POST` | `/api/v1/auth/password-reset/request`| No | None (Public) | `PasswordResetRequest` (`email`) | `MessageResponse` (`message`) | `429 RATE_LIMIT_EXCEEDED` | `ForgotPasswordForm` (`/forgot-password`) | `VERIFIED` |
| 9 | `POST` | `/api/v1/auth/password-reset/confirm`| No | None (Public) | `PasswordResetConfirmRequest` (`token`, `new_password`) | `MessageResponse` (`message`) | `400 TOKEN_EXPIRED`, `400 PASSWORD_TOO_WEAK` | `ResetPasswordForm` (`/reset-password`) | `VERIFIED` |
| 10| `POST` | `/api/v1/auth/oauth/google` | No | None (Public) | `GoogleOAuthRequest` (`id_token`) | `LoginResponse` (`user`, `access_token`) + Sets `__Host-lms_session` cookie | `401 INVALID_OAUTH_TOKEN`, `401 OAUTH_EMAIL_UNVERIFIED` | `GoogleLoginButton` (`/login`, `/signup`) | `VERIFIED` |
| 11| `POST` | `/api/v1/auth/onboarding/claim` | No | None (Invitee) | `StaffOnboardingClaimRequest` (`token`, `password`, `full_name`) | `LoginResponse` (`user`, `access_token`) + Sets session cookie | `400 INVALID_TOKEN`, `400 TOKEN_EXPIRED` | `StaffClaimPage` (`/onboarding/claim`) | `VERIFIED` |
| 12| `GET` | `/api/v1/users` | Yes | `users:view_all` (Admin/Super Admin) | Query params (`page`, `per_page`, `role`, `search`) | `UserListResponse` (`items: list[UserResponse]`, `total`, `page`, `pages`) | `401 UNAUTHORIZED`, `403 PERMISSION_DENIED` | `AdminUserTable` (`/admin/students`) | `VERIFIED` |
| 13| `POST` | `/api/v1/users/staff/invite` | Yes | `staff:invite` (Admin/Super Admin) | `StaffInviteRequest` (`email`, `full_name`, `role: STAFF|ADMIN`) | `MessageResponse` (`message`) | `400 INVALID_ROLE`, `409 EMAIL_EXISTS`, `403 PERMISSION_DENIED` | `InviteStaffModal` (`/control/staff`) | `VERIFIED` |
| 14| `GET` | `/api/v1/users/{id}` | Yes | `users:view_all` or Own Profile | Path param `id: UUID` | `UserResponse` (`id`, `email`, `full_name`, `roles`, `is_active`) | `404 USER_NOT_FOUND`, `403 FORBIDDEN` | `UserDetailDrawer` | `VERIFIED` |
| 15| `PATCH`| `/api/v1/users/{id}` | Yes | Own Profile or Admin | Path param `id`, Body: `UserUpdateRequest` (`full_name`) | `UserResponse` | `400 INVALID_INPUT`, `404 USER_NOT_FOUND` | `ProfileEditForm` (`/app/profile`) | `VERIFIED` |
| 16| `PATCH`| `/api/v1/users/{id}/roles` | Yes | `roles:assign` (Super Admin) | Path param `id`, Body: `UserRoleAssignRequest` (`roles: list[str]`) | `UserResponse` | `403 PERMISSION_DENIED`, `422 LAST_SUPER_ADMIN_CANNOT_BE_DEMOTED` | `RoleAssignmentModal` (`/control/permissions`) | `VERIFIED` |
| 17| `PATCH`| `/api/v1/users/{id}/status` | Yes | `users:manage_status` (Super Admin) | Path param `id`, Body: `UserStatusUpdateRequest` (`is_active: bool`, `reason`) | `UserResponse` | `403 PERMISSION_DENIED`, `422 CANNOT_SUSPEND_LAST_SUPER_ADMIN` | `UserStatusToggleModal` (`/admin/students`) | `VERIFIED` |
| 18| `GET` | `/api/v1/courses` | No | None (Public) | Query params (`page`, `per_page`, `search`, `tag`) | `CourseListResponse` (`items: list[CoursePublicResponse]`, `total`) | None | `PublicCatalogGrid` (`/courses`, `/`) | `VERIFIED` |
| 19| `POST` | `/api/v1/courses` | Yes | `course:create` (Admin/Super Admin) | `CourseCreateRequest` (`title`, `slug`, `description`, `price_amount`, `currency`) | `CourseResponse` (`id`, `title`, `slug`, `current_draft_revision_id`) | `409 SLUG_EXISTS`, `403 PERMISSION_DENIED` | `CreateCourseModal` (`/admin/courses`) | `VERIFIED` |
| 20| `GET` | `/api/v1/courses/manage` | Yes | `course:view_all` (Admin/Super Admin) | Query params (`page`, `per_page`, `status_filter`) | `CourseManageListResponse` (`items`, `total`) | `403 PERMISSION_DENIED` | `AdminCourseTable` (`/admin/courses`) | `VERIFIED` |
| 21| `GET` | `/api/v1/courses/{id_or_slug}` | No | None (Public) | Path param `id_or_slug: str` | `CourseDetailResponse` (`id`, `title`, `slug`, `description`, `price_amount`, `curriculum_tree`) | `404 COURSE_NOT_FOUND` | `CourseDetailPage` (`/courses/:slug`), `AppCourseView` (`/app/courses/:id`) | `VERIFIED` |
| 22| `PATCH`| `/api/v1/courses/{id}` | Yes | `course:edit` (Admin/Super Admin) | Path param `id`, Body: `CourseUpdateRequest` (`title`, `description`, `price_amount`) | `CourseResponse` | `404 COURSE_NOT_FOUND`, `403 PERMISSION_DENIED` | `CourseSettingsTab` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 23| `DELETE`| `/api/v1/courses/{id}` | Yes | `course:archive` (Super Admin) | Path param `id: UUID` | `MessageResponse` (`message`) | `404 COURSE_NOT_FOUND`, `403 PERMISSION_DENIED` | `ArchiveCourseDialog` (`/admin/courses`) | `VERIFIED` |
| 24| `GET` | `/api/v1/courses/{id}/publish-checklist`| Yes | `course:edit` (Admin/Super Admin) | Path param `id: UUID` | `PublishChecklistResponse` (`ready_to_publish: bool`, `checks: list[CheckItem]`) | `404 COURSE_NOT_FOUND` | `PublishPreflightModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 25| `POST` | `/api/v1/courses/{id}/revisions` | Yes | `course:revision_create` (Admin/Super Admin) | Path param `id: UUID` | `CourseRevisionResponse` (`id`, `revision_number`, `status: DRAFT`) | `409 ACTIVE_DRAFT_EXISTS` | `NewRevisionButton` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 26| `GET` | `/api/v1/courses/{id}/revisions/{rev_id}`| Yes | `course:edit` (Admin/Super Admin) | Path params `id`, `rev_id` | `CourseRevisionDetailResponse` (`id`, `sections: list[SectionDetail]`) | `404 REVISION_NOT_FOUND` | `CourseBuilderCanvas` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 27| `POST` | `/api/v1/courses/{id}/revisions/{rev_id}/publish`| Yes | `course:publish` (Super Admin) | Path params `id`, `rev_id` | `CourseResponse` (`id`, `status: PUBLISHED`, `live_revision_id`) | `422 CHECKLIST_FAILED`, `403 PERMISSION_DENIED` | `PublishRevisionButton` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 28| `POST` | `/api/v1/courses/{id}/revisions/{rev_id}/sections`| Yes | `curriculum:manage` (Admin/Super Admin) | Path params `id`, `rev_id`, Body: `SectionCreateRequest` (`title`, `description`) | `SectionResponse` (`id`, `title`, `sort_order`) | `404 REVISION_NOT_FOUND` | `AddSectionButton` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 29| `PUT` | `/api/v1/courses/{id}/revisions/{rev_id}/sections/reorder`| Yes | `curriculum:reorder` (Admin/Super Admin) | Path params, Body: `SectionReorderRequest` (`section_ids: list[UUID]`, `expected_version`) | `MessageResponse` (`message`) | `409 CONCURRENT_CONFLICT` | `DraggableSectionList` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 30| `PATCH`| `/api/v1/sections/{id}` | Yes | `curriculum:manage` (Admin/Super Admin) | Path param `id`, Body: `SectionUpdateRequest` (`title`, `description`) | `SectionResponse` | `404 SECTION_NOT_FOUND` | `SectionHeader` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 31| `DELETE`| `/api/v1/sections/{id}` | Yes | `curriculum:manage` (Admin/Super Admin) | Path param `id: UUID` | `MessageResponse` (`message`) | `404 SECTION_NOT_FOUND` | `DeleteSectionDialog` | `VERIFIED` |
| 32| `POST` | `/api/v1/sections/{id}/lessons` | Yes | `curriculum:manage` (Admin/Super Admin) | Path param `id`, Body: `LessonCreateRequest` (`title`, `lesson_type`, `is_preview`) | `LessonResponse` (`id`, `title`, `lesson_type`, `sort_order`) | `404 SECTION_NOT_FOUND` | `AddLessonModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 33| `PUT` | `/api/v1/sections/{id}/lessons/reorder`| Yes | `curriculum:reorder` (Admin/Super Admin) | Path param `id`, Body: `LessonReorderRequest` (`lesson_ids: list[UUID]`, `expected_version`) | `MessageResponse` (`message`) | `409 CONCURRENT_CONFLICT` | `DraggableLessonList` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 34| `DELETE`| `/api/v1/resources/{id}` | Yes | `curriculum:manage` (Admin/Super Admin) | Path param `id: UUID` | `MessageResponse` (`message`) | `404 RESOURCE_NOT_FOUND` | `LessonResourceDeleteButton` | `VERIFIED` |
| 35| `POST` | `/api/v1/media/upload-intent` | Yes | `media:upload` (Admin/Super Admin) | `UploadIntentRequest` (`file_name`, `file_size_bytes`, `mime_type`, `purpose`) | `UploadIntentResponse` (`upload_url`, `media_id`, `expires_in_seconds`) | `400 INVALID_MIME_TYPE`, `413 PAYLOAD_TOO_LARGE` | `MediaUploader` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 36| `POST` | `/api/v1/media/{id}/confirm` | Yes | `media:upload` (Admin/Super Admin) | Path param `id`, Body: `UploadConfirmRequest` (`etag`, `actual_size_bytes`) | `MediaAssetResponse` (`id`, `status: PROCESSING|READY`, `duration_seconds`) | `404 ASSET_NOT_FOUND`, `400 REMOTE_STORAGE_CHECK_FAILED` | `MediaUploadWatcher` | `VERIFIED` |
| 37| `GET` | `/api/v1/media` | Yes | `media:upload` (Admin/Super Admin) | Query params (`status`, `page`, `per_page`) | `MediaAssetListResponse` (`items: list[MediaAssetResponse]`, `total`) | `403 PERMISSION_DENIED` | `MediaLibraryModal` | `VERIFIED` |
| 38| `GET` | `/api/v1/media/{id}` | Yes | Enrolled Student or Staff | Path param `id`, Query param `lesson_id` | `MediaAssetResponse` | `404 ASSET_NOT_FOUND`, `403 FORBIDDEN` | `MediaPreview` | `VERIFIED` |
| 39| `POST` | `/api/v1/media/{id}/playback-token` | Yes | Active Student Enrollment or Staff | Path param `id`, Body: `PlaybackTokenRequest` (`lesson_id`) | `PlaybackTokenResponse` (`playback_url`, `token`, `expires_at`, `drm_type: hls`) | `403 NOT_ENROLLED`, `404 LESSON_NOT_FOUND` | `VideoPlayer` (`/learn/:courseId/:lessonId`) | `VERIFIED` |
| 40| `GET` | `/api/v1/media/{id}/protected-pdf` | Yes | Active Student Enrollment or Staff | Path param `id`, Query param `lesson_id` | Binary PDF `StreamingResponse` (`Content-Type: application/pdf`) | `403 NOT_ENROLLED`, `404 RESOURCE_NOT_FOUND` | `ProtectedPdfViewer` (`/learn/:courseId/:lessonId`) | `VERIFIED` |
| 41| `GET` | `/api/v1/orders` | Yes | `orders:view_own` (Student) or `orders:view_all` (Admin) | Query params (`page`, `per_page`, `status`) | `OrderListResponse` (`items: list[OrderResponse]`, `total`) | `401 UNAUTHORIZED` | `StudentOrdersPage` (`/app/orders`), `AdminOrdersPage` (`/admin/orders`) | `VERIFIED` |
| 42| `POST` | `/api/v1/orders` | Yes | `orders:create` (Student) | `OrderCreateRequest` (`course_id`, `currency: INR`) | `OrderCreateResponse` (`order_id`, `razorpay_order_id`, `amount: 49900`, `currency: INR`, `key_id`) | `409 ALREADY_ENROLLED`, `404 COURSE_NOT_FOUND` | `CheckoutButton` (`/courses/:slug`, `/checkout/:courseId`) | `VERIFIED` |
| 43| `GET` | `/api/v1/orders/{id}` | Yes | Order Owner or Admin | Path param `id: UUID` | `OrderDetailResponse` (`id`, `status: PENDING|PAID|FAILED|REFUNDED`, `amount`, `payment_details`) | `404 ORDER_NOT_FOUND`, `403 FORBIDDEN` | `OrderSummaryCard` (`/order-success/:orderId`) | `VERIFIED` |
| 44| `POST` | `/api/v1/orders/{id}/refund` | Yes | `payments:refund` (Super Admin) | Path param `id`, Body: `OrderRefundRequest` (`amount`, `reason`) | `RefundResponse` (`refund_id`, `status: PROCESSED`, `amount_refunded`) | `400 ORDER_NOT_PAID`, `403 PERMISSION_DENIED` | `RefundDialog` (`/admin/orders`) | `VERIFIED` |
| 45| `POST` | `/api/v1/webhooks/razorpay` | No | Cryptographic HMAC Signature | Raw JSON body + Header: `X-Razorpay-Signature` | `dict` (`status: captured`) | `400 INVALID_SIGNATURE` | Server-to-server webhook (Razorpay backend) | `VERIFIED` |
| 46| `GET` | `/api/v1/enrollments` | Yes | `enrollment:view_own` (Student) | Query params (`page`, `per_page`, `status`) | `EnrollmentListResponse` (`items: list[EnrollmentResponse]`, `total`) | `401 UNAUTHORIZED` | `StudentCoursesGrid` (`/app/courses`, `/app`) | `VERIFIED` |
| 47| `GET` | `/api/v1/enrollments/all` | Yes | `enrollment:view_all` (Admin/Super Admin) | Query params (`page`, `per_page`, `course_id`) | `EnrollmentManageListResponse` (`items`, `total`) | `403 PERMISSION_DENIED` | `AdminEnrollmentRoster` (`/admin/students`) | `VERIFIED` |
| 48| `GET` | `/api/v1/enrollments/check/{course_id}`| Yes | Student | Path param `course_id: UUID` | `dict` (`enrolled: bool`, `enrollment_id: Optional[UUID]`) | None | `CourseEnrollmentGuard`, `EnrollButton` | `VERIFIED` |
| 49| `POST` | `/api/v1/enrollments/manual` | Yes | `enrollment:grant` (Admin/Super Admin) | `ManualEnrollmentRequest` (`user_id`, `course_id`, `reason`) | `EnrollmentResponse` (`id`, `status: ACTIVE`) | `409 ALREADY_ENROLLED`, `404 USER_NOT_FOUND` | `ManualEnrollModal` (`/admin/students`) | `VERIFIED` |
| 50| `GET` | `/api/v1/assignments/{id}` | Yes | Enrolled Student or Staff | Path param `id: UUID` | `AssignmentDetailResponse` (`id`, `title`, `instructions`, `due_date`, `max_attempts`, `rubric: RubricDetail`) | `404 ASSIGNMENT_NOT_FOUND`, `403 NOT_ENROLLED` | `AssignmentView` (`/app/assignments/:id`) | `VERIFIED` |
| 51| `PATCH`| `/api/v1/assignments/{id}` | Yes | `assignment:manage` (Admin/Super Admin) | Path param `id`, Body: `AssignmentUpdateRequest` (`instructions`, `due_date`, `max_points`) | `AssignmentResponse` | `404 ASSIGNMENT_NOT_FOUND`, `403 PERMISSION_DENIED` | `EditAssignmentModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 52| `POST` | `/api/v1/assignments/{id}/rubric` | Yes | `assignment:manage` (Admin/Super Admin) | Path param `id`, Body: `RubricCreateRequest` (`criteria: list[RubricCriteriaCreate]`) | `RubricResponse` (`id`, `version`, `criteria: list[RubricCriteria]`) | `422 TOTAL_POINTS_MISMATCH` | `RubricBuilderModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 53| `GET` | `/api/v1/assignments/{id}/submissions`| Yes | `assignment:view_all` (Staff/Admin) | Path param `id`, Query params (`status`, `page`, `per_page`) | `SubmissionListResponse` (`items: list[SubmissionListItem]`, `total`) | `403 PERMISSION_DENIED` | `StaffReviewQueue` (`/staff/reviews`) | `VERIFIED` |
| 54| `POST` | `/api/v1/assignments/{id}/submissions`| Yes | `assignment:submit` (Enrolled Student) | Path param `id`, Body: `SubmissionCreateRequest` (`submission_text`, `attachment_ids: list[UUID]`, `external_url`) | `SubmissionResponse` (`id`, `status: SUBMITTED`, `attempt_number`) | `403 NOT_ENROLLED`, `409 ATTEMPTS_EXCEEDED` | `AssignmentSubmitForm` (`/app/assignments/:id`) | `VERIFIED` |
| 55| `GET` | `/api/v1/submissions/{id}` | Yes | Submission Owner or Staff | Path param `id: UUID` | `SubmissionDetailResponse` (`id`, `submission_text`, `rubric_scores`, `grade_status`, `feedback`, `grade_override`) | `404 SUBMISSION_NOT_FOUND`, `403 FORBIDDEN` | `SubmissionResultCard` (`/app/assignments/:id`), `StaffReviewWorkspace` (`/staff/reviews/:id`) | `VERIFIED` |
| 56| `POST` | `/api/v1/submissions/{id}/grade` | Yes | `assignment:grade` (Staff/Admin) | Path param `id`, Body: `GradeSubmissionRequest` (`rubric_scores: list[CriteriaScore]`, `general_feedback`) | `SubmissionResponse` (`id`, `status: GRADED`, `total_score`, `passed: bool`) | `422 INVALID_RUBRIC_CRITERIA`, `403 PERMISSION_DENIED` | `RubricGradingForm` (`/staff/reviews/:id`) | `VERIFIED` |
| 57| `POST` | `/api/v1/submissions/{id}/override-grade`| Yes | `assignment:override` (Super Admin) | Path param `id`, Body: `GradeOverrideRequest` (`new_score`, `reason`) | `GradeOverrideResponse` (`id`, `original_score`, `overridden_score`, `justification`) | `400 REASON_REQUIRED`, `403 PERMISSION_DENIED` | `GradeOverrideDialog` (`/staff/reviews/:id`) | `VERIFIED` |
| 58| `GET` | `/api/v1/quizzes/{id}` | Yes | Enrolled Student or Staff | Path param `id: UUID` | `QuizResponse` (`id`, `title`, `duration_minutes`, `pass_percentage`, `questions: list[QuestionPublicResponse]`) | `404 QUIZ_NOT_FOUND`, `403 NOT_ENROLLED` | `QuizOverviewCard` (`/app/quizzes/:id`) | `VERIFIED` |
| 59| `PATCH`| `/api/v1/quizzes/{id}` | Yes | `quiz:manage` (Admin/Super Admin) | Path param `id`, Body: `QuizUpdateRequest` (`duration_minutes`, `pass_percentage`, `max_attempts`) | `QuizResponse` | `404 QUIZ_NOT_FOUND`, `403 PERMISSION_DENIED` | `QuizSettingsModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 60| `POST` | `/api/v1/quizzes/{id}/questions` | Yes | `quiz:manage` (Admin/Super Admin) | Path param `id`, Body: `QuestionCreateRequest` (`text`, `question_type`, `points`, `options: list[OptionCreate]`) | `QuestionResponse` (`id`, `text`, `question_type`, `points`, `options`) | `422 AT_LEAST_ONE_CORRECT_OPTION_REQUIRED` | `AddQuestionModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 61| `POST` | `/api/v1/quizzes/{id}/questions/bulk-csv`| Yes | `quiz:import_csv` (Admin/Super Admin) | Path param `id`, Body: `BulkCSVImportRequest` (`csv_content: str`) | `BulkCSVImportResponse` (`total_imported`, `errors: list[str]`) | `400 INVALID_CSV_FORMAT`, `403 PERMISSION_DENIED` | `BulkQuestionImportModal` (`/admin/courses/:id/edit`) | `VERIFIED` |
| 62| `POST` | `/api/v1/quizzes/{id}/attempts` | Yes | `quiz:attempt` (Enrolled Student) | Path param `id: UUID` | `QuizAttemptStartResponse` (`attempt_id`, `started_at`, `expires_at`, `questions: list[QuestionConcealedResponse]`) | `403 NOT_ENROLLED`, `409 ATTEMPTS_EXCEEDED` | `StartQuizButton` (`/app/quizzes/:id`) | `VERIFIED` |
| 63| `GET` | `/api/v1/quizzes/{id}/attempts` | Yes | `quiz:view_attempts` (Staff/Admin) | Path param `id: UUID`, Query params (`page`, `per_page`) | `QuizAttemptListResponse` (`items: list[AttemptListItem]`, `total`) | `403 PERMISSION_DENIED` | `StaffQuizAttemptsList` (`/staff`) | `VERIFIED` |
| 64| `GET` | `/api/v1/quiz-attempts` | Yes | Student | Query params (`page`, `per_page`) | `QuizAttemptListResponse` (`items: list[MyAttemptListItem]`, `total`) | `401 UNAUTHORIZED` | `StudentQuizHistory` (`/app/quizzes`) | `VERIFIED` |
| 65| `GET` | `/api/v1/quiz-attempts/{id}` | Yes | Attempt Owner or Staff | Path param `id: UUID` | `QuizAttemptResultResponse` (`id`, `score`, `total_points`, `passed: bool`, `answers: list[AnswerReviewResponse]`) | `404 ATTEMPT_NOT_FOUND`, `403 FORBIDDEN` | `QuizResultView` (`/app/quizzes/:id`) | `VERIFIED` |
| 66| `PATCH`| `/api/v1/quiz-attempts/{id}/autosave` | Yes | Attempt Owner (Student) | Path param `id`, Body: `AutosaveAnswerRequest` (`question_id`, `selected_option_ids: list[UUID]`, `text_answer`) | `AutosaveAnswerResponse` (`saved_at`, `status: IN_PROGRESS`) | `409 ATTEMPT_EXPIRED`, `403 NOT_ATTEMPT_OWNER` | `QuizQuestionForm` (Debounced Autosave) | `VERIFIED` |
| 67| `POST` | `/api/v1/quiz-attempts/{id}/submit` | Yes | Attempt Owner (Student) | Path param `id: UUID` | `QuizAttemptResultResponse` (`id`, `score`, `passed: bool`, `completed_at`) | `409 ATTEMPT_ALREADY_SUBMITTED`, `409 ATTEMPT_EXPIRED` | `SubmitQuizButton` (`/app/quizzes/:id`) | `VERIFIED` |
| 68| `POST` | `/api/v1/progress/lessons/{lesson_id}` | Yes | Enrolled Student | Path param `lesson_id`, Body: `LessonProgressHeartbeatRequest` (`watch_seconds`, `completed: Optional[bool]`) | `LessonProgressResponse` (`completed: bool`, `watch_seconds`, `last_watched_at`) | `403 NOT_ENROLLED`, `404 LESSON_NOT_FOUND` | `VideoPlayer` (Watch Heartbeat), `CompleteLessonToggle` | `VERIFIED` |
| 69| `GET` | `/api/v1/progress/courses/{course_id}` | Yes | Enrolled Student | Path param `course_id: UUID` | `CourseProgressSummaryResponse` (`completion_percentage`, `completed_lessons_count`, `total_lessons_count`, `is_completed: bool`) | `403 NOT_ENROLLED`, `404 COURSE_NOT_FOUND` | `CourseProgressBar`, `CoursePlayerSidebar` | `VERIFIED` |
| 70| `GET` | `/api/v1/certificates/{course_id}` | Yes | Enrolled Student (100% Finished) | Path param `course_id: UUID` | `CertificateResponse` (`id`, `verification_hash`, `pdf_url`, `issued_at`, `qr_code_url`) | `400 COURSE_NOT_100_PERCENT_COMPLETED` | `CertificateCard` (`/app/certificates`, `/app/courses/:id`) | `VERIFIED` |
| 71| `GET` | `/api/v1/certificates/{course_id}/download`| Yes | Enrolled Student | Path param `course_id: UUID` | Binary PDF `StreamingResponse` (`Content-Disposition: attachment; filename="certificate.pdf"`) | `404 CERTIFICATE_NOT_FOUND` | `DownloadCertificateButton` | `VERIFIED` |
| 72| `GET` | `/api/v1/certificates/verify/{verification_hash}`| No | None (Public QR Code) | Path param `verification_hash: str` | `CertificateVerifyResponse` (`is_valid: bool`, `student_name`, `course_title`, `issued_at`, `instructor_name`) | `404 CERTIFICATE_NOT_FOUND` | `PublicVerifyCertificatePage` (`/verify/certificate/:hash`) | `VERIFIED` |
| 73| `POST` | `/api/v1/certificates/{certificate_id}/revoke`| Yes | Super Admin | Path param `certificate_id`, Body: `CertificateRevokeRequest` (`reason: str`) | `MessageResponse` (`message`) | `404 CERTIFICATE_NOT_FOUND`, `403 PERMISSION_DENIED` | `RevokeCertificateDialog` | `VERIFIED` |
| 74| `GET` | `/api/v1/notifications` | Yes | Authenticated User | Query params (`unread_only: bool`, `page`, `per_page`) | `NotificationListResponse` (`items: list[NotificationResponse]`, `unread_count`, `total`) | `401 UNAUTHORIZED` | `NotificationBell`, `NotificationPopover` | `VERIFIED` |
| 75| `PATCH`| `/api/v1/notifications/{id}/read` | Yes | Notification Recipient | Path param `id: UUID` | `NotificationResponse` (`id`, `is_read: true`, `read_at`) | `404 NOTIFICATION_NOT_FOUND` | `NotificationItemClick` | `VERIFIED` |
| 76| `POST` | `/api/v1/notifications/read-all` | Yes | Authenticated User | None | `MessageResponse` (`message`) | `401 UNAUTHORIZED` | `MarkAllReadButton` | `VERIFIED` |
| 77| `GET` | `/api/v1/audit-logs` | Yes | `audit:view` (Super Admin) | Query params (`page`, `per_page`, `action`, `actor_id`, `start_date`, `end_date`) | `AuditLogListResponse` (`items: list[AuditLogResponse]`, `total`) | `403 PERMISSION_DENIED` | `AuditLogTable` (`/control/audit`) | `VERIFIED` |
| 78| `GET` | `/healthz` | No | None (Public) | None | `dict` (`status: "ok"`) | None | Docker/K8s Liveness Probe | `VERIFIED` |
| 79| `GET` | `/api/v1/health` | No | None (Public) | None | `dict` (`status: "ready"`, `dependencies: {database: "connected"}`) | `503 SERVICE_UNAVAILABLE` | Deployment Readiness Probe | `VERIFIED` |

---

## 3. Analysis of Incomplete, Undocumented or Missing Capabilities

1. **Lesson Resource Download URL Endpoint**:
   * Currently, `DELETE /api/v1/resources/{id}` exists for admin lesson resource removal, and protected PDFs are streamed via `GET /api/v1/media/{id}/protected-pdf`. For general file resources (e.g. ZIP files, code samples), the frontend should download via S3/R2 presigned GET or direct protected proxy.
2. **Support Ticketing API**:
   * The route inventory designates `/staff/tickets` and `/staff/tickets/:id`. The current backend models transactional outbox notifications and audit logs, but does not yet contain a dedicated `SupportTicket` table. Support inquiries are currently handled via instructor email or notifications.
   * **Recommendation**: Flag for project-owner review whether dedicated ticketing should be introduced in a future backend minor version or managed via in-app notifications.
3. **Frontend API Mocking Prohibition**:
   * In strict compliance with `GLOBAL_RULES.md`, frontend development must connect directly to the running backend on `http://localhost:8000`. Mocking backend endpoints or generating fabricated JSON stubs in production code is strictly forbidden.
