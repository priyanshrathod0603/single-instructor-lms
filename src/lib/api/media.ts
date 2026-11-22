import { apiClient } from "./client";
import {
  MediaAssetListResponse,
  MediaAssetResponse,
  MediaListParams,
  PlaybackTokenRequest,
  PlaybackTokenResponse,
  UploadConfirmRequest,
  UploadIntentRequest,
  UploadIntentResponse,
} from "@/types/media";

export const mediaApi = {
  /**
   * Request authoritative short-lived signed playback token for HLS video.
   */
  async getPlaybackToken(
    mediaId: string,
    data?: PlaybackTokenRequest
  ): Promise<PlaybackTokenResponse> {
    return apiClient.post<PlaybackTokenResponse>(
      `/media/${encodeURIComponent(mediaId)}/playback-token`,
      data || {}
    );
  },

  /**
   * Get relative endpoint URL to stream watermarked protected PDF with authorization.
   */
  getProtectedPdfStreamUrl(mediaId: string, lessonId?: string): string {
    const base = `/api/v1/media/${encodeURIComponent(mediaId)}/protected-pdf`;
    return lessonId ? `${base}?lesson_id=${encodeURIComponent(lessonId)}` : base;
  },

  /**
   * Request presigned upload intent for video or PDF.
   */
  async getUploadIntent(data: UploadIntentRequest): Promise<UploadIntentResponse> {
    return apiClient.post<UploadIntentResponse>("/media/upload-intent", data);
  },

  /**
   * Confirm that binary upload completed successfully.
   */
  async confirmUpload(mediaId: string, data?: UploadConfirmRequest): Promise<MediaAssetResponse> {
    return apiClient.post<MediaAssetResponse>(
      `/media/${encodeURIComponent(mediaId)}/confirm`,
      data || {}
    );
  },

  /**
   * List media library assets with optional pagination and mime-type filters.
   */
  async listMediaAssets(params?: MediaListParams): Promise<MediaAssetListResponse> {
    return apiClient.get<MediaAssetListResponse>("/media", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        mime_type: params?.mime_type || undefined,
      },
    });
  },

  /**
   * Get metadata for a specific media asset.
   */
  async getMediaAsset(mediaId: string): Promise<MediaAssetResponse> {
    return apiClient.get<MediaAssetResponse>(`/media/${encodeURIComponent(mediaId)}`);
  },

  /**
   * Delete an unreferenced media asset safely.
   */
  async deleteMediaAsset(mediaId: string): Promise<void> {
    return apiClient.delete<void>(`/media/${encodeURIComponent(mediaId)}`);
  },
};
