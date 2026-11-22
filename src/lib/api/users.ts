import { apiClient } from "./client";
import {
  StaffInviteRequest,
  StaffInviteResponse,
  StudentLearningSummaryResponse,
  UserCreateRequest,
  UserDirectoryResponse,
  UserProfileResponse,
  UserProfileUpdateRequest,
  UserRoleUpdateRequest,
  UserStatusUpdateRequest,
} from "@/types/user";

export interface UserListParams {
  page?: number;
  per_page?: number;
  role?: string;
  search?: string;
  is_active?: boolean;
  is_verified?: boolean;
  sort_by?: string;
  sort_order?: string;
}

export const usersApi = {
  /**
   * Search and list users in the directory with pagination, filters, and sorting.
   */
  async listUsers(params?: UserListParams): Promise<UserDirectoryResponse> {
    return apiClient.get<UserDirectoryResponse>("/users", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        role: params?.role || undefined,
        search: params?.search || undefined,
        is_active: params?.is_active !== undefined ? params.is_active : undefined,
        is_verified: params?.is_verified !== undefined ? params.is_verified : undefined,
        sort_by: params?.sort_by || undefined,
        sort_order: params?.sort_order || undefined,
      },
    });
  },

  /**
   * Retrieve single user profile by user ID.
   */
  async getUser(userId: string): Promise<UserProfileResponse> {
    return apiClient.get<UserProfileResponse>(`/users/${encodeURIComponent(userId)}`);
  },

  /**
   * Retrieve comprehensive learning performance and audit ledger for a student.
   */
  async getStudentLearningRecords(userId: string): Promise<StudentLearningSummaryResponse> {
    return apiClient.get<StudentLearningSummaryResponse>(
      `/users/${encodeURIComponent(userId)}/learning-records`
    );
  },

  /**
   * Update student or user profile fields (e.g. full_name, avatar_url).
   */
  async updateProfile(
    userId: string,
    data: UserProfileUpdateRequest
  ): Promise<UserProfileResponse> {
    return apiClient.patch<UserProfileResponse>(`/users/${encodeURIComponent(userId)}`, data);
  },

  /**
   * Activate or suspend a user account (Admin only).
   */
  async updateStatus(
    userId: string,
    data: UserStatusUpdateRequest
  ): Promise<UserProfileResponse> {
    return apiClient.patch<UserProfileResponse>(
      `/users/${encodeURIComponent(userId)}/status`,
      data
    );
  },

  /**
   * Invite a new staff member or instructor (Admin only).
   */
  async inviteStaff(data: StaffInviteRequest): Promise<StaffInviteResponse> {
    return apiClient.post<StaffInviteResponse>("/users/staff/invite", data);
  },

  /**
   * Assign or revoke a system role for a user (Super Admin only).
   */
  async manageRole(
    userId: string,
    data: UserRoleUpdateRequest
  ): Promise<UserProfileResponse> {
    return apiClient.patch<UserProfileResponse>(
      `/users/${encodeURIComponent(userId)}/roles`,
      data
    );
  },

  /**
   * Provision a new user account with personal details, credentials, and role (Super Admin only).
   */
  async createUser(data: UserCreateRequest): Promise<UserProfileResponse> {
    return apiClient.post<UserProfileResponse>("/control/users", data);
  },

  /**
   * Backward-compatible role update helper.
   */
  async updateRoles(userId: string, roles: string[]): Promise<UserProfileResponse> {
    // If a single role is passed, assign it
    const roleId = roles[0] || "STUDENT";
    return this.manageRole(userId, { role_id: roleId, action: "ASSIGN" });
  },
};
