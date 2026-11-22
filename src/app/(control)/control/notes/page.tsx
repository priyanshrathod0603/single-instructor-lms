"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
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
  User,
  Calendar,
  Layers,
  FileUp,
  FileDown,
  ExternalLink,
  BookOpen,
} from "lucide-react";
import { toast } from "sonner";
import { controlApi } from "@/lib/api/control";
import {
  NoteItem,
  NoteCreatePayload,
  NoteUpdatePayload,
  NoteReplacePdfPayload,
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

function formatFileSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

export default function NotesCMSPage() {
  const queryClient = useQueryClient();

  // Filters & Pagination State
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [page, setPage] = useState(1);
  const perPage = 10;

  // Modal States
  const [inspectNote, setInspectNote] = useState<NoteItem | null>(null);
  const [noteToDelete, setNoteToDelete] = useState<NoteItem | null>(null);

  // Replace PDF Modal State
  const [noteToReplacePdf, setNoteToReplacePdf] = useState<NoteItem | null>(null);
  const [replacePdfUrl, setReplacePdfUrl] = useState("");
  const [replaceFileSize, setReplaceFileSize] = useState<number | undefined>(undefined);
  const [replacePdfError, setReplacePdfError] = useState<string | null>(null);

  // Create / Edit Modal State
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formSlug, setFormSlug] = useState("");
  const [formCategory, setFormCategory] = useState("Study Materials");
  const [formDescription, setFormDescription] = useState("");
  const [formPdfUrl, setFormPdfUrl] = useState("");
  const [formFileSize, setFormFileSize] = useState<number | undefined>(undefined);
  const [formStatus, setFormStatus] = useState("DRAFT");
  const [editorError, setEditorError] = useState<string | null>(null);

  // 1. Fetch Categories
  const { data: categories = [] } = useQuery({
    queryKey: ["control-notes-categories"],
    queryFn: () => controlApi.getNoteCategories(),
    staleTime: 30000,
  });

  // 2. Fetch Overview Metrics
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ["control-notes-metrics"],
    queryFn: () => controlApi.listNotes({ per_page: 100 }),
    staleTime: 30000,
  });

  const totalNotes = metricsData?.total ?? 0;
  const publishedNotes =
    metricsData?.items.filter((n) => n.status === "PUBLISHED").length ?? 0;
  const draftNotes =
    metricsData?.items.filter((n) => n.status === "DRAFT").length ?? 0;
  const categoriesCount = categories.length;

  // 3. Fetch Paginated Notes
  const {
    data: notesData,
    isLoading: notesLoading,
    isFetching,
    error: notesError,
    refetch,
  } = useQuery({
    queryKey: [
      "control-notes-list",
      statusFilter,
      categoryFilter,
      searchTerm,
      page,
      perPage,
    ],
    queryFn: () =>
      controlApi.listNotes({
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
  const saveNoteMutation = useMutation({
    mutationFn: async () => {
      if (!formTitle.trim()) throw new Error("Note title is required.");

      const payload = {
        title: formTitle.trim(),
        slug: formSlug.trim() || slugify(formTitle),
        category: formCategory.trim() || "Study Materials",
        description: formDescription.trim() || undefined,
        pdf_url: formPdfUrl.trim() || undefined,
        file_size_bytes: formFileSize && formFileSize > 0 ? formFileSize : undefined,
        status: formStatus,
      };

      if (editingNoteId) {
        return controlApi.updateNote(editingNoteId, payload as NoteUpdatePayload);
      } else {
        return controlApi.createNote(payload as NoteCreatePayload);
      }
    },
    onSuccess: (savedNote) => {
      toast.success(
        editingNoteId
          ? `Note "${savedNote.title}" updated successfully.`
          : `Note "${savedNote.title}" created successfully.`
      );
      closeEditor();
      queryClient.invalidateQueries({ queryKey: ["control-notes-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-notes-metrics"] });
      queryClient.invalidateQueries({ queryKey: ["control-notes-categories"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to save note.";
      setEditorError(msg);
      toast.error(msg);
    },
  });

  // 5. Replace PDF Mutation
  const replacePdfMutation = useMutation({
    mutationFn: async () => {
      if (!noteToReplacePdf) throw new Error("No note selected.");
      if (!replacePdfUrl.trim()) throw new Error("PDF document URL is required.");

      const payload: NoteReplacePdfPayload = {
        pdf_url: replacePdfUrl.trim(),
        file_size_bytes: replaceFileSize && replaceFileSize > 0 ? replaceFileSize : undefined,
      };

      return controlApi.replaceNotePdf(noteToReplacePdf.id, payload);
    },
    onSuccess: (updatedNote) => {
      toast.success(`PDF document for "${updatedNote.title}" replaced successfully.`);
      setNoteToReplacePdf(null);
      setReplacePdfUrl("");
      setReplaceFileSize(undefined);
      setReplacePdfError(null);
      queryClient.invalidateQueries({ queryKey: ["control-notes-list"] });
      if (inspectNote && inspectNote.id === updatedNote.id) {
        setInspectNote(updatedNote);
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to replace PDF.";
      setReplacePdfError(msg);
      toast.error(msg);
    },
  });

  // 6. Quick Status Toggle Mutation
  const toggleStatusMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: string; newStatus: string }) =>
      controlApi.changeNoteStatus(id, newStatus),
    onSuccess: (updated) => {
      toast.success(`Note "${updated.title}" marked as ${updated.status}.`);
      queryClient.invalidateQueries({ queryKey: ["control-notes-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-notes-metrics"] });
      if (inspectNote && inspectNote.id === updated.id) {
        setInspectNote(updated);
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to change status.";
      toast.error(msg);
    },
  });

  // 7. Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => controlApi.deleteNote(id),
    onSuccess: () => {
      toast.success("Study note deleted successfully.");
      setNoteToDelete(null);
      queryClient.invalidateQueries({ queryKey: ["control-notes-list"] });
      queryClient.invalidateQueries({ queryKey: ["control-notes-metrics"] });
      queryClient.invalidateQueries({ queryKey: ["control-notes-categories"] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || err?.message || "Failed to delete note.";
      toast.error(msg);
    },
  });

  // Editor Helpers
  const openCreateEditor = () => {
    setEditingNoteId(null);
    setFormTitle("");
    setFormSlug("");
    setFormCategory("Study Materials");
    setFormDescription("");
    setFormPdfUrl("");
    setFormFileSize(undefined);
    setFormStatus("DRAFT");
    setEditorError(null);
    setIsEditorOpen(true);
  };

  const openEditEditor = (note: NoteItem) => {
    setEditingNoteId(note.id);
    setFormTitle(note.title);
    setFormSlug(note.slug);
    setFormCategory(note.category || "Study Materials");
    setFormDescription(note.description || "");
    setFormPdfUrl(note.pdf_url || "");
    setFormFileSize(note.file_size_bytes || undefined);
    setFormStatus(note.status);
    setEditorError(null);
    setIsEditorOpen(true);
  };

  const closeEditor = () => {
    setIsEditorOpen(false);
    setEditingNoteId(null);
    setEditorError(null);
  };

  const openReplacePdfModal = (note: NoteItem) => {
    setNoteToReplacePdf(note);
    setReplacePdfUrl(note.pdf_url || "");
    setReplaceFileSize(note.file_size_bytes || undefined);
    setReplacePdfError(null);
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
            <FileText className="h-6 w-6 text-primary-teal" />
            <h1 className="font-heading text-2xl font-bold text-slate-900">
              Notes CMS & Study Material Governance
            </h1>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Super Admin repository for downloadable course PDFs, revision cheat sheets, and companion notes.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              refetch();
              queryClient.invalidateQueries({ queryKey: ["control-notes-metrics"] });
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
            Upload Study Note
          </Button>
        </div>
      </div>

      {/* KPI Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Notes */}
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Notes
            </span>
            <BookOpen className="h-4 w-4 text-blue-500" />
          </div>
          {metricsLoading ? (
            <div className="h-8 w-16 bg-slate-100 animate-pulse rounded mt-2" />
          ) : (
            <div className="mt-2">
              <span className="text-2xl font-bold text-slate-900 font-mono">
                {totalNotes}
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
                {publishedNotes}
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
                {draftNotes}
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
              placeholder="Search by note title, slug, or description..."
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

      {/* Notes Table */}
      <div className="bg-white rounded-[16px] border border-slate-200 shadow-sm overflow-hidden">
        {notesLoading ? (
          <div className="p-12 flex flex-col items-center justify-center text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal mb-3" />
            <p className="text-sm">Loading study notes...</p>
          </div>
        ) : notesError ? (
          <div className="p-12 text-center text-rose-500">
            <AlertCircle className="h-8 w-8 mx-auto mb-3" />
            <p className="text-sm font-medium">Failed to load study notes</p>
            <p className="text-xs text-slate-500 mt-1">
              {(notesError as any)?.message || "Please check network or permissions."}
            </p>
          </div>
        ) : !notesData?.items || notesData.items.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <FileText className="h-8 w-8 mx-auto mb-3 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">No study notes found</p>
            <p className="text-xs text-slate-400 mt-1">
              Upload your first companion note or adjust filters to view drafts.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/75 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-3 px-4">Study Note</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Attached Document</th>
                  <th className="py-3 px-4">Author</th>
                  <th className="py-3 px-4">Published Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {notesData.items.map((note) => (
                  <tr key={note.id} className="hover:bg-slate-50/50 transition-colors">
                    {/* Note Details */}
                    <td className="py-3 px-4 max-w-xs">
                      <div className="font-semibold text-slate-900 line-clamp-1">
                        {note.title}
                      </div>
                      <div className="text-xs font-mono text-slate-400 mt-0.5 truncate">
                        /notes/{note.slug}
                      </div>
                      {note.description && (
                        <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                          {note.description}
                        </div>
                      )}
                    </td>

                    {/* Category */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                        {note.category}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      {getStatusBadge(note.status)}
                    </td>

                    {/* Attached Document */}
                    <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-600">
                      {note.pdf_url ? (
                        <div className="flex items-center gap-1.5">
                          <FileDown className="h-4 w-4 text-primary-teal shrink-0" />
                          <span className="font-mono">{formatFileSize(note.file_size_bytes)}</span>
                          <a
                            href={note.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-primary-teal"
                            title="Open Document Link"
                          >
                            <ExternalLink className="h-3 w-3 ml-0.5" />
                          </a>
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">No PDF attached</span>
                      )}
                    </td>

                    {/* Author */}
                    <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <User className="h-3.5 w-3.5 text-slate-400" />
                        <span>{note.author?.full_name || "Super Admin"}</span>
                      </div>
                    </td>

                    {/* Published Date */}
                    <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-500 font-mono">
                      {formatDate(note.published_at || note.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setInspectNote(note)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="View Note Details"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditEditor(note)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="Edit Note"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openReplacePdfModal(note)}
                          className="h-8 px-2 text-xs flex items-center gap-1 text-slate-600 hover:text-slate-900"
                          title="Replace Attached PDF"
                        >
                          <FileUp className="h-3.5 w-3.5" />
                        </Button>

                        {note.status === "PUBLISHED" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              toggleStatusMutation.mutate({
                                id: note.id,
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
                                id: note.id,
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
                          onClick={() => setNoteToDelete(note)}
                          className="h-8 px-2 text-xs text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                          title="Delete Note"
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
        {notesData && notesData.pages > 1 && (
          <div className="py-3 px-4 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing page <span className="font-medium text-slate-700">{page}</span> of{" "}
              <span className="font-medium text-slate-700">{notesData.pages}</span> (
              {notesData.total} total notes)
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
                onClick={() => setPage((p) => Math.min(notesData.pages, p + 1))}
                disabled={page >= notesData.pages}
                className="h-7 px-2 text-xs"
              >
                Next <ChevronRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Inspect Note Modal */}
      <Modal open={!!inspectNote} onOpenChange={(open) => !open && setInspectNote(null)}>
        <ModalContent className="max-w-xl">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5 text-primary-teal" />
              Study Note Details
            </ModalTitle>
            <ModalDescription>
              Inspection of note metadata, attached document details, and publication lifecycle.
            </ModalDescription>
          </ModalHeader>

          {inspectNote && (
            <div className="space-y-4 py-2 text-sm text-slate-700">
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-slate-900 text-lg">
                      {inspectNote.title}
                    </h3>
                    <p className="text-xs font-mono text-slate-500">
                      slug: /notes/{inspectNote.slug}
                    </p>
                  </div>
                  <div>{getStatusBadge(inspectNote.status)}</div>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 pt-2 border-t border-slate-200">
                  <span className="flex items-center gap-1">
                    <Tag className="h-3.5 w-3.5 text-slate-400" />
                    Category: <strong className="text-slate-700">{inspectNote.category}</strong>
                  </span>
                  <span className="flex items-center gap-1">
                    <User className="h-3.5 w-3.5 text-slate-400" />
                    Author:{" "}
                    <strong className="text-slate-700">
                      {inspectNote.author?.full_name || "Super Admin"}
                    </strong>
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5 text-slate-400" />
                    Published:{" "}
                    <strong className="text-slate-700">
                      {formatDate(inspectNote.published_at || inspectNote.created_at)}
                    </strong>
                  </span>
                </div>
              </div>

              {/* PDF Document Attachment Card */}
              <div className="p-3 bg-white rounded-lg border border-slate-200 space-y-2">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Attached PDF Document
                </span>
                {inspectNote.pdf_url ? (
                  <div className="flex items-center justify-between gap-2 bg-slate-50 p-2.5 rounded border border-slate-200">
                    <div className="flex items-center gap-2 overflow-hidden">
                      <FileDown className="h-5 w-5 text-primary-teal shrink-0" />
                      <div className="overflow-hidden">
                        <p className="text-xs font-mono text-slate-700 truncate">
                          {inspectNote.pdf_url}
                        </p>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Size: {formatFileSize(inspectNote.file_size_bytes)}
                        </p>
                      </div>
                    </div>
                    <a
                      href={inspectNote.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2 py-1 bg-white border border-slate-200 rounded text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-1 shrink-0"
                    >
                      <ExternalLink className="h-3 w-3" /> View
                    </a>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No PDF document attached.</p>
                )}
              </div>

              {inspectNote.description && (
                <div>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Description
                  </span>
                  <p className="text-xs text-slate-600 mt-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    {inspectNote.description}
                  </p>
                </div>
              )}
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setInspectNote(null)}
            >
              Close
            </Button>
            {inspectNote && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  const n = inspectNote;
                  setInspectNote(null);
                  openEditEditor(n);
                }}
                className="bg-primary-teal hover:bg-primary-teal/90 text-white"
              >
                Edit Note
              </Button>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Create / Edit Note Modal */}
      <Modal open={isEditorOpen} onOpenChange={(open) => !open && closeEditor()}>
        <ModalContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              {editingNoteId ? (
                <>
                  <Edit3 className="h-5 w-5 text-primary-teal" /> Edit Study Note
                </>
              ) : (
                <>
                  <Plus className="h-5 w-5 text-primary-teal" /> Upload Study Note
                </>
              )}
            </ModalTitle>
            <ModalDescription>
              {editingNoteId
                ? "Update study note attributes, category, and publication status."
                : "Create a new study note or revision guide."}
            </ModalDescription>
          </ModalHeader>

          <div className="space-y-4 py-2 text-sm">
            {/* Title */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Note Title <span className="text-rose-500">*</span>
              </label>
              <Input
                type="text"
                placeholder="e.g. Next.js 15 App Router Architecture Cheat Sheet"
                value={formTitle}
                onChange={(e) => {
                  setFormTitle(e.target.value);
                  if (!editingNoteId) {
                    setFormSlug(slugify(e.target.value));
                  }
                }}
                className="bg-white border-slate-300 text-sm"
              />
            </div>

            {/* Slug & Category */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  URL Slug
                </label>
                <Input
                  type="text"
                  placeholder="nextjs-15-cheat-sheet"
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
                  placeholder="e.g. Cheat Sheets, Lecture Slides"
                  value={formCategory}
                  onChange={(e) => setFormCategory(e.target.value)}
                  className="bg-white border-slate-300 text-sm"
                />
              </div>
            </div>

            {/* PDF URL & File Size */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  PDF Document URL / Storage Key
                </label>
                <Input
                  type="text"
                  placeholder="https://.../notes.pdf"
                  value={formPdfUrl}
                  onChange={(e) => setFormPdfUrl(e.target.value)}
                  className="bg-white border-slate-300 font-mono text-xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  File Size (Bytes, optional)
                </label>
                <Input
                  type="number"
                  placeholder="e.g. 1048576 (1 MB)"
                  value={formFileSize !== undefined ? String(formFileSize) : ""}
                  onChange={(e) =>
                    setFormFileSize(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="bg-white border-slate-300 font-mono text-xs"
                />
              </div>
            </div>

            {/* Status */}
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
                <option value="PUBLISHED">PUBLISHED (Available for Students)</option>
                <option value="ARCHIVED">ARCHIVED</option>
              </select>
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Description (Optional)
              </label>
              <textarea
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={4}
                placeholder="Overview of the topics and key formulas covered in this document..."
                className="w-full text-sm bg-white border border-slate-300 rounded-lg p-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary-teal"
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
              disabled={saveNoteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => saveNoteMutation.mutate()}
              disabled={saveNoteMutation.isPending}
              className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-1.5"
            >
              {saveNoteMutation.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              {editingNoteId ? "Save Changes" : "Create Note"}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Replace PDF Modal */}
      <Modal open={!!noteToReplacePdf} onOpenChange={(open) => !open && setNoteToReplacePdf(null)}>
        <ModalContent className="max-w-md">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg">
              <FileUp className="h-5 w-5 text-primary-teal" />
              Replace Attached PDF
            </ModalTitle>
            <ModalDescription>
              Update the binary storage path and size for this study note document.
            </ModalDescription>
          </ModalHeader>

          {noteToReplacePdf && (
            <div className="space-y-4 py-2 text-sm">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 font-medium">Target Note:</span>
                <p className="font-semibold text-slate-900 mt-0.5">{noteToReplacePdf.title}</p>
                <p className="text-xs font-mono text-slate-500 mt-1">
                  Current PDF: {noteToReplacePdf.pdf_url || "None"}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  New PDF Document URL <span className="text-rose-500">*</span>
                </label>
                <Input
                  type="text"
                  placeholder="https://.../updated-notes.pdf"
                  value={replacePdfUrl}
                  onChange={(e) => setReplacePdfUrl(e.target.value)}
                  className="bg-white border-slate-300 font-mono text-xs"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  New File Size (Bytes, optional)
                </label>
                <Input
                  type="number"
                  placeholder="e.g. 2097152 (2 MB)"
                  value={replaceFileSize !== undefined ? String(replaceFileSize) : ""}
                  onChange={(e) =>
                    setReplaceFileSize(e.target.value ? Number(e.target.value) : undefined)
                  }
                  className="bg-white border-slate-300 font-mono text-xs"
                />
              </div>

              {replacePdfError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {replacePdfError}
                </div>
              )}
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setNoteToReplacePdf(null);
                setReplacePdfError(null);
              }}
              disabled={replacePdfMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => replacePdfMutation.mutate()}
              disabled={replacePdfMutation.isPending}
              className="bg-primary-teal hover:bg-primary-teal/90 text-white flex items-center gap-1.5"
            >
              {replacePdfMutation.isPending && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              )}
              Replace PDF
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal open={!!noteToDelete} onOpenChange={(open) => !open && setNoteToDelete(null)}>
        <ModalContent className="max-w-md">
          <ModalHeader>
            <ModalTitle className="flex items-center gap-2 text-lg text-rose-600">
              <Trash2 className="h-5 w-5 text-rose-600" />
              Delete Study Note
            </ModalTitle>
            <ModalDescription>
              Are you sure you want to permanently delete this study note? This action is audited and cannot be undone.
            </ModalDescription>
          </ModalHeader>

          {noteToDelete && (
            <div className="py-2 text-sm">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 font-medium">Note Title:</span>
                <p className="font-semibold text-slate-900 mt-0.5">{noteToDelete.title}</p>
                <p className="text-xs font-mono text-slate-500 mt-1">
                  /notes/{noteToDelete.slug}
                </p>
              </div>
            </div>
          )}

          <ModalFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setNoteToDelete(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => noteToDelete && deleteMutation.mutate(noteToDelete.id)}
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
