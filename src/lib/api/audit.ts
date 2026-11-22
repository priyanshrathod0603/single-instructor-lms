import { apiClient } from "./client";
import { AuditLogListParams, AuditLogListResponse, AuditLogResponse } from "@/types/audit";

export const auditApi = {
  /**
   * Filter and query the immutable platform security audit log trail.
   */
  async listAuditLogs(params?: AuditLogListParams): Promise<AuditLogListResponse> {
    return apiClient.get<AuditLogListResponse>("/audit-logs", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        action: params?.action || undefined,
        actor_id: params?.actor_id || undefined,
        resource_type: params?.resource_type || undefined,
        resource_id: params?.resource_id || undefined,
        ip_address: params?.ip_address || undefined,
      },
    });
  },

  /**
   * Retrieve a single audit log entry by UUID.
   */
  async getAuditLog(id: string): Promise<AuditLogResponse> {
    return apiClient.get<AuditLogResponse>(`/audit-logs/${id}`);
  },
};
