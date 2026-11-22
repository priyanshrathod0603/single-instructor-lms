/**
 * TypeScript definitions for Super Admin Control Dashboard & Analytics (SA-01).
 */

import { AuditLogResponse } from "./audit";

export type AuditLogEntry = AuditLogResponse;

export interface UserMetrics {
  total_students: number;
  total_admins: number;
  total_staff: number;
  total_super_admins: number;
  active_users: number;
}

export interface CourseMetrics {
  total_courses: number;
  published_courses: number;
  draft_courses: number;
  archived_courses: number;
}

export interface EnrollmentMetrics {
  total_enrollments: number;
  active_enrollments: number;
}

export interface FinancialMetrics {
  verified_revenue_paise: number;
  verified_revenue_inr: number;
  successful_transactions: number;
  refunded_amount_paise: number;
  refunded_amount_inr: number;
  net_revenue_paise: number;
  net_revenue_inr: number;
  currency: string;
}

export interface SecurityMetrics {
  total_audit_events: number;
  security_events_count: number;
  active_staff_count: number;
  security_model: string;
}

export interface DailyTrendPoint {
  date: string; // YYYY-MM-DD
  count: number;
}

export interface ControlOverviewData {
  user_metrics: UserMetrics;
  course_metrics: CourseMetrics;
  enrollment_metrics: EnrollmentMetrics;
  financial_metrics: FinancialMetrics;
  security_metrics: SecurityMetrics;
  registration_trends: DailyTrendPoint[];
  enrollment_trends: DailyTrendPoint[];
  recent_activity: AuditLogEntry[];
  generated_at: string;
}

// =============================================================================
// SA-03: Security Governance & Session Management Types
// =============================================================================

export interface SessionUserSummary {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  is_active: boolean;
}

export interface SessionItem {
  id: string;
  user_id: string;
  user?: SessionUserSummary | null;
  status: "ACTIVE" | "REVOKED" | "EXPIRED" | string;
  ip_address?: string | null;
  user_agent?: string | null;
  last_active_at: string;
  expires_at: string;
  created_at: string;
  revoked_at?: string | null;
  revoked_by?: string | null;
  revocation_reason?: string | null;
}

export interface SessionListResponse {
  items: SessionItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface SessionDetailResponse extends SessionItem {
  correlated_events: AuditLogEntry[];
}

export interface SessionRevokePayload {
  reason: string;
}

export interface UserSessionsRevokeResponse {
  user_id: string;
  revoked_sessions_count: number;
  message: string;
}

export interface EmergencyRevocationPayload {
  reason: string;
}

export interface EmergencyRevocationResponse {
  revoked_sessions_count: number;
  caller_session_id: string;
  caller_session_preserved: boolean;
  message: string;
}

export interface DetailedSecurityMetricsData {
  active_sessions_total: number;
  active_sessions_by_role: Record<string, number>;
  sessions_revoked_24h: number;
  sessions_displaced_24h: number;
  sessions_expired_24h: number;
  failed_logins_24h: number;
  rate_limit_breaches_24h: number;
  suspended_accounts_total: number;
  generated_at: string;
}

export interface SessionFilterParams {
  status?: string;
  user_id?: string;
  role?: string;
  ip_address?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: "created_at" | "last_active_at" | "expires_at";
  sort_order?: "asc" | "desc";
  page?: number;
  per_page?: number;
}
