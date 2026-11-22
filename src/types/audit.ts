/**
 * TypeScript definitions for Platform Audit Logs.
 * Synchronized with backend: backend/app/schemas/audit.py
 */

export interface AuditLogResponse {
  id: string;
  actor_id?: string | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
  request_id?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogResponse[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface AuditLogListParams {
  page?: number;
  per_page?: number;
  action?: string;
  actor_id?: string;
  resource_type?: string;
  resource_id?: string;
  ip_address?: string;
}
