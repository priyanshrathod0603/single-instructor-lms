import { apiClient } from "./client";
import {
  EnrollmentCheckResponse,
  EnrollmentListResponse,
  EnrollmentResponse,
  ManualEnrollmentGrantRequest,
} from "@/types/enrollment";

export interface EnrollmentListParams {
  page?: number;
  per_page?: number;
  status?: string;
  course_id?: string;
  student_id?: string;
}

export const enrollmentsApi = {
  /**
   * List courses the authenticated student is actively enrolled in.
   */
  async listOwnEnrollments(
    params?: EnrollmentListParams
  ): Promise<EnrollmentListResponse> {
    return apiClient.get<EnrollmentListResponse>("/enrollments", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        status: params?.status,
      },
    });
  },

  /**
   * Fast access-check verifying if authenticated student holds access to a course.
   */
  async checkEnrollment(courseId: string): Promise<EnrollmentCheckResponse> {
    return apiClient.get<EnrollmentCheckResponse>(
      `/enrollments/check/${encodeURIComponent(courseId)}`
    );
  },

  /**
   * Admin directory listing of all platform enrollments with filters.
   */
  async listAllEnrollments(
    params?: EnrollmentListParams
  ): Promise<EnrollmentListResponse> {
    return apiClient.get<EnrollmentListResponse>("/enrollments/all", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        status: params?.status,
        course_id: params?.course_id,
        student_id: params?.student_id,
      },
    });
  },

  /**
   * Administrative manual grant of course access.
   */
  async grantManualEnrollment(
    data: ManualEnrollmentGrantRequest
  ): Promise<EnrollmentResponse> {
    return apiClient.post<EnrollmentResponse>("/enrollments/grant-manual", data);
  },

  /**
   * Revoke active course enrollment access.
   */
  async revokeEnrollment(
    enrollmentId: string,
    reason: string
  ): Promise<EnrollmentResponse> {
    return apiClient.patch<EnrollmentResponse>(
      `/enrollments/${encodeURIComponent(enrollmentId)}/revoke`,
      { reason }
    );
  },
};
