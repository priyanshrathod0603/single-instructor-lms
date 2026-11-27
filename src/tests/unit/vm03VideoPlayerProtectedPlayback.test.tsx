import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VideoPlayer } from "@/components/player/VideoPlayer";
import { mediaApi } from "@/lib/api/media";
import { progressApi } from "@/lib/api/progress";

// Mock API clients
vi.mock("@/lib/api/media", () => ({
  mediaApi: {
    getPlaybackToken: vi.fn(),
    getProtectedHlsStreamUrl: vi.fn(
      (mediaId: string, token: string) => `/api/v1/media/${mediaId}/hls/master.m3u8?token=${token}`
    ),
  },
}));

vi.mock("@/lib/api/progress", () => ({
  progressApi: {
    recordLessonProgress: vi.fn(),
  },
}));

vi.mock("@/lib/hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "student-123",
      email: "student@example.com",
      full_name: "Test Student",
    },
  }),
}));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        retryDelay: 0,
      },
    },
  });
}

function renderPlayer(props: {
  mediaId: string;
  lessonId: string;
  courseId: string;
  initialWatchSeconds?: number;
  onCompleted?: () => void;
}) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <VideoPlayer {...props} />
    </QueryClientProvider>
  );
}

describe("VM-03 Protected VideoPlayer Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    delete (window as any).Hls;
  });

  it("displays authorization loading skeleton while requesting playback token", () => {
    (mediaApi.getPlaybackToken as any).mockReturnValue(new Promise(() => {})); // Never resolves

    renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
    });

    expect(screen.getByText("Authorizing secure video stream...")).toBeInTheDocument();
  });

  it("displays error alert with retry button when token authorization fails", async () => {
    (mediaApi.getPlaybackToken as any).mockRejectedValue(
      new Error("Enrollment required to stream course video.")
    );

    renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
    });

    await waitFor(
      () => {
        expect(screen.getByText("Video Playback Unauthorized or Unavailable")).toBeInTheDocument();
        expect(
          screen.getByText("Enrollment required to stream course video.")
        ).toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // Verify retry button is rendered
    const retryBtn = screen.getByRole("button", { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();
  });

  it("renders video element and security watermark upon successful token retrieval", async () => {
    (mediaApi.getPlaybackToken as any).mockResolvedValue({
      media_id: "media-uuid-1",
      playback_token: "jwt-token-12345",
      stream_url: "https://stream.instructor.com/media/media-uuid-1/hls/master.m3u8",
      expires_at: "2026-11-24T05:00:00Z",
      ttl_seconds: 7200,
    });

    renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
    });

    await waitFor(() => {
      expect(screen.getByText("student@example.com")).toBeInTheDocument();
    });

    // Check mediaApi.getProtectedHlsStreamUrl was called to resolve mock CDN URL
    expect(mediaApi.getProtectedHlsStreamUrl).toHaveBeenCalledWith(
      "media-uuid-1",
      "jwt-token-12345"
    );
  });

  it("uses Safari native HLS when canPlayType returns probably/maybe", async () => {
    (mediaApi.getPlaybackToken as any).mockResolvedValue({
      media_id: "media-uuid-1",
      playback_token: "jwt-token-12345",
      stream_url: "/api/v1/media/media-uuid-1/hls/master.m3u8?token=jwt-token-12345",
      expires_at: "2026-11-24T05:00:00Z",
      ttl_seconds: 7200,
    });

    // Simulate Safari native HLS capability on HTMLMediaElement
    const canPlayTypeSpy = vi
      .spyOn(HTMLMediaElement.prototype, "canPlayType")
      .mockImplementation((type: string) => {
        if (type === "application/vnd.apple.mpegurl") return "probably";
        return "";
      });

    renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
    });

    await waitFor(() => {
      expect(screen.getByText("student@example.com")).toBeInTheDocument();
    });

    canPlayTypeSpy.mockRestore();
  });

  it("initializes HLS.js when native HLS is unsupported and window.Hls is available", async () => {
    (mediaApi.getPlaybackToken as any).mockResolvedValue({
      media_id: "media-uuid-1",
      playback_token: "jwt-token-12345",
      stream_url: "/api/v1/media/media-uuid-1/hls/master.m3u8?token=jwt-token-12345",
      expires_at: "2026-11-24T05:00:00Z",
      ttl_seconds: 7200,
    });

    // canPlayType returns empty
    const canPlayTypeSpy = vi
      .spyOn(HTMLMediaElement.prototype, "canPlayType")
      .mockReturnValue("");

    // Mock window.Hls
    const mockHlsInstance = {
      loadSource: vi.fn(),
      attachMedia: vi.fn(),
      on: vi.fn(),
      destroy: vi.fn(),
      startLoad: vi.fn(),
      recoverMediaError: vi.fn(),
    };
    const mockHlsConstructor = vi.fn().mockImplementation(() => mockHlsInstance);
    (mockHlsConstructor as any).isSupported = vi.fn().mockReturnValue(true);
    (mockHlsConstructor as any).Events = { ERROR: "hlsError" };
    (mockHlsConstructor as any).ErrorTypes = {
      NETWORK_ERROR: "networkError",
      MEDIA_ERROR: "mediaError",
      OTHER_ERROR: "otherError",
    };
    (window as any).Hls = mockHlsConstructor;

    const { unmount } = renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
    });

    await waitFor(() => {
      expect(mockHlsConstructor).toHaveBeenCalled();
      expect(mockHlsInstance.loadSource).toHaveBeenCalledWith(
        "/api/v1/media/media-uuid-1/hls/master.m3u8?token=jwt-token-12345"
      );
      expect(mockHlsInstance.attachMedia).toHaveBeenCalled();
    });

    // Verify cleanup on unmount
    unmount();
    expect(mockHlsInstance.destroy).toHaveBeenCalled();

    canPlayTypeSpy.mockRestore();
  });

  it("restores initialWatchSeconds to video element currentTime", async () => {
    (mediaApi.getPlaybackToken as any).mockResolvedValue({
      media_id: "media-uuid-1",
      playback_token: "jwt-token-12345",
      stream_url: "/api/v1/media/media-uuid-1/hls/master.m3u8?token=jwt-token-12345",
      expires_at: "2026-11-24T05:00:00Z",
      ttl_seconds: 7200,
    });

    const { container } = renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
      initialWatchSeconds: 45,
    });

    await waitFor(() => {
      const video = container.querySelector("video");
      expect(video).toBeInTheDocument();
      if (video) {
        expect(video.currentTime).toBe(45);
      }
    });
  });

  it("triggers completion heartbeat when playback passes 90% threshold", async () => {
    (mediaApi.getPlaybackToken as any).mockResolvedValue({
      media_id: "media-uuid-1",
      playback_token: "jwt-token-12345",
      stream_url: "/api/v1/media/media-uuid-1/hls/master.m3u8?token=jwt-token-12345",
      expires_at: "2026-11-24T05:00:00Z",
      ttl_seconds: 7200,
    });

    (progressApi.recordLessonProgress as any).mockResolvedValue({
      lesson_id: "lesson-uuid-1",
      is_completed: true,
      watch_position_seconds: 95,
    });

    const onCompletedMock = vi.fn();

    const { container } = renderPlayer({
      mediaId: "media-uuid-1",
      lessonId: "lesson-uuid-1",
      courseId: "course-uuid-1",
      onCompleted: onCompletedMock,
    });

    await waitFor(() => {
      const video = container.querySelector("video");
      expect(video).toBeInTheDocument();
    });

    const video = container.querySelector("video")!;
    Object.defineProperty(video, "duration", { value: 100, configurable: true });
    Object.defineProperty(video, "currentTime", { value: 92, configurable: true });

    // Fire timeupdate event
    fireEvent.timeUpdate(video);

    await waitFor(() => {
      expect(progressApi.recordLessonProgress).toHaveBeenCalledWith(
        "lesson-uuid-1",
        {
          watch_position_seconds: 92,
          is_completed: true,
        }
      );
      expect(onCompletedMock).toHaveBeenCalled();
    });
  });
});
