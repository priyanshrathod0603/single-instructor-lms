"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Film,
  FileText,
  UploadCloud,
  Trash2,
  Check,
  AlertCircle,
  Loader2,
  X,
  RefreshCw,
} from "lucide-react";
import { mediaApi } from "@/lib/api/media";
import { getApiBaseUrl } from "@/lib/api/client";
import { MediaAssetResponse } from "@/types/media";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

interface MediaLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect?: (asset: MediaAssetResponse) => void;
  allowedMimeType?: string; // e.g. "video/mp4" or "application/pdf"
  title?: string;
}

export const MediaLibraryModal: React.FC<MediaLibraryModalProps> = ({
  isOpen,
  onClose,
  onSelect,
  allowedMimeType,
  title = "Media Library",
}) => {
  const queryClient = useQueryClient();
  const [selectedAsset, setSelectedAsset] = useState<MediaAssetResponse | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const {
    data: mediaData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["media-assets", allowedMimeType],
    queryFn: () => mediaApi.listMediaAssets({ per_page: 50, mime_type: allowedMimeType }),
    enabled: isOpen,
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      const hasPending = items.some(
        (asset) => asset.status === "UPLOADING" || asset.status === "PROCESSING"
      );
      return hasPending ? 3000 : false;
    },
  });

  const displayedItems = (mediaData?.items || []).filter((asset) => {
    if (!allowedMimeType) return true;
    const allowedList = allowedMimeType.split(",").map((s) => s.trim().toLowerCase());
    return allowedList.some((allowed) => {
      if (allowed === "video" || allowed === "video/*") {
        return asset.mime_type?.toLowerCase().startsWith("video/");
      }
      if (allowed.endsWith("/*")) {
        return asset.mime_type?.toLowerCase().startsWith(allowed.slice(0, -1));
      }
      return asset.mime_type?.toLowerCase() === allowed;
    });
  });

  const deleteMutation = useMutation({
    mutationFn: (mediaId: string) => mediaApi.deleteMediaAsset(mediaId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["media-assets"] });
      setSelectedAsset(null);
      setErrorMessage(null);
    },
    onError: (err: any) => {
      if (err?.code === "MEDIA_ASSET_IN_USE" || err?.message?.includes("in use") || err?.message?.includes("attached")) {
        setErrorMessage("Cannot delete media asset: it is currently attached to a course lesson or resource.");
      } else {
        setErrorMessage(err?.message || "Failed to delete media asset.");
      }
    },
  });

  if (!isOpen) return null;

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    setIsUploading(true);
    setErrorMessage(null);

    try {
      // 1. Get presigned upload intent
      const intent = await mediaApi.getUploadIntent({
        filename: uploadFile.name,
        mime_type: uploadFile.type || "application/octet-stream",
        file_size_bytes: uploadFile.size,
      });

      // 2. Direct binary PUT to storage presigned URL (resolving local dev backend URL if needed)
      let uploadUrl = intent.presigned_url;
      if (uploadUrl.startsWith("/")) {
        uploadUrl = `${getApiBaseUrl()}${uploadUrl}`;
      } else if (uploadUrl.includes("localhost:8000") && typeof window !== "undefined") {
        const apiBase = getApiBaseUrl();
        if (!apiBase.includes("localhost:8000")) {
          uploadUrl = uploadUrl.replace("http://localhost:8000", apiBase);
        }
      }

      const uploadHeaders: Record<string, string> = {
        ...(intent.headers || {}),
        "Content-Type": uploadFile.type || "application/octet-stream",
      };

      const putRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: uploadHeaders,
        body: uploadFile,
      });

      if (!putRes.ok) {
        throw new Error(`Storage upload failed with HTTP status ${putRes.status}`);
      }

      // 3. Confirm upload with backend
      const confirmedAsset = await mediaApi.confirmUpload(intent.media_id, {
        file_key: intent.file_key,
      });

      queryClient.invalidateQueries({ queryKey: ["media-assets"] });
      setUploadFile(null);
      setSelectedAsset(confirmedAsset);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to complete asset upload.");
    } finally {
      setIsUploading(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="media-library-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 sm:p-6"
    >
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-[16px] bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50">
          <div className="flex items-center gap-2">
            <Film className="h-5 w-5 text-primary-teal" />
            <h2 id="media-library-title" className="font-heading text-lg font-bold text-slate-900">
              {title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 border border-rose-200">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Content Tabs / Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Upload Form Box */}
          <div className="rounded-[12px] border-2 border-dashed border-slate-200 bg-slate-50/50 p-4 sm:p-6">
            <form onSubmit={handleUpload} className="flex flex-col sm:flex-row items-center gap-4">
              <input
                type="file"
                id="media-file-input"
                aria-label="Select file to upload"
                accept={allowedMimeType || "video/*,application/pdf"}
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="text-sm text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-[8px] file:border-0 file:text-sm file:font-semibold file:bg-primary-teal/10 file:text-primary-teal hover:file:bg-primary-teal/20"
              />
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={!uploadFile || isUploading}
                isLoading={isUploading}
              >
                <UploadCloud className="h-4 w-4 mr-2" />
                Upload Asset
              </Button>
            </form>
          </div>

          {/* Asset Grid */}
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">
              Existing Media Assets ({displayedItems.length})
            </h3>
            {isError ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50/60 p-6 text-center space-y-3">
                <div className="p-2 rounded-full bg-rose-100 text-rose-600 w-fit mx-auto">
                  <AlertCircle className="h-5 w-5" />
                </div>
                <p className="text-xs font-semibold text-rose-800">
                  {error instanceof Error ? error.message : "Failed to load media assets."}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => refetch()}
                  className="text-xs text-rose-700 border-rose-300 hover:bg-rose-100"
                >
                  <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                  Retry Connection
                </Button>
              </div>
            ) : isLoading ? (
              <div className="flex h-48 items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
              </div>
            ) : displayedItems.length === 0 ? (
              <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-500">
                No media assets found. Upload your first video or document above.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {displayedItems.map((asset) => {
                  const isSelected = selectedAsset?.id === asset.id;
                  const isVideo = asset.mime_type?.startsWith("video/");
                  const isPdf = asset.mime_type === "application/pdf";

                  return (
                    <div
                      key={asset.id}
                      onClick={() => setSelectedAsset(asset)}
                      className={`relative flex flex-col justify-between rounded-[12px] border p-4 cursor-pointer transition-all ${
                        isSelected
                          ? "border-primary-teal bg-teal-50/40 ring-2 ring-primary-teal/30"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="p-2.5 rounded-lg bg-slate-100 text-slate-700 shrink-0">
                          {isVideo ? (
                            <Film className="h-5 w-5 text-teal-600" />
                          ) : isPdf ? (
                            <FileText className="h-5 w-5 text-coral-orange" />
                          ) : (
                            <FileText className="h-5 w-5 text-slate-600" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-slate-900 truncate" title={asset.filename}>
                            {asset.filename}
                          </p>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {formatBytes(asset.file_size_bytes)}
                          </p>
                        </div>
                      </div>

                      <div className="mt-4 flex items-center justify-between pt-3 border-t border-slate-100">
                        {asset.status === "READY" ? (
                          <Badge variant="success">Ready</Badge>
                        ) : asset.status === "PROCESSING" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            <Loader2 className="h-2.5 w-2.5 animate-spin text-amber-600" />
                            Processing...
                          </span>
                        ) : asset.status === "FAILED" ? (
                          <Badge variant="error">Failed</Badge>
                        ) : (
                          <Badge variant="outline">{asset.status}</Badge>
                        )}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`Delete ${asset.filename}?`)) {
                              deleteMutation.mutate(asset.id);
                            }
                          }}
                          className="text-slate-400 hover:text-rose-600 p-1 rounded transition-colors min-h-[32px] min-w-[32px] flex items-center justify-center"
                          title="Delete asset"
                          aria-label={`Delete ${asset.filename}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 bg-slate-50">
          <div className="text-xs text-slate-500 flex flex-col">
            <span>{selectedAsset ? `Selected: ${selectedAsset.filename}` : "No asset selected"}</span>
            {selectedAsset?.status === "PROCESSING" && (
              <span className="text-[11px] text-amber-600 font-medium">
                Note: Video is still transcoding. You can attach it now; publishing will unlock once ready.
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            {onSelect && (
              <Button
                variant="primary"
                size="sm"
                disabled={!selectedAsset}
                onClick={() => {
                  if (selectedAsset) {
                    onSelect(selectedAsset);
                    onClose();
                  }
                }}
              >
                <Check className="h-4 w-4 mr-2" />
                Attach Selected Asset
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
