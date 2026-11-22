/**
 * TypeScript definitions for Media Assets, Signed Playback Tokens, and Streams.
 * Synchronized with backend: backend/app/schemas/media.py & backend/app/models/media.py
 */

export const SUPPORTED_VIDEO_MIME_TYPES = [
  "video/mp4",
  "video/webm",
  "video/quicktime",
] as const;

export type SupportedVideoMimeType = (typeof SUPPORTED_VIDEO_MIME_TYPES)[number];

export interface PlaybackTokenRequest {
  lesson_id?: string | null;
  course_id?: string | null;
}

export interface PlaybackTokenResponse {
  media_id: string;
  playback_token: string;
  stream_url: string;
  expires_at: string;
  ttl_seconds: number;
}

export interface MediaAssetResponse {
  id: string;
  uploader_id: string;
  filename: string;
  file_key: string;
  bucket: string;
  mime_type: string;
  file_size_bytes: number;
  status: "UPLOADING" | "UPLOADED" | "PROCESSING" | "READY" | "FAILED" | string;
  transcode_output?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface UploadIntentRequest {
  filename: string;
  mime_type: string;
  file_size_bytes: number;
}

export interface UploadIntentResponse {
  media_id: string;
  file_key: string;
  bucket: string;
  presigned_url: string;
  headers: Record<string, string>;
  expires_in_seconds: number;
}

export interface UploadConfirmRequest {
  duration_seconds?: number | null;
  metadata?: Record<string, unknown>;
  file_key?: string;
}

export interface MediaAssetListResponse {
  items: MediaAssetResponse[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface MediaListParams {
  page?: number;
  per_page?: number;
  mime_type?: string;
}
