import { apiClient } from "./client";
import {
  AssignmentResponse,
  CreateAssignmentPayload,
  CreateRubricPayload,
  GradeOverrideResponse,
  GradeSubmissionPayload,
  OverrideGradePayload,
  RubricResponse,
  SubmissionCreateRequest,
  SubmissionListResponse,
  SubmissionResponse,
  UpdateAssignmentPayload,
} from "@/types/assignment";

export const assignmentsApi = {
  /**
   * Retrieve assignment instructions and rubric attached to a curriculum lesson.
   */
  async getLessonAssignment(lessonId: string): Promise<AssignmentResponse> {
    return apiClient.get<AssignmentResponse>(
      `/lessons/${encodeURIComponent(lessonId)}/assignment`
    );
  },

  /**
   * Retrieve assignment details by assignment ID.
   */
  async getAssignment(assignmentId: string): Promise<AssignmentResponse> {
    return apiClient.get<AssignmentResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}`
    );
  },

  /**
   * Attach an assignment to a lesson.
   */
  async createAssignment(
    lessonId: string,
    data: CreateAssignmentPayload
  ): Promise<AssignmentResponse> {
    return apiClient.post<AssignmentResponse>(
      `/lessons/${encodeURIComponent(lessonId)}/assignment`,
      data
    );
  },

  /**
   * Update assignment details.
   */
  async updateAssignment(
    assignmentId: string,
    data: UpdateAssignmentPayload
  ): Promise<AssignmentResponse> {
    return apiClient.patch<AssignmentResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}`,
      data
    );
  },

  /**
   * Configure rubric criteria for an assignment.
   */
  async createRubric(
    assignmentId: string,
    data: CreateRubricPayload
  ): Promise<RubricResponse> {
    return apiClient.post<RubricResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}/rubric`,
      data
    );
  },

  /**
   * Submit student project work for an assignment.
   */
  async submitProject(
    assignmentId: string,
    data: SubmissionCreateRequest
  ): Promise<SubmissionResponse> {
    return apiClient.post<SubmissionResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}/submissions`,
      data
    );
  },

  /**
   * Retrieve specific submission details with rubric scores and feedback.
   */
  async getSubmission(submissionId: string): Promise<SubmissionResponse> {
    return apiClient.get<SubmissionResponse>(
      `/submissions/${encodeURIComponent(submissionId)}`
    );
  },

  /**
   * List submissions for an assignment.
   */
  async listAssignmentSubmissions(
    assignmentId: string,
    params?: { status?: string; student_id?: string; page?: number; size?: number }
  ): Promise<SubmissionListResponse> {
    return apiClient.get<SubmissionListResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}/submissions`,
      { params }
    );
  },

  /**
   * List the authenticated student's own submissions for an assignment.
   */
  async listOwnSubmissions(
    assignmentId: string,
    params?: { page?: number; size?: number }
  ): Promise<SubmissionListResponse> {
    return apiClient.get<SubmissionListResponse>(
      `/assignments/${encodeURIComponent(assignmentId)}/my-submissions`,
      { params }
    );
  },

  /**
   * Grade a student submission against rubric criteria.
   */
  async gradeSubmission(
    submissionId: string,
    data: GradeSubmissionPayload
  ): Promise<SubmissionResponse> {
    return apiClient.post<SubmissionResponse>(
      `/submissions/${encodeURIComponent(submissionId)}/grade`,
      data
    );
  },

  /**
   * Administrative override of a finalized submission grade.
   */
  async overrideGrade(
    submissionId: string,
    data: OverrideGradePayload
  ): Promise<GradeOverrideResponse> {
    return apiClient.post<GradeOverrideResponse>(
      `/submissions/${encodeURIComponent(submissionId)}/override-grade`,
      data
    );
  },
};
