import { apiClient } from "./client";
import {
  CourseProgressSummaryResponse,
  LessonProgressHeartbeatRequest,
  LessonProgressResponse,
} from "@/types/progress";

export const progressApi = {
  /**
   * Post lesson heartbeat or toggle article completion.
   */
  async recordLessonProgress(
    lessonId: string,
    data: LessonProgressHeartbeatRequest
  ): Promise<LessonProgressResponse> {
    return apiClient.post<LessonProgressResponse>(
      `/progress/lessons/${encodeURIComponent(lessonId)}`,
      data
    );
  },

  /**
   * Fetch aggregated progress metrics for an enrolled course.
   */
  async getCourseProgress(
    courseId: string
  ): Promise<CourseProgressSummaryResponse> {
    return apiClient.get<CourseProgressSummaryResponse>(
      `/progress/courses/${encodeURIComponent(courseId)}`
    );
  },
};
