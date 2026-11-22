import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import BlogCMSPage from "@/app/(control)/control/blog/page";
import { controlApi } from "@/lib/api/control";
import { BlogPostListResponse, BlogPostItem } from "@/types/content";

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockBlogList: BlogPostListResponse = {
  items: [
    {
      id: "post-1",
      title: "Deep Dive into Next.js 15",
      slug: "deep-dive-nextjs-15",
      excerpt: "Explore Server Actions and caching.",
      content: "Detailed markdown content about Next.js 15 features.",
      category: "Frameworks",
      thumbnail_url: "https://example.com/next.png",
      status: "PUBLISHED",
      published_at: "2026-11-10T10:00:00Z",
      author_id: "u-admin",
      author: {
        id: "u-admin",
        email: "superadmin@example.com",
        full_name: "Super Admin",
      },
      created_at: "2026-11-08T10:00:00Z",
      updated_at: "2026-11-10T10:00:00Z",
    },
    {
      id: "post-2",
      title: "Building Microservices with Python",
      slug: "microservices-python",
      excerpt: "Designing resilient backends.",
      content: "Event-driven architecture with FastAPI and Kafka.",
      category: "Architecture",
      thumbnail_url: null,
      status: "DRAFT",
      published_at: null,
      author_id: "u-admin",
      author: {
        id: "u-admin",
        email: "superadmin@example.com",
        full_name: "Super Admin",
      },
      created_at: "2026-11-12T10:00:00Z",
      updated_at: "2026-11-12T10:00:00Z",
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
      <BlogCMSPage />
    </QueryClientProvider>
  );
}

describe("Blog CMS Page (SA-04.2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(controlApi, "listBlogPosts").mockResolvedValue(mockBlogList);
    vi.spyOn(controlApi, "getBlogCategories").mockResolvedValue(["Frameworks", "Architecture"]);
  });

  it("renders page header, metrics cards, and blog articles table", async () => {
    renderComponent();

    expect(screen.getByText("Blog CMS & Article Governance")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Total Articles")).toBeInTheDocument();
      expect(screen.getByText("Deep Dive into Next.js 15")).toBeInTheDocument();
      expect(screen.getByText("/blog/deep-dive-nextjs-15")).toBeInTheDocument();
      expect(screen.getByText("Building Microservices with Python")).toBeInTheDocument();
    });

    expect(screen.getAllByText("Frameworks").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Architecture").length).toBeGreaterThanOrEqual(1);
  });

  it("opens create post modal and creates a new blog post", async () => {
    const createSpy = vi.spyOn(controlApi, "createBlogPost").mockResolvedValue({
      id: "post-3",
      title: "New Async Patterns",
      slug: "new-async-patterns",
      content: "Async generators and tasks.",
      category: "Tutorials",
      status: "DRAFT",
      author_id: "u-admin",
      created_at: "2026-11-16T10:00:00Z",
      updated_at: "2026-11-16T10:00:00Z",
    });

    renderComponent();

    const createBtn = screen.getByRole("button", { name: /create post/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText("Create Blog Post")).toBeInTheDocument();
    });

    const titleInput = screen.getByPlaceholderText(/e\.g\. Master Full-Stack Architecture/i);
    fireEvent.change(titleInput, { target: { value: "New Async Patterns" } });

    const contentTextarea = screen.getByPlaceholderText(/write the article content here/i);
    fireEvent.change(contentTextarea, { target: { value: "Async generators and tasks." } });

    const submitBtn = screen.getByRole("button", { name: /create article/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New Async Patterns",
          content: "Async generators and tasks.",
          status: "DRAFT",
        })
      );
    });
  });

  it("quick toggles publish/unpublish status", async () => {
    const statusSpy = vi.spyOn(controlApi, "changeBlogStatus").mockResolvedValue({
      ...mockBlogList.items[0],
      status: "DRAFT",
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Deep Dive into Next.js 15")).toBeInTheDocument();
    });

    const unpublishBtn = screen.getByRole("button", { name: /unpublish/i });
    fireEvent.click(unpublishBtn);

    await waitFor(() => {
      expect(statusSpy).toHaveBeenCalledWith("post-1", "DRAFT");
    });
  });

  it("opens delete confirmation modal and deletes a blog post", async () => {
    const deleteSpy = vi.spyOn(controlApi, "deleteBlogPost").mockResolvedValue(undefined);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Deep Dive into Next.js 15")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByTitle("Delete Article");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Delete Blog Post")).toBeInTheDocument();
    });

    const confirmDeleteBtn = screen.getByRole("button", { name: /confirm delete/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("post-1");
    });
  });
});
