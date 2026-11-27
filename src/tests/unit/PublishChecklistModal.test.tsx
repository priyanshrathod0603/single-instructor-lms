import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PublishChecklistModal } from "@/components/admin/PublishChecklistModal";
import { coursesApi } from "@/lib/api/courses";

vi.mock("@/lib/api/courses", () => ({
  coursesApi: {
    getPublishChecklist: vi.fn(),
    publishRevision: vi.fn(),
  },
}));

describe("PublishChecklistModal Usability & Error Transparency", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  const renderModal = (props: Partial<React.ComponentProps<typeof PublishChecklistModal>> = {}) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <PublishChecklistModal
          isOpen={true}
          onClose={vi.fn()}
          courseId="course-123"
          revisionId="rev-456"
          {...props}
        />
      </QueryClientProvider>
    );
  };

  it("renders blockers with actionable 'How to fix' hints and disables publish button", async () => {
    vi.mocked(coursesApi.getPublishChecklist).mockResolvedValueOnce({
      course_id: "course-123",
      revision_id: "rev-456",
      revision_no: 1,
      can_publish: false,
      blockers: [
        {
          code: "MEDIA_NOT_READY",
          message: "Video asset for lesson 'Intro' is not ready (status: PROCESSING).",
        },
        {
          code: "EMPTY_HEADLINE",
          message: "Course headline cannot be empty.",
        },
      ],
      warnings: [],
    });

    renderModal();

    expect(await screen.findByText("Publication Blocked: Issues Require Resolution")).toBeInTheDocument();
    expect(screen.getByText("Video asset for lesson 'Intro' is not ready (status: PROCESSING).")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Video is transcoding in the background\. Wait a moment for processing to finish, or select a ready video from Media Library\./i
      )
    ).toBeInTheDocument();

    expect(screen.getByText("Course headline cannot be empty.")).toBeInTheDocument();
    expect(
      screen.getByText(/Go to Course Details to fill in required metadata\./i)
    ).toBeInTheDocument();

    const publishBtn = screen.getByRole("button", { name: /publish live snapshot/i });
    expect(publishBtn).toBeDisabled();
  });

  it("enables publish button when checklist passes with zero blockers", async () => {
    vi.mocked(coursesApi.getPublishChecklist).mockResolvedValueOnce({
      course_id: "course-123",
      revision_id: "rev-456",
      revision_no: 2,
      can_publish: true,
      blockers: [],
      warnings: [],
    });

    renderModal();

    expect(await screen.findByText("Ready for Publication")).toBeInTheDocument();
    expect(
      screen.getByText("All automated checks passed. Ready to snapshot and deploy this revision as the live version.")
    ).toBeInTheDocument();

    const publishBtn = screen.getByRole("button", { name: /publish live snapshot/i });
    expect(publishBtn).not.toBeDisabled();
  });

  it("renders prominent error alert inside modal when publish mutation fails", async () => {
    vi.mocked(coursesApi.getPublishChecklist).mockResolvedValueOnce({
      course_id: "course-123",
      revision_id: "rev-456",
      revision_no: 1,
      can_publish: true,
      blockers: [],
      warnings: [],
    });

    vi.mocked(coursesApi.publishRevision).mockRejectedValueOnce(
      new Error("Cannot publish revision; pre-flight checklist conditions failed.")
    );

    renderModal();

    expect(await screen.findByText("Ready for Publication")).toBeInTheDocument();
    const publishBtn = screen.getByRole("button", { name: /publish live snapshot/i });
    expect(publishBtn).not.toBeDisabled();

    fireEvent.click(publishBtn);

    expect(await screen.findByText("Publishing Blocked")).toBeInTheDocument();
    expect(
      screen.getByText("Cannot publish revision; pre-flight checklist conditions failed.")
    ).toBeInTheDocument();
  });

  it("calls onSuccess and onClose when publication succeeds", async () => {
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    vi.mocked(coursesApi.getPublishChecklist).mockResolvedValueOnce({
      course_id: "course-123",
      revision_id: "rev-456",
      revision_no: 1,
      can_publish: true,
      blockers: [],
      warnings: [],
    });

    vi.mocked(coursesApi.publishRevision).mockResolvedValueOnce({
      course_id: "course-123",
      published_revision_id: "rev-456",
      published_at: "2026-11-23T20:00:00Z",
    } as any);

    renderModal({ onSuccess: handleSuccess, onClose: handleClose });

    expect(await screen.findByText("Ready for Publication")).toBeInTheDocument();
    const publishBtn = screen.getByRole("button", { name: /publish live snapshot/i });
    expect(publishBtn).not.toBeDisabled();

    fireEvent.click(publishBtn);

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledTimes(1);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });
});
