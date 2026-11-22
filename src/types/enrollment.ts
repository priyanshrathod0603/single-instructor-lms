/**
 * TypeScript definitions for Student Course Enrollments.
 * Synchronized with backend: backend/app/schemas/enrollment.py
 */

export interface EnrollmentResponse {
  id: string;
  student_id: string;
  course_id: string;
  order_id?: string | null;
  status: "ACTIVE" | "REVOKED" | "EXPIRED" | string;
  granted_at: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  revoked_reason?: string | null;
  course_title?: string | null;
  course_slug?: string | null;
}

export interface EnrollmentListResponse {
  items: EnrollmentResponse[];
  total: number;
  page: number;
  size: number;
}

export interface EnrollmentCheckResponse {
  course_id: string;
  is_enrolled: boolean;
  status?: string | null;
  access_granted: boolean;
}

export interface ManualEnrollmentGrantRequest {
  student_id: string;
  course_id: string;
  expires_at?: string | null;
  reason?: string | null;
}

export interface RevokeEnrollmentRequest {
  reason: string;
}
