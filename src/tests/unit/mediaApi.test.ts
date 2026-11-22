import { describe, it, expect, vi, beforeEach } from "vitest";
import { mediaApi } from "@/lib/api/media";
import { apiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

describe("mediaApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requests playback token for video asset", async () => {
    const mockToken = {
      media_id: "media-1",
      playback_token: "signed-jwt-token",
      stream_url: "https://cdn.example.com/hls/media-1/master.m3u8?token=signed-jwt-token",
      expires_at: "2026-01-01T02:00:00Z",
      ttl_seconds: 7200,
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockToken);

    const result = await mediaApi.getPlaybackToken("media-1", {
      lesson_id: "les-1",
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      "/media/media-1/playback-token",
      { lesson_id: "les-1" }
    );
    expect(result.playback_token).toBe("signed-jwt-token");
    expect(result.stream_url).toContain("master.m3u8");
  });

  it("constructs protected PDF stream URL with lesson parameter", () => {
    const url = mediaApi.getProtectedPdfStreamUrl("media-pdf-1", "lesson-99");
    expect(url).toBe("/api/v1/media/media-pdf-1/protected-pdf?lesson_id=lesson-99");
  });

  it("confirms upload with synchronized contract (duration_seconds, metadata, and optional file_key)", async () => {
    const mockAsset = {
      id: "media-1",
      uploader_id: "user-1",
      filename: "lecture.mp4",
      file_key: "raw-videos/media-1/lecture.mp4",
      bucket: "lms-media",
      mime_type: "video/mp4",
      file_size_bytes: 1048576,
      status: "PROCESSING",
      transcode_output: { duration_seconds: 120 },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockAsset);

    const result = await mediaApi.confirmUpload("media-1", {
      duration_seconds: 120,
      metadata: { codec: "h264" },
      file_key: "raw-videos/media-1/lecture.mp4",
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      "/media/media-1/confirm",
      {
        duration_seconds: 120,
        metadata: { codec: "h264" },
        file_key: "raw-videos/media-1/lecture.mp4",
      }
    );
    expect(result.status).toBe("PROCESSING");
  });

  it("confirms upload with default empty payload when no data is provided", async () => {
    const mockAsset = {
      id: "media-2",
      uploader_id: "user-1",
      filename: "doc.pdf",
      file_key: "protected-docs/media-2/doc.pdf",
      bucket: "lms-media",
      mime_type: "application/pdf",
      file_size_bytes: 512,
      status: "READY",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockAsset);

    const result = await mediaApi.confirmUpload("media-2");

    expect(apiClient.post).toHaveBeenCalledWith("/media/media-2/confirm", {});
    expect(result.status).toBe("READY");
  });
});
