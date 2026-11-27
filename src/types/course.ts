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

export type CourseDifficultyLevel =
  | "BEGINNER"
  | "INTERMEDIATE"
  | "ADVANCED"
  | "ALL_LEVELS";

export const DIFFICULTY_LEVEL_LABELS: Record<CourseDifficultyLevel, string> = {
  BEGINNER: "Beginner",
  INTERMEDIATE: "Intermediate",
  ADVANCED: "Advanced",
  ALL_LEVELS: "All Levels",
};

export function getDifficultyLabel(level: string | null | undefined): string {
  if (!level) return "All Levels";
  const key = level.toUpperCase() as CourseDifficultyLevel;
  return DIFFICULTY_LEVEL_LABELS[key] ?? level;
}

export const DEFAULT_COURSE_CATEGORIES = [
  "Web Development",
  "Backend Engineering",
  "System Design",
  "Data Science & AI",
  "Mobile Development",
  "Cloud & DevOps",
  "Cybersecurity",
  "Programming Languages",
  "Career & Interview Prep",
  "General",
] as const;

export const DEFAULT_COURSE_LANGUAGES = [
  "English",
  "Hindi",
  "Hinglish",
  "Spanish",
  "French",
  "German",
] as const;

export interface CourseSummary {
  id: string;
  slug: string;
  title: string;
  headline?: string | null;
  thumbnail_url?: string | null;
  thumbnail_media_id?: string | null;
  category?: string;
  difficulty_level?: CourseDifficultyLevel | string;
  language?: string;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  price_inr: number; // Effective selling price in paise (e.g. 499900 = ₹4,999.00)
  compare_at_price_inr?: number | null; // Optional regular price in paise when discounted
  currency?: string;
  discount_percentage?: number | null;
  is_free: boolean;
  tags: string[];
  live_revision_id?: string | null;
  draft_revision_id?: string | null;
  latest_revision_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CourseDetail extends CourseSummary {
  description?: string | null;
  learning_outcomes?: string[];
  requirements?: string[];
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
  status?: string;
  search?: string;
  tag?: string;
  category?: string;
  difficulty_level?: string;
  language?: string;
  page?: number;
  per_page?: number;
}

export interface CreateCoursePayload {
  title: string;
  slug?: string;
  headline?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  thumbnail_media_id?: string | null;
  category?: string;
  difficulty_level?: CourseDifficultyLevel | string;
  language?: string;
  learning_outcomes?: string[];
  requirements?: string[];
  price_inr?: number;
  compare_at_price_inr?: number | null;
  currency?: string;
  is_free?: boolean;
  tags?: string[];
}

export interface UpdateCoursePayload {
  title?: string;
  slug?: string;
  headline?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  thumbnail_media_id?: string | null;
  category?: string;
  difficulty_level?: CourseDifficultyLevel | string;
  language?: string;
  learning_outcomes?: string[];
  requirements?: string[];
  price_inr?: number;
  compare_at_price_inr?: number | null;
  currency?: string;
  is_free?: boolean;
  tags?: string[];
}

export interface CourseSlugCheckResponse {
  slug: string;
  available: boolean;
  reason?: string | null;
}

export interface CourseMetadataOptionItem {
  value: CourseDifficultyLevel | string;
  label: string;
}

export interface CourseMetadataOptionsResponse {
  categories: string[];
  difficulty_levels: CourseMetadataOptionItem[];
  languages: string[];
  currencies: string[];
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
  course_id?: string;
  revision_id: string;
  revision_no: number;
  blockers: PublishChecklistBlocker[];
  warnings: PublishChecklistWarning[];
}
