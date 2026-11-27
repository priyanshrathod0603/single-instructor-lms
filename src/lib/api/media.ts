import { apiClient, getApiBaseUrl } from "./client";
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

function putFileWithProgress(
  uploadUrl: string,
  file: File,
  headers: Record<string, string>,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl, true);
    Object.entries(headers).forEach(([key, val]) => {
      xhr.setRequestHeader(key, val);
    });
    if (!headers["Content-Type"] && file.type) {
      xhr.setRequestHeader("Content-Type", file.type);
    }
    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress) {
        onProgress(Math.min(100, Math.round((evt.loaded / evt.total) * 100)));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve();
      } else {
        reject(new Error(`Storage upload failed with HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during image upload."));
    xhr.send(file);
  });
}

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
   * Get relative endpoint URL to stream protected HLS master playlist with authorization token.
   */
  getProtectedHlsStreamUrl(mediaId: string, token: string): string {
    return `/api/v1/media/${encodeURIComponent(mediaId)}/hls/master.m3u8?token=${encodeURIComponent(token)}`;
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

  /**
   * Full 3-step course thumbnail upload (intent -> PUT with progress -> confirm).
   */
  async uploadCourseThumbnail(
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<MediaAssetResponse> {
    const intent = await this.getUploadIntent({
      filename: file.name,
      mime_type: file.type,
      file_size_bytes: file.size,
    });
    const base = getApiBaseUrl().replace(/\/$/, "");
    const resolvedUploadUrl = intent.presigned_url.startsWith("/")
      ? `${base}${intent.presigned_url}`
      : intent.presigned_url;

    await putFileWithProgress(
      resolvedUploadUrl,
      file,
      intent.headers || { "Content-Type": file.type },
      onProgress,
    );

    return this.confirmUpload(intent.media_id, {
      file_key: intent.file_key,
    });
  },
};
