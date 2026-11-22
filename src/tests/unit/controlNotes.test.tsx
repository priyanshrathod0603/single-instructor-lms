import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NotesCMSPage from "@/app/(control)/control/notes/page";
import { controlApi } from "@/lib/api/control";
import { NoteListResponse } from "@/types/content";

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockNotesList: NoteListResponse = {
  items: [
    {
      id: "note-1",
      title: "System Design Cheat Sheet",
      slug: "system-design-cheat-sheet",
      description: "Quick revision notes on caching, queues, and databases.",
      category: "Cheat Sheets",
      pdf_media_id: "media-pdf-1",
      pdf_url: "https://storage.example.com/system-design.pdf",
      file_size_bytes: 2097152, // 2 MB
      status: "PUBLISHED",
      published_at: "2026-11-10T10:00:00Z",
      author_id: "u-admin",
      author: {
        id: "u-admin",
        email: "superadmin@example.com",
        full_name: "Super Admin",
      },
      created_at: "2026-11-09T10:00:00Z",
      updated_at: "2026-11-10T10:00:00Z",
    },
    {
      id: "note-2",
      title: "SQL Performance Tuning Guide",
      slug: "sql-performance-tuning",
      description: "Index optimization and EXPLAIN ANALYZE.",
      category: "Guides",
      pdf_media_id: null,
      pdf_url: null,
      file_size_bytes: null,
      status: "DRAFT",
      published_at: null,
      author_id: "u-admin",
      author: {
        id: "u-admin",
        email: "superadmin@example.com",
        full_name: "Super Admin",
      },
      created_at: "2026-11-14T10:00:00Z",
      updated_at: "2026-11-14T10:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  per_page: 10,
  pages: 1,
};

function renderComponent() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <NotesCMSPage />
    </QueryClientProvider>
  );
}

describe("Notes CMS Page (SA-04.3)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "listNotes").mockResolvedValue(mockNotesList);
    vi.spyOn(controlApi, "getNoteCategories").mockResolvedValue(["Cheat Sheets", "Guides"]);
  });

  it("renders page header, metrics cards, and study notes table", async () => {
    renderComponent();

    expect(
      screen.getByText("Notes CMS & Study Material Governance")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Total Notes")).toBeInTheDocument();
      expect(screen.getByText("System Design Cheat Sheet")).toBeInTheDocument();
      expect(screen.getByText("/notes/system-design-cheat-sheet")).toBeInTheDocument();
      expect(screen.getByText("SQL Performance Tuning Guide")).toBeInTheDocument();
    });

    expect(screen.getAllByText("Cheat Sheets").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Guides").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("2.0 MB")).toBeInTheDocument();
  });

  it("opens create note modal and creates a new study note", async () => {
    const createSpy = vi.spyOn(controlApi, "createNote").mockResolvedValue({
      id: "note-3",
      title: "Docker Essentials",
      slug: "docker-essentials",
      category: "Cheat Sheets",
      status: "DRAFT",
      author_id: "u-admin",
      created_at: "2026-11-16T10:00:00Z",
      updated_at: "2026-11-16T10:00:00Z",
    });

    renderComponent();

    const uploadBtn = screen.getByRole("button", { name: /upload study note/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByText("Create a new study note or revision guide.")).toBeInTheDocument();
    });

    const titleInput = screen.getByPlaceholderText(/e\.g\. Next\.js 15 App Router/i);
    fireEvent.change(titleInput, { target: { value: "Docker Essentials" } });

    const submitBtn = screen.getByRole("button", { name: /create note/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Docker Essentials",
          status: "DRAFT",
        })
      );
    });
  });

  it("opens replace PDF modal and updates the document URL", async () => {
    const replaceSpy = vi.spyOn(controlApi, "replaceNotePdf").mockResolvedValue({
      ...mockNotesList.items[0],
      pdf_url: "https://storage.example.com/system-design-v2.pdf",
      file_size_bytes: 3145728, // 3 MB
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("System Design Cheat Sheet")).toBeInTheDocument();
    });

    const replaceButtons = screen.getAllByTitle("Replace Attached PDF");
    fireEvent.click(replaceButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Replace Attached PDF")).toBeInTheDocument();
    });

    const pdfInput = screen.getByPlaceholderText(/https:\/\/.*\/updated-notes\.pdf/i);
    fireEvent.change(pdfInput, {
      target: { value: "https://storage.example.com/system-design-v2.pdf" },
    });

    const confirmBtn = screen.getByRole("button", { name: /replace pdf/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(replaceSpy).toHaveBeenCalledWith("note-1", {
        pdf_url: "https://storage.example.com/system-design-v2.pdf",
        file_size_bytes: 2097152,
      });
    });
  });

  it("quick toggles publish/unpublish status for notes", async () => {
    const statusSpy = vi.spyOn(controlApi, "changeNoteStatus").mockResolvedValue({
      ...mockNotesList.items[0],
      status: "DRAFT",
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("System Design Cheat Sheet")).toBeInTheDocument();
    });

    const unpublishBtn = screen.getByRole("button", { name: /unpublish/i });
    fireEvent.click(unpublishBtn);

    await waitFor(() => {
      expect(statusSpy).toHaveBeenCalledWith("note-1", "DRAFT");
    });
  });

  it("opens delete confirmation modal and deletes a note", async () => {
    const deleteSpy = vi.spyOn(controlApi, "deleteNote").mockResolvedValue(undefined);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("System Design Cheat Sheet")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByTitle("Delete Note");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Delete Study Note")).toBeInTheDocument();
    });

    const confirmDeleteBtn = screen.getByRole("button", { name: /confirm delete/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("note-1");
    });
  });
});
