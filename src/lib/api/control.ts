import { apiClient } from "./client";
import {
  ControlOverviewData,
  DetailedSecurityMetricsData,
  EmergencyRevocationPayload,
  EmergencyRevocationResponse,
  SessionDetailResponse,
  SessionFilterParams,
  SessionListResponse,
  SessionRevokePayload,
  UserSessionsRevokeResponse,
} from "@/types/control";
import {
  BlogPostCreatePayload,
  BlogPostItem,
  BlogPostListResponse,
  BlogPostUpdatePayload,
  CourseGovernanceItem,
  CourseGovernanceListResponse,
  CourseStatusUpdatePayload,
  NoteCreatePayload,
  NoteItem,
  NoteListResponse,
  NoteReplacePdfPayload,
  NoteUpdatePayload,
} from "@/types/content";
import {
  OfferCreatePayload,
  OfferFilterParams,
  OfferItem,
  OfferListResponse,
  OfferStatusPayload,
  OfferUpdatePayload,
  PaymentMetrics,
  PlatformSettingsUpdatePayload,
  PublicPlatformInfo,
  TransactionFilterParams,
  TransactionItem,
  TransactionListResponse,
} from "@/types/commerce";

/**
 * Super Admin Control & Platform Analytics API Client.
 * Synchronized with backend routes in backend/app/api/v1/control.py.
 */
export const controlApi = {
  /**
   * Fetch verified real-time platform metrics, trends, and recent activity.
   * Requires authenticated SUPER_ADMIN role.
   */
  async getOverview(): Promise<ControlOverviewData> {
    return apiClient.get<ControlOverviewData>("/control/overview");
  },

  /**
   * List platform authentication sessions with multi-attribute filtering.
   * Requires authenticated SUPER_ADMIN role.
   */
  async listSessions(params?: SessionFilterParams): Promise<SessionListResponse> {
    return apiClient.get<SessionListResponse>("/control/sessions", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get detailed session surveillance metadata, client data, and correlated audit events.
   * Requires authenticated SUPER_ADMIN role.
   */
  async getSession(id: string): Promise<SessionDetailResponse> {
    return apiClient.get<SessionDetailResponse>(`/control/sessions/${id}`);
  },

  /**
   * Target revocation of a specific active session.
   * Requires authenticated SUPER_ADMIN role.
   */
  async revokeSession(
    id: string,
    payload: SessionRevokePayload
  ): Promise<SessionDetailResponse> {
    return apiClient.post<SessionDetailResponse>(
      `/control/sessions/${id}/revoke`,
      payload
    );
  },

  /**
   * User-wide revocation of all active sessions for a target user.
   * Requires authenticated SUPER_ADMIN role.
   */
  async revokeUserSessions(
    userId: string,
    payload: SessionRevokePayload
  ): Promise<UserSessionsRevokeResponse> {
    return apiClient.post<UserSessionsRevokeResponse>(
      `/control/users/${userId}/revoke-sessions`,
      payload
    );
  },

  /**
   * Emergency platform-wide revocation of all active sessions EXCEPT the caller's session.
   * Caller session is derived exclusively from server-side verified auth context.
   * Requires authenticated SUPER_ADMIN role.
   */
  async revokeOtherSessions(
    payload: EmergencyRevocationPayload
  ): Promise<EmergencyRevocationResponse> {
    return apiClient.post<EmergencyRevocationResponse>(
      "/control/sessions/revoke-others",
      payload
    );
  },

  /**
   * Detailed security & surveillance metrics (active sessions by role, 24h revocations/displacements).
   * Requires authenticated SUPER_ADMIN role.
   */
  async getSecurityMetrics(): Promise<DetailedSecurityMetricsData> {
    return apiClient.get<DetailedSecurityMetricsData>("/control/security/metrics");
  },

  // ===========================================================================
  // SA-04.1: Course Governance API
  // ===========================================================================

  /**
   * List all courses with curriculum aggregation stats, enrollment counts, and filters.
   */
  async listGovernedCourses(params?: {
    search?: string;
    status?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
    per_page?: number;
  }): Promise<CourseGovernanceListResponse> {
    return apiClient.get<CourseGovernanceListResponse>("/control/courses", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get single course governance inspection detail.
   */
  async getGovernedCourse(id: string): Promise<CourseGovernanceItem> {
    return apiClient.get<CourseGovernanceItem>(`/control/courses/${id}`);
  },

  /**
   * Change course lifecycle status (DRAFT, PUBLISHED, ARCHIVED).
   */
  async updateCourseStatus(
    id: string,
    payload: CourseStatusUpdatePayload
  ): Promise<CourseGovernanceItem> {
    return apiClient.patch<CourseGovernanceItem>(
      `/control/courses/${id}/status`,
      payload
    );
  },

  // ===========================================================================
  // SA-04.2: Blog CMS API
  // ===========================================================================

  /**
   * List blog posts with search, status, and category filtering.
   */
  async listBlogPosts(params?: {
    search?: string;
    status?: string;
    category?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
    per_page?: number;
  }): Promise<BlogPostListResponse> {
    return apiClient.get<BlogPostListResponse>("/control/blog", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get single blog post by UUID.
   */
  async getBlogPost(id: string): Promise<BlogPostItem> {
    return apiClient.get<BlogPostItem>(`/control/blog/${id}`);
  },

  /**
   * Create a new blog post.
   */
  async createBlogPost(payload: BlogPostCreatePayload): Promise<BlogPostItem> {
    return apiClient.post<BlogPostItem>("/control/blog", payload);
  },

  /**
   * Update an existing blog post.
   */
  async updateBlogPost(
    id: string,
    payload: BlogPostUpdatePayload
  ): Promise<BlogPostItem> {
    return apiClient.put<BlogPostItem>(`/control/blog/${id}`, payload);
  },

  /**
   * Publish, unpublish, or archive a blog post.
   */
  async changeBlogStatus(id: string, status: string): Promise<BlogPostItem> {
    return apiClient.patch<BlogPostItem>(`/control/blog/${id}/status`, {
      status,
    });
  },

  /**
   * Delete a blog post.
   */
  async deleteBlogPost(id: string): Promise<void> {
    return apiClient.delete<void>(`/control/blog/${id}`);
  },

  /**
   * Get all unique blog categories.
   */
  async getBlogCategories(): Promise<string[]> {
    return apiClient.get<string[]>("/control/blog/categories");
  },

  // ===========================================================================
  // SA-04.3: Notes CMS API
  // ===========================================================================

  /**
   * List study notes with search, status, and category filtering.
   */
  async listNotes(params?: {
    search?: string;
    status?: string;
    category?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
    per_page?: number;
  }): Promise<NoteListResponse> {
    return apiClient.get<NoteListResponse>("/control/notes", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get single study note by UUID.
   */
  async getNote(id: string): Promise<NoteItem> {
    return apiClient.get<NoteItem>(`/control/notes/${id}`);
  },

  /**
   * Create a new study note.
   */
  async createNote(payload: NoteCreatePayload): Promise<NoteItem> {
    return apiClient.post<NoteItem>("/control/notes", payload);
  },

  /**
   * Update an existing study note.
   */
  async updateNote(
    id: string,
    payload: NoteUpdatePayload
  ): Promise<NoteItem> {
    return apiClient.put<NoteItem>(`/control/notes/${id}`, payload);
  },

  /**
   * Replace the PDF document for a note.
   */
  async replaceNotePdf(
    id: string,
    payload: NoteReplacePdfPayload
  ): Promise<NoteItem> {
    return apiClient.post<NoteItem>(`/control/notes/${id}/pdf`, payload);
  },

  /**
   * Publish, unpublish, or archive a study note.
   */
  async changeNoteStatus(id: string, status: string): Promise<NoteItem> {
    return apiClient.patch<NoteItem>(`/control/notes/${id}/status`, {
      status,
    });
  },

  /**
   * Delete a study note.
   */
  async deleteNote(id: string): Promise<void> {
    return apiClient.delete<void>(`/control/notes/${id}`);
  },

  /**
   * Get all unique note categories.
   */
  async getNoteCategories(): Promise<string[]> {
    return apiClient.get<string[]>("/control/notes/categories");
  },

  // ==========================================================================
  // SA-05.1: Offers Management API
  // ==========================================================================

  /**
   * List promotional offers with multi-criteria filtering and pagination.
   */
  async listOffers(params?: OfferFilterParams): Promise<OfferListResponse> {
    return apiClient.get<OfferListResponse>("/control/offers", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get full details of a specific promotional offer.
   */
  async getOffer(id: string): Promise<OfferItem> {
    return apiClient.get<OfferItem>(`/control/offers/${id}`);
  },

  /**
   * Create a new promotional discount offer.
   */
  async createOffer(payload: OfferCreatePayload): Promise<OfferItem> {
    return apiClient.post<OfferItem>("/control/offers", payload);
  },

  /**
   * Update an existing promotional offer.
   */
  async updateOffer(id: string, payload: OfferUpdatePayload): Promise<OfferItem> {
    return apiClient.put<OfferItem>(`/control/offers/${id}`, payload);
  },

  /**
   * Toggle or update offer lifecycle status (ACTIVE, INACTIVE, ARCHIVED).
   */
  async changeOfferStatus(id: string, status: string): Promise<OfferItem> {
    return apiClient.patch<OfferItem>(`/control/offers/${id}/status`, {
      status,
    });
  },

  /**
   * Delete an offer permanently.
   */
  async deleteOffer(id: string): Promise<void> {
    return apiClient.delete<void>(`/control/offers/${id}`);
  },

  // ==========================================================================
  // SA-05.2: Payment Overview API
  // ==========================================================================

  /**
   * Fetch aggregate commercial payment metrics derived from real database records.
   */
  async getPaymentOverview(): Promise<PaymentMetrics> {
    return apiClient.get<PaymentMetrics>("/control/payments/overview");
  },

  /**
   * List payment transactions with pagination, filters, and relationship summaries.
   */
  async listTransactions(params?: TransactionFilterParams): Promise<TransactionListResponse> {
    return apiClient.get<TransactionListResponse>("/control/payments/transactions", {
      params: params as Record<string, string | number | boolean | undefined>,
    });
  },

  /**
   * Get transaction details and associated order/refund details.
   */
  async getTransaction(id: string): Promise<TransactionItem> {
    return apiClient.get<TransactionItem>(`/control/payments/transactions/${id}`);
  },

  // ==========================================================================
  // SA-05.3: Platform Information & Settings API
  // ==========================================================================

  /**
   * Fetch non-sensitive platform branding and safe system configuration.
   */
  async getPlatformSettings(): Promise<PublicPlatformInfo> {
    return apiClient.get<PublicPlatformInfo>("/control/settings");
  },

  /**
   * Update non-sensitive platform and brand settings.
   */
  async updatePlatformSettings(payload: PlatformSettingsUpdatePayload): Promise<PublicPlatformInfo> {
    return apiClient.put<PublicPlatformInfo>("/control/settings", payload);
  },
};
