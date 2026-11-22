import { apiClient } from "./client";
import {
  CourseDetail,
  CourseListParams,
  CourseListResponse,
  CourseRevision,
  CourseSummary,
  CreateCoursePayload,
  CreateLessonPayload,
  CreateResourcePayload,
  CreateSectionPayload,
  CurriculumLesson,
  CurriculumSection,
  LessonResource,
  PublishChecklistResponse,
  ReorderItem,
  UpdateCoursePayload,
  UpdateLessonPayload,
  UpdateSectionPayload,
} from "@/types/course";

/**
 * Course Catalog & Admin Curriculum API Client.
 * Synchronized with backend routes in:
 * - backend/app/api/v1/courses.py
 * - backend/app/api/v1/sections.py
 * - backend/app/api/v1/lessons.py
 */
export const coursesApi = {
  // ---------------------------------------------------------------------------
  // Public Catalog
  // ---------------------------------------------------------------------------
  /**
   * Fetch paginated list of published courses.
   */
  async listCourses(params?: CourseListParams): Promise<CourseListResponse> {
    return apiClient.get<CourseListResponse>("/courses", {
      params: {
        search: params?.search || undefined,
        tag: params?.tag || undefined,
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
      },
    });
  },

  /**
   * Fetch full details and live published curriculum of a single course by slug or ID.
   */
  async getCourseDetail(idOrSlug: string): Promise<CourseDetail> {
    const encoded = encodeURIComponent(idOrSlug);
    return apiClient.get<CourseDetail>(`/courses/${encoded}`);
  },

  // ---------------------------------------------------------------------------
  // Admin Course Directory & Revisions
  // ---------------------------------------------------------------------------
  /**
   * Admin directory of all courses (draft, published, archived).
   */
  async listManageCourses(params?: CourseListParams): Promise<CourseListResponse> {
    return apiClient.get<CourseListResponse>("/courses/manage", {
      params: {
        search: params?.search || undefined,
        tag: params?.tag || undefined,
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
      },
    });
  },

  /**
   * Create new course entity and initial working draft revision.
   */
  async createCourse(data: CreateCoursePayload): Promise<CourseSummary> {
    return apiClient.post<CourseSummary>("/courses", data);
  },

  /**
   * Update top-level course metadata (title, price, thumbnail, tags).
   */
  async updateCourse(id: string, data: UpdateCoursePayload): Promise<CourseSummary> {
    return apiClient.patch<CourseSummary>(`/courses/${id}`, data);
  },

  /**
   * Archive a course (soft delete).
   */
  async archiveCourse(id: string): Promise<CourseSummary> {
    return apiClient.delete<CourseSummary>(`/courses/${id}`);
  },

  /**
   * Spawn a new working draft revision from a published course.
   */
  async createRevision(id: string): Promise<CourseRevision> {
    return apiClient.post<CourseRevision>(`/courses/${id}/revisions`, {});
  },

  /**
   * Fetch a specific revision tree with all sections, lessons, and resources.
   */
  async getRevision(id: string, revId: string): Promise<CourseRevision> {
    return apiClient.get<CourseRevision>(`/courses/${id}/revisions/${revId}`);
  },

  /**
   * Evaluate pre-flight publishing checklist.
   */
  async getPublishChecklist(id: string, revisionId?: string): Promise<PublishChecklistResponse> {
    return apiClient.get<PublishChecklistResponse>(`/courses/${id}/publish-checklist`, {
      params: revisionId ? { revision_id: revisionId } : undefined,
    });
  },

  /**
   * Atomically publish a draft revision as the live course revision.
   */
  async publishRevision(id: string, revId: string): Promise<CourseRevision> {
    return apiClient.post<CourseRevision>(`/courses/${id}/revisions/${revId}/publish`, {});
  },

  // ---------------------------------------------------------------------------
  // Curriculum Sections
  // ---------------------------------------------------------------------------
  /**
   * Add a new section to a draft revision.
   */
  async createSection(id: string, revId: string, data: CreateSectionPayload): Promise<CurriculumSection> {
    return apiClient.post<CurriculumSection>(`/courses/${id}/revisions/${revId}/sections`, data);
  },

  /**
   * Bulk reorder sections within a revision.
   */
  async reorderSections(id: string, revId: string, items: ReorderItem[]): Promise<CurriculumSection[]> {
    return apiClient.put<CurriculumSection[]>(`/courses/${id}/revisions/${revId}/sections/reorder`, { items });
  },

  /**
   * Update section title or description.
   */
  async updateSection(sectionId: string, data: UpdateSectionPayload): Promise<CurriculumSection> {
    return apiClient.patch<CurriculumSection>(`/sections/${sectionId}`, data);
  },

  /**
   * Delete a section and its child lessons.
   */
  async deleteSection(sectionId: string): Promise<void> {
    return apiClient.delete<void>(`/sections/${sectionId}`);
  },

  // ---------------------------------------------------------------------------
  // Curriculum Lessons
  // ---------------------------------------------------------------------------
  /**
   * Add a new lesson to a section.
   */
  async createLesson(sectionId: string, data: CreateLessonPayload): Promise<CurriculumLesson> {
    return apiClient.post<CurriculumLesson>(`/sections/${sectionId}/lessons`, data);
  },

  /**
   * Bulk reorder lessons within a section.
   */
  async reorderLessons(sectionId: string, items: ReorderItem[]): Promise<CurriculumLesson[]> {
    return apiClient.put<CurriculumLesson[]>(`/sections/${sectionId}/lessons/reorder`, { items });
  },

  /**
   * Retrieve a single lesson by ID.
   */
  async getLesson(lessonId: string): Promise<CurriculumLesson> {
    return apiClient.get<CurriculumLesson>(`/lessons/${lessonId}`);
  },

  /**
   * Update lesson content, preview flag, duration, or title.
   */
  async updateLesson(lessonId: string, data: UpdateLessonPayload): Promise<CurriculumLesson> {
    return apiClient.patch<CurriculumLesson>(`/lessons/${lessonId}`, data);
  },

  /**
   * Delete a lesson.
   */
  async deleteLesson(lessonId: string): Promise<void> {
    return apiClient.delete<void>(`/lessons/${lessonId}`);
  },

  // ---------------------------------------------------------------------------
  // Lesson Resources
  // ---------------------------------------------------------------------------
  /**
   * Attach a resource to a lesson.
   */
  async createResource(lessonId: string, data: CreateResourcePayload): Promise<LessonResource> {
    return apiClient.post<LessonResource>(`/lessons/${lessonId}/resources`, data);
  },

  /**
   * Delete a resource from a lesson.
   */
  async deleteResource(resourceId: string): Promise<void> {
    return apiClient.delete<void>(`/resources/${resourceId}`);
  },
};
