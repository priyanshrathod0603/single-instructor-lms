"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileEdit,
  FileText,
  Search,
  RotateCcw,
  CheckCircle2,
  Clock,
  Archive,
  Eye,
  Plus,
  Edit3,
  Trash2,
  Tag,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Globe,
  Image as ImageIcon,
  User,
  Calendar,
  Layers,
  ArrowRightLeft,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import {
  BlogPostItem,
  BlogPostCreatePayload,
  BlogPostUpdatePayload,
} from "@/types/content";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalTitle,
  ModalDescription,
  ModalFooter,
} from "@/components/ui/Modal";

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export default function BlogCMSPage() {
  const queryClient = useQueryClient();

  // Filter & Pagination State
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [page, setPage] = useState(1);
  const perPage = 10;

  // Modal States
  const [inspectPost, setInspectPost] = useState<BlogPostItem | null>(null);
  const [postToDelete, setPostToDelete] = useState<BlogPostItem | null>(null);

  // Create / Edit Modal State
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingPostId, setEditingPostId] = useState<string | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formSlug, setFormSlug] = useState("");
  const [formCategory, setFormCategory] = useState("General");
  const [formExcerpt, setFormExcerpt] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formThumbnailUrl, setFormThumbnailUrl] = useState("");
  const [formStatus, setFormStatus] = useState("DRAFT");
  const [editorError, setEditorError] = useState<string | null>(null);

  // 1. Fetch Categories
  const { data: categories = [] } = useQuery({
    queryKey: ["control-blog-categories"],
    queryFn: () => controlApi.getBlogCategories(),
    staleTime: 30000,
  });

  // 2. Fetch Blog Overview Metrics (first page sample to estimate counts)
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ["control-blog-metrics"],
    queryFn: () => controlApi.listBlogPosts({ per_page: 100 }),
    staleTime: 30000,
  });

  const totalArticles = metricsData?.total ?? 0;
  const publishedArticles =
    metricsData?.items.filter((p) => p.status === "PUBLISHED").length ?? 0;
  const draftArticles =
    metricsData?.items.filter((p) => p.status === "DRAFT").length ?? 0;
  const categoriesCount = categories.length;

  // 3. Fetch Paginated Blog Posts
  const {
    data: blogData,
    isLoading: blogLoading,
    isFetching,
    error: blogError,
    refetch,
  } = useQuery({
    queryKey: [
      "control-blog-posts",
      statusFilter,
      categoryFilter,
      searchTerm,
      page,
      perPage,
    ],
    queryFn: () =>
      controlApi.listBlogPosts({
        status: statusFilter === "ALL" ? undefined : statusFilter,
        category: categoryFilter === "ALL" ? undefined : categoryFilter,
        search: searchTerm.trim() || undefined,
        sort_by: "created_at",
        sort_order: "desc",
        page,
        per_page: perPage,
      }),
  });

  // 4. Create / Update Mutation
  const savePostMutation = useMutation({
    mutationFn: async () => {
      if (!formTitle.trim()) throw new Error("Article title is required.");
      if (!formContent.trim()) throw new Error("Article content is required.");

      const payload = {
        title: formTitle.trim(),
        slug: formSlug.trim() || slugify(formTitle),
        category: formCategory.trim() || "General",
        excerpt: formExcerpt.trim() || undefined,
        content: formContent.trim(),
        thumbnail_url: formThumbnailUrl.trim() || undefined,
        status: formStatus,
      };

      if (editingPostId) {
        return controlApi.updateBlogPost(editingPostId, payload as BlogPostUpdatePayload);
      } else {
        return controlApi.createBlogPost(payload as BlogPostCreatePayload);
      }
    },
    onSuccess: (savedPost) => {
      toast.success(
        editingPostId
          ? `Article "${savedPost.title}" updated successfully.`
          : `Article "${savedPost.title}" created successfully.`
      );
      closeEditor();
      queryClient.invalidateQueries({ queryKey: ["control-blog-posts"] });
      queryClient.invalidateQueries({ queryKey: ["control-blog-metrics"] });
      queryClient.invalidateQueries({ queryKey: ["control-blog-categories"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to save blog post.";
      setEditorError(msg);
      toast.error(msg);
    },
  });

  // 5. Quick Status Change Mutation (Publish / Unpublish)
  const toggleStatusMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: string; newStatus: string }) =>
      controlApi.changeBlogStatus(id, newStatus),
    onSuccess: (updated) => {
      toast.success(`Post "${updated.title}" marked as ${updated.status}.`);
      queryClient.invalidateQueries({ queryKey: ["control-blog-posts"] });
      queryClient.invalidateQueries({ queryKey: ["control-blog-metrics"] });
      if (inspectPost && inspectPost.id === updated.id) {
        setInspectPost(updated);
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to change status.";
      toast.error(msg);
    },
  });

  // 6. Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => controlApi.deleteBlogPost(id),
    onSuccess: () => {
      toast.success(`Blog post deleted successfully.`);
      setPostToDelete(null);
      queryClient.invalidateQueries({ queryKey: ["control-blog-posts"] });
      queryClient.invalidateQueries({ queryKey: ["control-blog-metrics"] });
      queryClient.invalidateQueries({ queryKey: ["control-blog-categories"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to delete post.";
      toast.error(msg);
    },
  });

  // Editor Open / Close Helpers
  const openCreateEditor = () => {
    setEditingPostId(null);
    setFormTitle("");
    setFormSlug("");
    setFormCategory("General");
    setFormExcerpt("");
    setFormContent("");
    setFormThumbnailUrl("");
    setFormStatus("DRAFT");
    setEditorError(null);
    setIsEditorOpen(true);
  };

  const openEditEditor = (post: BlogPostItem) => {
    setEditingPostId(post.id);
    setFormTitle(post.title);
    setFormSlug(post.slug);
    setFormCategory(post.category || "General");
    setFormExcerpt(post.excerpt || "");
    setFormContent(post.content);
    setFormThumbnailUrl(post.thumbnail_url || "");
    setFormStatus(post.status);
    setEditorError(null);
    setIsEditorOpen(true);
  };

  const closeEditor = () => {
    setIsEditorOpen(false);
    setEditingPostId(null);
    setEditorError(null);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PUBLISHED":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
            Published
          </span>
        );
      case "DRAFT":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
            Draft
          </span>
        );
      case "ARCHIVED":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 border border-rose-200">
            Archived
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FileEdit className="h-6 w-6 text-primary-teal" />
            <h1 className="font-heading text-2xl font-bold text-slate-900">
              Blog CMS & Article Governance
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Author, edit, publish, and govern platform educational articles and editorial content.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              refetch();
              queryClient.invalidateQueries({ queryKey: ["control-blog-metrics"] });
            }}
            disabled={isFetching}
            className="flex items-center gap-2"
          >
            <RotateCcw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={openCreateEditor}
            className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-2 font-medium"
          >
            <Plus className="h-4 w-4" />
            Create Post
          </Button>
        </div>
      </div>

      {/* KPI Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Articles */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Articles
            </span>
            <FileText className="h-4 w-4 text-blue-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-slate-900 font-mono">
                {totalArticles}
              </span>
            </div>
          )}
        </div>

        {/* Published */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Published
            </span>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-emerald-600 font-mono">
                {publishedArticles}
              </span>
            </div>
          )}
        </div>

        {/* Drafts */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Drafts
            </span>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-amber-600 font-mono">
                {draftArticles}
              </span>
            </div>
          )}
        </div>

        {/* Categories */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Categories
            </span>
            <Layers className="h-4 w-4 text-purple-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-purple-600 font-mono">
                {categoriesCount}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-[16px] border border-slate-200 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row gap-3">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              type="text"
              placeholder="Search by article title, slug, or content..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setPage(1);
              }}
              className="pl-9 bg-slate-50 border-slate-200 text-sm"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-teal"
            >
              <option value="ALL">All Statuses</option>
              <option value="PUBLISHED">Published</option>
              <option value="DRAFT">Draft</option>
              <option value="ARCHIVED">Archived</option>
            </select>
          </div>

          {/* Category Filter */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Category:</span>
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-teal"
            >
              <option value="ALL">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          {/* Reset Filters */}
          {(searchTerm || statusFilter !== "ALL" || categoryFilter !== "ALL") && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearchTerm("");
                setStatusFilter("ALL");
                setCategoryFilter("ALL");
                setPage(1);
              }}
              className="text-xs text-slate-500 hover:text-slate-800"
            >
              Reset
            </Button>
          )}
        </div>
      </div>

      {/* Blog Posts Table */}
      <div className="bg-white rounded-[16px] border border-slate-200 shadow-sm overflow-hidden">
        {blogLoading ? (
          <div className="p-12 flex flex-col items-center justify-center text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
            <p className="text-sm">Loading blog articles...</p>
          </div>
        ) : blogError ? (
          <div className="p-12 text-center text-rose-500">
            <AlertCircle className="h-8 w-8 mx-auto mb-3" />
            <p className="text-sm font-medium">Failed to load blog posts</p>
            <p className="text-xs text-slate-500 mt-1">
              {(blogError as any)?.message || "Please check network or permissions."}
            </p>
          </div>
        ) : !blogData?.items || blogData.items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <FileText className="h-8 w-8 mx-auto mb-3 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">No blog posts found</p>
            <p className="text-xs text-slate-400 mt-1">
              Create your first article or adjust filters to view drafts and archived posts.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-3 px-4">Article</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Author</th>
                  <th className="py-3 px-4">Published Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {blogData.items.map((post) => (
                  <tr key={post.id} className="hover:bg-slate-50/50 transition-colors">
                    {/* Article Details */}
                    <td className="py-3 px-4 max-w-sm">
                      <div className="font-semibold text-slate-900 line-clamp-1">
                        {post.title}
                      </div>
                      <div className="text-xs font-mono text-slate-400 mt-0.5 truncate">
                        /blog/{post.slug}
                      </div>
                      {post.excerpt && (
                        <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                          {post.excerpt}
                        </div>
                      )}
                    </td>

                    {/* Category */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {post.category}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getStatusBadge(post.status)}
                    </td>

                    {/* Author */}
                    <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <User className="h-3.5 w-3.5 text-slate-400" />
                        <span>{post.author?.full_name || "Super Admin"}</span>
                      </div>
                    </td>

                    {/* Published Date */}
                    <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-500 font-mono">
                      {formatDate(post.published_at || post.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setInspectPost(post)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="View Article"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditEditor(post)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="Edit Article"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </Button>

                        {post.status === "PUBLISHED" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toggleStatusMutation.mutate({
                                id: post.id,
                                newStatus: "DRAFT",
                              })
                            }
                            className="h-8 px-2 text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                            title="Unpublish (set to draft)"
                          >
                            Unpublish
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toggleStatusMutation.mutate({
                                id: post.id,
                                newStatus: "PUBLISHED",
                              })
                            }
                            className="h-8 px-2 text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                            title="Publish Live"
                          >
                            Publish
                          </Button>
                        )}

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPostToDelete(post)}
                          className="h-8 px-2 text-xs text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                          title="Delete Article"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {blogData && blogData.pages > 1 && (
          <div className="py-3 px-4 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing page <span className="font-medium text-slate-700">{page}</span> of{" "}
              <span className="font-medium text-slate-700">{blogData.pages}</span> (
              {blogData.total} total posts)
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-7 px-2 text-xs"
              >
                <ChevronLeft className="h-3.5 w-3.5 mr-1" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(blogData.pages, p + 1))}
                disabled={page >= blogData.pages}
                className="h-7 px-2 text-xs"
              >
                Next <ChevronRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Inspect Blog Post Modal */}
      <Modal open={!!inspectPost} onOpenChange={(open) => !open && setInspectPost(null)}>
        <ModalContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5 text-primary-teal" />
              Blog Post Details
            </ModalTitle>
            <ModalDescription>
              Inspection of article content, author attribution, and publication lifecycle.
            </ModalDescription>
          </ModalHeader>

          {inspectPost && (
            <div className="space-y-4 py-2 text-sm text-slate-700">
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-slate-900 text-lg">
                      {inspectPost.title}
                    </h3>
                    <p className="text-xs font-mono text-slate-500">
                      slug: /blog/{inspectPost.slug}
                    </p>
                  </div>
                  <div>{getStatusBadge(inspectPost.status)}</div>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 pt-2 border-t border-slate-200">
                  <span className="flex items-center gap-1">
                    <Tag className="h-3.5 w-3.5 text-slate-400" />
                    Category: <strong className="text-slate-700">{inspectPost.category}</strong>
                  </span>
                  <span className="flex items-center gap-1">
                    <User className="h-3.5 w-3.5 text-slate-400" />
                    Author:{" "}
                    <strong className="text-slate-700">
                      {inspectPost.author?.full_name || "Super Admin"}
                    </strong>
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5 text-slate-400" />
                    Published:{" "}
                    <strong className="text-slate-700">
                      {formatDate(inspectPost.published_at || inspectPost.created_at)}
                    </strong>
                  </span>
                </div>
              </div>

              {inspectPost.thumbnail_url && (
                <div>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Thumbnail Image
                  </span>
                  <div className="mt-1 p-2 bg-slate-50 rounded-lg border border-slate-200">
                    <p className="text-xs font-mono text-blue-600 truncate mb-2">
                      {inspectPost.thumbnail_url}
                    </p>
                    <img
                      src={inspectPost.thumbnail_url}
                      alt={inspectPost.title}
                      className="max-h-48 rounded object-cover border border-slate-200"
                    />
                  </div>
                </div>
              )}

              {inspectPost.excerpt && (
                <div>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Excerpt
                  </span>
                  <p className="text-xs text-slate-600 mt-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200 italic">
                    {inspectPost.excerpt}
                  </p>
                </div>
              )}

              <div>
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Article Body
                </span>
                <div className="mt-1 p-3 bg-slate-50 rounded-lg border border-slate-200 font-sans text-xs text-slate-800 whitespace-pre-wrap max-h-60 overflow-y-auto">
                  {inspectPost.content}
                </div>
              </div>
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setInspectPost(null)}
            >
              Close
            </Button>
            {inspectPost && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const p = inspectPost;
                  setInspectPost(null);
                  openEditEditor(p);
                }}
                className="bg-primary-teal hover:bg-primary-teal/90 text-white"
              >
                Edit Post
              </Button>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Create / Edit Blog Post Modal */}
      <Modal open={isEditorOpen} onOpenChange={(open) => !open && closeEditor()}>
        <ModalContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              {editingPostId ? (
                <>
                  <Edit3 className="h-5 w-5 text-primary-teal" /> Edit Blog Post
                </>
              ) : (
                <>
                  <Plus className="h-5 w-5 text-primary-teal" /> Create Blog Post
                </>
              )}
            </ModalTitle>
            <ModalDescription>
              {editingPostId
                ? "Update blog article content, category, and publication status."
                : "Author a new blog article for the platform."}
            </ModalDescription>
          </ModalHeader>

          <div className="space-y-4 py-2 text-sm">
            {/* Title */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Title <span className="text-rose-500">*</span>
              </label>
              <Input
                type="text"
                placeholder="e.g. Master Full-Stack Architecture in 2026"
                value={formTitle}
                onChange={(e) => {
                  setFormTitle(e.target.value);
                  if (!editingPostId) {
                    setFormSlug(slugify(e.target.value));
                  }
                }}
                className="bg-white border-slate-300 text-sm"
              />
            </div>

            {/* Slug & Category row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  URL Slug
                </label>
                <Input
                  type="text"
                  placeholder="master-full-stack-architecture"
                  value={formSlug}
                  onChange={(e) => setFormSlug(slugify(e.target.value))}
                  className="bg-white border-slate-300 font-mono text-xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Category
                </label>
                <Input
                  type="text"
                  placeholder="e.g. Architecture, Tutorials, Guides"
                  value={formCategory}
                  onChange={(e) => setFormCategory(e.target.value)}
                  className="bg-white border-slate-300 text-sm"
                />
              </div>
            </div>

            {/* Status & Thumbnail */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Publication Status
                </label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value)}
                  className="w-full text-sm bg-white border border-slate-300 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
                >
                  <option value="DRAFT">DRAFT (Unpublished)</option>
                  <option value="PUBLISHED">PUBLISHED (Live)</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Thumbnail URL (Optional)
                </label>
                <Input
                  type="text"
                  placeholder="https://.../thumbnail.webp"
                  value={formThumbnailUrl}
                  onChange={(e) => setFormThumbnailUrl(e.target.value)}
                  className="bg-white border-slate-300 text-sm font-mono text-xs"
                />
              </div>
            </div>

            {/* Excerpt */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Excerpt (Brief Summary)
              </label>
              <textarea
                value={formExcerpt}
                onChange={(e) => setFormExcerpt(e.target.value)}
                rows={2}
                placeholder="A concise synopsis of the post for card previews and search results..."
                className="w-full text-sm bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
              />
            </div>

            {/* Content Body */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Article Content <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={formContent}
                onChange={(e) => setFormContent(e.target.value)}
                rows={8}
                placeholder="Write the article content here (Markdown formatted)..."
                className="w-full text-sm bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary-teal"
              />
            </div>

            {editorError && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                {editorError}
              </div>
            )}
          </div>

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={closeEditor}
              disabled={savePostMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => savePostMutation.mutate()}
              disabled={savePostMutation.isPending}
              className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-1.5"
            >
              {savePostMutation.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              {editingPostId ? "Save Changes" : "Create Article"}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal open={!!postToDelete} onOpenChange={(open) => !open && setPostToDelete(null)}>
        <ModalContent className="max-w-md">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg text-rose-600">
              <Trash2 className="h-5 w-5 text-rose-600" />
              Delete Blog Post
            </ModalTitle>
            <ModalDescription>
              Are you sure you want to permanently delete this blog post? This action is audited and cannot be undone.
            </ModalDescription>
          </ModalHeader>

          {postToDelete && (
            <div className="py-2 text-sm">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 font-medium">Article Title:</span>
                <p className="font-semibold text-slate-900 mt-0.5">{postToDelete.title}</p>
                <p className="text-xs font-mono text-slate-500 mt-1">
                  /blog/{postToDelete.slug}
                </p>
              </div>
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPostToDelete(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => postToDelete && deleteMutation.mutate(postToDelete.id)}
              disabled={deleteMutation.isPending}
              className="bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-1.5"
            >
              {deleteMutation.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              Confirm Delete
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
