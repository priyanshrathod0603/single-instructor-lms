/**
 * TypeScript definitions for User Directory, Profiles, and Staff Onboarding.
 * Synchronized with backend: backend/app/schemas/user.py
 */

export interface UserProfileResponse {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  is_verified: boolean;
  is_active: boolean;
  roles: string[];
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface UserDirectoryItem {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  is_verified: boolean;
  is_active: boolean;
  roles: string[];
  created_at: string;
}

export interface UserCreateRequest {
  full_name: string;
  email: string;
  phone: string;
  password: string;
  role: "SUPER_ADMIN" | "ADMIN" | "STAFF" | "STUDENT";
}

export interface UserDirectoryResponse {
  items: UserDirectoryItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface UserProfileUpdateRequest {
  full_name?: string;
  avatar_url?: string;
}

export interface UserStatusUpdateRequest {
  is_active: boolean;
  reason?: string;
}

export interface StaffInviteRequest {
  email: string;
  full_name: string;
  role?: string;
}

export interface StaffInviteResponse {
  invitation_id: string;
  email: string;
  role: string;
  expires_at: string;
}

export interface UserRoleUpdateRequest {
  role_id: string;
  action: "ASSIGN" | "REVOKE";
}

export interface StudentEnrollmentSummary {
  id: string;
  course_id: string;
  course_title: string;
  course_slug?: string | null;
  status: string;
  granted_at: string;
  expires_at?: string | null;
  progress_percentage: number;
  completed_lessons_count: number;
  total_lessons_count: number;
  last_activity_at?: string | null;
}

export interface StudentQuizAttemptSummary {
  id: string;
  quiz_id: string;
  quiz_title: string;
  attempt_no: number;
  status: string;
  score?: number | null;
  is_passed?: boolean | null;
  started_at: string;
  completed_at?: string | null;
}

export interface StudentAssignmentSubmissionSummary {
  id: string;
  assignment_id: string;
  assignment_title: string;
  attempt_no: number;
  status: string;
  final_score?: number | null;
  max_score: number;
  pass_score: number;
  file_url: string;
  submitted_at: string;
  graded_at?: string | null;
  feedback?: string | null;
}

export interface StudentCertificateSummary {
  id: string;
  certificate_no: string;
  course_id: string;
  course_title: string;
  issued_at: string;
  verification_hash: string;
  pdf_url: string;
  is_revoked: boolean;
  revoked_at?: string | null;
  revoked_reason?: string | null;
}

export interface StudentLearningSummaryResponse {
  user: UserProfileResponse;
  enrollments: StudentEnrollmentSummary[];
  quiz_attempts: StudentQuizAttemptSummary[];
  assignment_submissions: StudentAssignmentSubmissionSummary[];
  certificates: StudentCertificateSummary[];
  audit_logs: Array<{
    id: string;
    action: string;
    actor_type: string;
    resource_type: string;
    resource_id?: string | null;
    before_state?: Record<string, any> | null;
    after_state?: Record<string, any> | null;
    ip_address?: string | null;
    created_at: string;
  }>;
}
