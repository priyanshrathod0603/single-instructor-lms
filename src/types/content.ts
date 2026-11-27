/**
 * TypeScript definitions for Content & Course Governance (SA-04).
 */

// =============================================================================
// Course Governance Types
// =============================================================================

export interface CourseGovernanceItem {
  id: string;
  slug: string;
  title: string;
  headline?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  price_inr: number;
  is_free: boolean;
  tags: string[];
  live_revision_id?: string | null;
  draft_revision_id?: string | null;
  latest_revision_id?: string | null;
  total_sections: number;
  total_lessons: number;
  total_duration_seconds: number;
  has_quiz: boolean;
  has_assignment: boolean;
  enrolled_students_count: number;
  created_at: string;
  updated_at: string;
}

export interface CourseGovernanceListResponse {
  items: CourseGovernanceItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface CourseStatusUpdatePayload {
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  reason?: string;
}

// =============================================================================
// Blog CMS Types
// =============================================================================

export interface BlogAuthorSummary {
  id: string;
  email: string;
  full_name: string;
}

export interface BlogPostItem {
  id: string;
  title: string;
  slug: string;
  excerpt?: string | null;
  content: string;
  category: string;
  thumbnail_url?: string | null;
  thumbnail_media_id?: string | null;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  published_at?: string | null;
  author_id: string;
  author?: BlogAuthorSummary | null;
  created_at: string;
  updated_at: string;
}

export interface BlogPostListResponse {
  items: BlogPostItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface BlogPostCreatePayload {
  title: string;
  slug?: string;
  excerpt?: string;
  content: string;
  category?: string;
  thumbnail_url?: string;
  thumbnail_media_id?: string;
  status?: string;
}

export interface BlogPostUpdatePayload {
  title?: string;
  slug?: string;
  excerpt?: string;
  content?: string;
  category?: string;
  thumbnail_url?: string;
  thumbnail_media_id?: string;
  status?: string;
}

// =============================================================================
// Notes CMS Types
// =============================================================================

export interface NoteAuthorSummary {
  id: string;
  email: string;
  full_name: string;
}

export interface NoteItem {
  id: string;
  title: string;
  slug: string;
  description?: string | null;
  category: string;
  pdf_media_id?: string | null;
  pdf_url?: string | null;
  file_size_bytes?: number | null;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | string;
  published_at?: string | null;
  author_id: string;
  author?: NoteAuthorSummary | null;
  created_at: string;
  updated_at: string;
}

export interface NoteListResponse {
  items: NoteItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface NoteCreatePayload {
  title: string;
  slug?: string;
  description?: string;
  category?: string;
  pdf_media_id?: string;
  pdf_url?: string;
  file_size_bytes?: number;
  status?: string;
}

export interface NoteUpdatePayload {
  title?: string;
  slug?: string;
  description?: string;
  category?: string;
  pdf_media_id?: string;
  pdf_url?: string;
  file_size_bytes?: number;
  status?: string;
}

export interface NoteReplacePdfPayload {
  pdf_media_id?: string;
  pdf_url: string;
  file_size_bytes?: number;
}
