/**
 * TypeScript definitions for Student Lesson and Course Progress.
 * Synchronized with backend: backend/app/schemas/progress.py
 */

export interface LessonProgressHeartbeatRequest {
  watch_position_seconds: number;
  is_completed?: boolean | null;
}

export interface CourseProgressSummaryResponse {
  course_id: string;
  completed_lessons_count: number;
  total_lessons_count: number;
  progress_percentage: number; // e.g. 85.50
  is_completed: boolean;
  completed_lesson_ids: string[];
  last_activity_at: string;
}

export interface LessonProgressResponse {
  lesson_id: string;
  is_completed: boolean;
  watch_position_seconds: number;
  completed_at?: string | null;
  course_progress?: CourseProgressSummaryResponse | null;
}
