/**
 * TypeScript definitions for Course Catalog, Curriculum, and Lesson entities.
 * Synchronized with backend Pydantic schemas: backend/app/schemas/course.py
 */

export type LessonType = "VIDEO" | "ARTICLE" | "QUIZ" | "ASSIGNMENT";

export type ResourceType = "PDF" | "SOURCE_CODE" | "LINK" | "ASSET";

export interface LessonResource {
  id: string;
  lesson_id: string;
  title: string;
  resource_type: ResourceType;
  file_url: string;
  file_size_bytes: number;
  created_at: string;
}

export interface CurriculumLesson {
  id: string;
  section_id: string;
  title: string;
  lesson_type: LessonType;
  sort_order: number;
  duration_seconds: number;
  is_preview: boolean;
  content?: Record<string, unknown> | null;
  resources: LessonResource[];
  created_at: string;
  updated_at: string;
}

export interface CurriculumSection {
  id: string;
  course_revision_id: string;
  title: string;
  description?: string | null;
  sort_order: number;
  lessons: CurriculumLesson[];
  created_at: string;
  updated_at: string;
}

export interface CourseSummary {
  id: string;
  slug: string;
  title: string;
  headline?: string | null;
  thumbnail_url?: string | null;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  price_inr: number; // In paise (e.g. 499900 = ₹4,999.00)
  is_free: boolean;
  tags: string[];
  live_revision_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CourseDetail extends CourseSummary {
  description?: string | null;
  curriculum: CurriculumSection[];
}

export interface CourseRevision {
  id: string;
  course_id: string;
  revision_no: number;
  status: string;
  title: string;
  headline?: string | null;
  description?: string | null;
  price_inr: number;
  is_free: boolean;
  tags: string[];
  sections: CurriculumSection[];
  created_at: string;
  updated_at: string;
}

export interface CourseListResponse {
  items: CourseSummary[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface CourseListParams {
  search?: string;
  tag?: string;
  page?: number;
  per_page?: number;
}

export interface CreateCoursePayload {
  title: string;
  headline?: string;
  description?: string;
  price_inr?: number;
  is_free?: boolean;
  tags?: string[];
  thumbnail_url?: string;
}

export interface UpdateCoursePayload {
  title?: string;
  headline?: string;
  description?: string;
  price_inr?: number;
  is_free?: boolean;
  tags?: string[];
  thumbnail_url?: string;
}

export interface CreateSectionPayload {
  title: string;
  description?: string;
  sort_order?: number;
}

export interface UpdateSectionPayload {
  title?: string;
  description?: string;
}

export interface ReorderItem {
  id: string;
  sort_order: number;
}

export interface CreateLessonPayload {
  title: string;
  lesson_type: LessonType;
  sort_order?: number;
  duration_seconds?: number;
  is_preview?: boolean;
  content?: Record<string, unknown>;
}

export interface UpdateLessonPayload {
  title?: string;
  duration_seconds?: number;
  is_preview?: boolean;
  content?: Record<string, unknown>;
}

export interface CreateResourcePayload {
  title: string;
  resource_type: ResourceType;
  file_url: string;
  file_size_bytes?: number;
}

export interface PublishChecklistBlocker {
  code: string;
  message: string;
  section_id?: string | null;
  lesson_id?: string | null;
}

export interface PublishChecklistWarning {
  code: string;
  message: string;
}

export interface PublishChecklistResponse {
  can_publish: boolean;
  revision_id: string;
  revision_no: number;
  blockers: PublishChecklistBlocker[];
  warnings: PublishChecklistWarning[];
}
