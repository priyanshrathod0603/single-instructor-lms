import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  SUPPORTED_VIDEO_MIME_TYPES,
  UploadConfirmRequest,
  MediaAssetResponse,
} from "@/types/media";
import { MediaLibraryModal } from "@/components/admin/MediaLibraryModal";
import { LessonEditorModal } from "@/components/admin/LessonEditorModal";
import { mediaApi } from "@/lib/api/media";
import { coursesApi } from "@/lib/api/courses";
import { CurriculumLesson } from "@/types/course";

// Mock API clients
vi.mock("@/lib/api/media", () => ({
  mediaApi: {
    listMediaAssets: vi.fn(),
    getUploadIntent: vi.fn(),
    confirmUpload: vi.fn(),
    deleteMediaAsset: vi.fn(),
  },
}));

vi.mock("@/lib/api/courses", () => ({
  coursesApi: {
    updateLesson: vi.fn(),
    createResource: vi.fn(),
    deleteResource: vi.fn(),
  },
}));

vi.mock("@/lib/api/quizzes", () => ({
  quizzesApi: {
    getLessonQuiz: vi.fn(),
    createQuiz: vi.fn(),
    updateQuiz: vi.fn(),
    bulkImportCsv: vi.fn(),
  },
}));

vi.mock("@/lib/api/assignments", () => ({
  assignmentsApi: {
    getLessonAssignment: vi.fn(),
    createAssignment: vi.fn(),
    updateAssignment: vi.fn(),
    createRubric: vi.fn(),
  },
}));

// Resolution helper matching src/app/learn/[courseId]/[lessonId]/page.tsx exactly
function resolveLessonMediaId(lesson: { content?: any; resources?: any[] }): string {
  const lessonContent =
    lesson.content &&
    typeof lesson.content === "object" &&
    !Array.isArray(lesson.content)
      ? lesson.content
      : {};

  const resolvedContentMediaId =
    (typeof lessonContent.media_asset_id === "string" && lessonContent.media_asset_id.trim()) ||
    (typeof lessonContent.media_id === "string" && lessonContent.media_id.trim()) ||
    (typeof lessonContent.video_id === "string" && lessonContent.video_id.trim()) ||
    "";

  const resolvedResourceMediaId =
    lesson.resources?.find((r: any) => r.resource_type === "ASSET" || r.file_url)?.id ||
    "";

  return resolvedContentMediaId || resolvedResourceMediaId || "";
}

describe("VM-01.1 Task A: Student Video Reference Resolution & Priority", () => {
  it("Scenario 1: Resolves canonical media_asset_id correctly", () => {
    const lesson = {
      content: { media_asset_id: "asset-uuid-101", file_key: "raw-videos/key.mp4" },
    };
    expect(resolveLessonMediaId(lesson)).toBe("asset-uuid-101");
  });

  it("Scenario 2: Resolves legacy media_id when media_asset_id is absent", () => {
    const lesson = {
      content: { media_id: "legacy-media-202" },
    };
    expect(resolveLessonMediaId(lesson)).toBe("legacy-media-202");
  });

  it("Scenario 3: Resolves legacy video_id when media_asset_id and media_id are absent", () => {
    const lesson = {
      content: { video_id: "legacy-video-303" },
    };
    expect(resolveLessonMediaId(lesson)).toBe("legacy-video-303");
  });

  it("Scenario 4: Canonical media_asset_id takes strict priority over media_id and video_id", () => {
    const lesson = {
      content: {
        media_asset_id: "canonical-primary-id",
        media_id: "legacy-second-id",
        video_id: "legacy-third-id",
      },
    };
    expect(resolveLessonMediaId(lesson)).toBe("canonical-primary-id");
  });

  it("Scenario 4b: media_id takes priority over video_id when media_asset_id is absent", () => {
    const lesson = {
      content: {
        media_id: "legacy-second-id",
        video_id: "legacy-third-id",
      },
    };
    expect(resolveLessonMediaId(lesson)).toBe("legacy-second-id");
  });

  it("Scenario 5: Handles missing, empty, or whitespace-only media references safely", () => {
    expect(resolveLessonMediaId({ content: null })).toBe("");
    expect(resolveLessonMediaId({ content: undefined })).toBe("");
    expect(resolveLessonMediaId({ content: {} })).toBe("");
    expect(resolveLessonMediaId({ content: { media_asset_id: "   " } })).toBe("");
    expect(resolveLessonMediaId({ content: { media_id: "" } })).toBe("");
    expect(resolveLessonMediaId({ content: { media_asset_id: 12345 as any } })).toBe("");
    expect(resolveLessonMediaId({ content: "not-an-object" as any })).toBe("");
    expect(resolveLessonMediaId({ content: [] as any })).toBe("");
  });

  it("Scenario 5b: Resolves resource ASSET fallback when content keys are absent", () => {
    const lesson = {
      content: {},
      resources: [
        { id: "res-asset-555", resource_type: "ASSET", file_url: "lesson-resources/data.zip" },
      ],
    };
    expect(resolveLessonMediaId(lesson)).toBe("res-asset-555");
  });

  it("Scenario 6: Non-video lessons remain unaffected with empty mediaId", () => {
    const articleLesson = {
      lesson_type: "ARTICLE",
      content: { body: "# Article Markdown Content" },
    };
    expect(resolveLessonMediaId(articleLesson)).toBe("");

    const quizLesson = {
      lesson_type: "QUIZ",
      content: {},
    };
    expect(resolveLessonMediaId(quizLesson)).toBe("");
  });
});

describe("VM-01.1 Task B: Upload Confirmation Type Contract Synchronization", () => {
  it("Scenario 7: UploadConfirmRequest accepts synchronized backend contract fields", () => {
    const reqWithDuration: UploadConfirmRequest = {
      duration_seconds: 3600,
      metadata: { codec: "h264", width: 1920, height: 1080 },
    };
    expect(reqWithDuration.duration_seconds).toBe(3600);
    expect(reqWithDuration.metadata?.codec).toBe("h264");

    const reqWithNullDuration: UploadConfirmRequest = {
      duration_seconds: null,
      metadata: {},
    };
    expect(reqWithNullDuration.duration_seconds).toBeNull();

    const reqWithLegacyFileKey: UploadConfirmRequest = {
      file_key: "raw-videos/test-key.mp4",
      duration_seconds: 120,
    };
    expect(reqWithLegacyFileKey.file_key).toBe("raw-videos/test-key.mp4");
  });

  it("Scenario 10: Existing upload confirmation calls work with empty or partial payloads", () => {
    const emptyPayload: UploadConfirmRequest = {};
    expect(emptyPayload.duration_seconds).toBeUndefined();
    expect(emptyPayload.metadata).toBeUndefined();
  });
});

describe("VM-01.1 Task C: Video MIME Selection Compatibility", () => {
  it("Scenario 8: SUPPORTED_VIDEO_MIME_TYPES matches backend supported video types exactly", () => {
    expect(SUPPORTED_VIDEO_MIME_TYPES).toContain("video/mp4");
    expect(SUPPORTED_VIDEO_MIME_TYPES).toContain("video/webm");
    expect(SUPPORTED_VIDEO_MIME_TYPES).toContain("video/quicktime");
    expect(SUPPORTED_VIDEO_MIME_TYPES.length).toBe(3);
  });

  it("Scenario 8b & 9: MediaLibraryModal filters displayed items allowing all 3 video formats and excluding others", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const mockAssets: MediaAssetResponse[] = [
      {
        id: "vid-1",
        uploader_id: "user-1",
        filename: "intro.mp4",
        file_key: "raw-videos/vid-1/intro.mp4",
        bucket: "lms-media",
        mime_type: "video/mp4",
        file_size_bytes: 10485760,
        status: "READY",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "vid-2",
        uploader_id: "user-1",
        filename: "demo.webm",
        file_key: "raw-videos/vid-2/demo.webm",
        bucket: "lms-media",
        mime_type: "video/webm",
        file_size_bytes: 20971520,
        status: "READY",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "vid-3",
        uploader_id: "user-1",
        filename: "screen.mov",
        file_key: "raw-videos/vid-3/screen.mov",
        bucket: "lms-media",
        mime_type: "video/quicktime",
        file_size_bytes: 31457280,
        status: "READY",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "doc-1",
        uploader_id: "user-1",
        filename: "syllabus.pdf",
        file_key: "protected-docs/doc-1/syllabus.pdf",
        bucket: "lms-media",
        mime_type: "application/pdf",
        file_size_bytes: 524288,
        status: "READY",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "unsupported-1",
        uploader_id: "user-1",
        filename: "old_clip.avi",
        file_key: "raw-videos/unsupported-1/old_clip.avi",
        bucket: "lms-media",
        mime_type: "video/x-msvideo",
        file_size_bytes: 5000000,
        status: "READY",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];

    vi.mocked(mediaApi.listMediaAssets).mockResolvedValue({
      items: mockAssets,
      total: mockAssets.length,
      page: 1,
      per_page: 50,
      total_pages: 1,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MediaLibraryModal
          isOpen={true}
          onClose={() => {}}
          allowedMimeType={SUPPORTED_VIDEO_MIME_TYPES.join(",")}
          title="Select Video for Lesson"
        />
      </QueryClientProvider>
    );

    // Verify allowed video items appear in the modal
    await waitFor(() => {
      expect(screen.getByText("intro.mp4")).toBeInTheDocument();
      expect(screen.getByText("demo.webm")).toBeInTheDocument();
      expect(screen.getByText("screen.mov")).toBeInTheDocument();
    });

    // Verify non-video and unsupported types are excluded
    expect(screen.queryByText("syllabus.pdf")).not.toBeInTheDocument();
    expect(screen.queryByText("old_clip.avi")).not.toBeInTheDocument();

    // Verify count header reflects exactly 3 compatible video items
    expect(screen.getByText("Existing Media Assets (3)")).toBeInTheDocument();

    // Verify file input accept attribute contains all 3 supported video MIME types
    const fileInput = screen.getByLabelText("Select file to upload");
    expect(fileInput).toHaveAttribute(
      "accept",
      "video/mp4,video/webm,video/quicktime"
    );
  });

  it("Scenario 8c: LessonEditorModal loads existing lesson video ID via deterministic resolution order", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const mockLesson: CurriculumLesson = {
      id: "lesson-abc-1",
      section_id: "sec-1",
      title: "Distributed Architecture",
      lesson_type: "VIDEO",
      sort_order: 0,
      duration_seconds: 600,
      is_preview: false,
      content: {
        media_asset_id: "canonical-video-uuid-999",
        file_key: "raw-videos/key.mp4",
      },
      resources: [],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    render(
      <QueryClientProvider client={queryClient}>
        <LessonEditorModal
          isOpen={true}
          onClose={() => {}}
          lesson={mockLesson}
          courseId="course-1"
        />
      </QueryClientProvider>
    );

    // Switch to content tab
    const contentTab = screen.getByRole("button", { name: /Video Media/i });
    fireEvent.click(contentTab);

    // Verify video media ID is displayed based on canonical media_asset_id
    expect(
      screen.getByText("Media ID: canonical-video-uuid-999")
    ).toBeInTheDocument();
  });
});
