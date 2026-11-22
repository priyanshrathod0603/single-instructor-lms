/**
 * TypeScript definitions for Assignments, Rubrics, Submissions, and Grading.
 * Synchronized with backend: backend/app/schemas/assignment.py
 */

export interface RubricCriteriaResponse {
  id: string;
  rubric_id: string;
  title: string;
  description?: string | null;
  max_points: number;
  weight: number;
  sort_order: number;
}

export interface RubricResponse {
  id: string;
  assignment_id: string;
  title: string;
  version: number;
  is_active: boolean;
  created_at: string;
  criteria: RubricCriteriaResponse[];
}

export interface AssignmentResponse {
  id: string;
  lesson_id: string;
  title: string;
  instructions: string;
  max_score: number;
  pass_score: number;
  allow_late: boolean;
  due_date?: string | null;
  created_at: string;
  updated_at: string;
  active_rubric?: RubricResponse | null;
}

export interface CreateAssignmentPayload {
  title: string;
  instructions: string;
  max_score?: number;
  pass_score?: number;
  allow_late?: boolean;
  due_date?: string | null;
}

export interface UpdateAssignmentPayload {
  title?: string;
  instructions?: string;
  max_score?: number;
  pass_score?: number;
  allow_late?: boolean;
  due_date?: string | null;
}

export interface RubricCriteriaPayload {
  title: string;
  description?: string;
  max_points: number;
  weight?: number;
  sort_order?: number;
}

export interface CreateRubricPayload {
  title: string;
  criteria: RubricCriteriaPayload[];
}

export interface SubmissionCreateRequest {
  file_url: string;
  text_notes?: string | null;
}

export interface RubricScoreResponse {
  id: string;
  submission_id: string;
  criteria_id: string;
  criteria_title?: string | null;
  max_points?: number | null;
  weight?: number | null;
  points_awarded: number;
  feedback?: string | null;
}

export interface GradeOverrideResponse {
  id: string;
  submission_id: string;
  original_score: number;
  overridden_score: number;
  reason: string;
  overridden_by: string;
  overrider_name?: string | null;
  created_at: string;
}

export interface SubmissionResponse {
  id: string;
  assignment_id: string;
  student_id: string;
  student_name?: string | null;
  student_email?: string | null;
  attempt_no: number;
  file_url: string;
  text_notes?: string | null;
  status: "SUBMITTED" | "GRADING" | "GRADED" | "REJECTED" | string;
  submitted_at: string;
  final_score?: number | null;
  graded_at?: string | null;
  graded_by?: string | null;
  grader_name?: string | null;
  feedback?: string | null;
  rubric_scores: RubricScoreResponse[];
  grade_overrides: GradeOverrideResponse[];
}

export interface SubmissionListResponse {
  items: SubmissionResponse[];
  total: number;
  page: number;
  size: number;
}

export interface RubricScoreInput {
  criteria_id: string;
  points_awarded: number;
  feedback?: string | null;
}

export interface GradeSubmissionPayload {
  scores: RubricScoreInput[];
  feedback?: string | null;
}

export interface OverrideGradePayload {
  overridden_score: number;
  reason: string;
}
