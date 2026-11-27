"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Film,
  FileText,
  UploadCloud,
  Trash2,
  AlertCircle,
  Loader2,
  CheckCircle2,
  ArrowLeft,
  RefreshCw,
} from "lucide-react";
import { mediaApi } from "@/lib/api/media";
import { getApiBaseUrl } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { SUPPORTED_VIDEO_MIME_TYPES } from "@/types/media";

export default function AdminMediaPage() {
  const queryClient = useQueryClient();
  const [mimeFilter, setMimeFilter] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const {
    data: mediaData,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["admin-media-library", mimeFilter],
    queryFn: () =>
      mediaApi.listMediaAssets({
        per_page: 50,
        mime_type: mimeFilter || undefined,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      const hasPending = items.some(
        (asset) => asset.status === "UPLOADING" || asset.status === "PROCESSING"
      );
      return hasPending ? 3000 : false;
    },
  });

  const displayedItems = (mediaData?.items || []).filter((asset) => {
    if (!mimeFilter) return true;
    if (mimeFilter === "video") {
      return (
        SUPPORTED_VIDEO_MIME_TYPES.includes(asset.mime_type as any) ||
        asset.mime_type?.startsWith("video/")
      );
    }
    return asset.mime_type === mimeFilter;
  });

  const deleteMutation = useMutation({
    mutationFn: (mediaId: string) => mediaApi.deleteMediaAsset(mediaId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-media-library"] });
      setErrorMessage(null);
      setSuccessMessage("Media asset successfully deleted.");
      setTimeout(() => setSuccessMessage(null), 3000);
    },
    onError: (err: any) => {
      if (
        err?.code === "MEDIA_ASSET_IN_USE" ||
        err?.message?.includes("in use") ||
        err?.message?.includes("attached")
      ) {
        setErrorMessage(
          "Reference protection active: Cannot delete media asset because it is bound to curriculum lessons or resources."
        );
      } else {
        setErrorMessage(err?.message || "Failed to delete media asset.");
      }
    },
  });

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    setIsUploading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      // 1. Get presigned upload intent
      const intent = await mediaApi.getUploadIntent({
        filename: uploadFile.name,
        mime_type: uploadFile.type || "application/octet-stream",
        file_size_bytes: uploadFile.size,
      });

      // 2. Direct binary PUT (resolving local dev backend URL if needed)
      let uploadUrl = intent.presigned_url;
      if (uploadUrl.startsWith("/")) {
        uploadUrl = `${getApiBaseUrl()}${uploadUrl}`;
      } else if (uploadUrl.includes("localhost:8000") && typeof window !== "undefined") {
        const apiBase = getApiBaseUrl();
        if (!apiBase.includes("localhost:8000")) {
          uploadUrl = uploadUrl.replace("http://localhost:8000", apiBase);
        }
      }

      const putRes = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          ...(intent.headers || {}),
          "Content-Type": uploadFile.type || "application/octet-stream",
        },
        body: uploadFile,
      });

      if (!putRes.ok) {
        throw new Error(`Upload to storage bucket failed with status ${putRes.status}`);
      }

      // 3. Confirm upload with backend
      await mediaApi.confirmUpload(intent.media_id, {
        file_key: intent.file_key,
      });

      queryClient.invalidateQueries({ queryKey: ["admin-media-library"] });
      setUploadFile(null);
      setSuccessMessage(`Asset "${uploadFile.name}" successfully registered and uploaded.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to upload asset.");
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
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/admin"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Admin Dashboard
        </Link>
      </div>

      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Media & Storage Management
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Manage encrypted video assets, curriculum PDFs, and safe asset deletion with reference protection.
        </p>
      </div>

      {/* Alerts */}
      {errorMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-4 text-sm text-rose-700 border border-rose-200">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-600" />
          <span>{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-teal-600" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Direct Uploader Card */}
      <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm space-y-4">
        <div>
          <h2 className="font-heading text-base font-bold text-slate-900">
            Direct S3/R2 Storage Uploader
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Upload videos, protected PDFs, or course images directly to cloud storage.
          </p>
        </div>

        <form onSubmit={handleUpload} className="space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full">
            <input
              type="file"
              id="admin-media-upload-input"
              aria-label="Choose file to upload"
              accept="video/mp4,video/webm,video/quicktime,application/pdf,image/*"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              className="block w-full text-xs sm:text-sm text-slate-600 file:mr-3 sm:file:mr-4 file:py-2 file:px-3.5 sm:file:px-4 file:rounded-[8px] file:border-0 file:text-xs sm:file:text-sm file:font-semibold file:bg-primary-teal/10 file:text-primary-teal hover:file:bg-primary-teal/20 cursor-pointer min-h-[44px]"
            />
            <Button
              type="submit"
              variant="primary"
              size="default"
              disabled={!uploadFile || isUploading}
              isLoading={isUploading}
              className="w-full sm:w-auto shrink-0 whitespace-nowrap min-h-[44px] justify-center"
            >
              <UploadCloud className="h-4 w-4 mr-2 shrink-0" />
              Upload to Private Storage
            </Button>
          </div>

          {uploadFile && (
            <div className="flex items-center gap-2 text-xs text-slate-600 pt-1">
              <span className="font-semibold text-slate-700">Selected file:</span>
              <span className="truncate max-w-xs font-mono text-slate-800">{uploadFile.name}</span>
              <span className="text-slate-400">({formatBytes(uploadFile.size)})</span>
            </div>
          )}
        </form>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setMimeFilter("")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            mimeFilter === ""
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          All Assets ({mediaData?.items?.length || 0})
        </button>
        <button
          onClick={() => setMimeFilter("video")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            mimeFilter === "video"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Videos
        </button>
        <button
          onClick={() => setMimeFilter("application/pdf")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            mimeFilter === "application/pdf"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Protected PDFs (.pdf)
        </button>
      </div>

      {/* Asset Grid */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm p-6">
        {isError ? (
          <div className="p-8 text-center space-y-4">
            <div className="p-3 rounded-full bg-rose-100 text-rose-600 w-fit mx-auto">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-800">
                Failed to load media assets
              </p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                {error instanceof Error ? error.message : "Unable to reach media storage API."}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="text-xs"
            >
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
              Retry Connection
            </Button>
          </div>
        ) : isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !displayedItems.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <Film className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No media assets in library</p>
            <p className="text-xs text-slate-500">Upload your videos or documents using the form above.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {displayedItems.map((asset) => {
              const isVideo = asset.mime_type?.startsWith("video/");
              const isPdf = asset.mime_type === "application/pdf";

              return (
                <div
                  key={asset.id}
                  className="flex flex-col justify-between rounded-[12px] border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 transition-all"
                >
                  <div className="flex items-start gap-3">
                    <div className="p-2.5 rounded-lg bg-slate-50 text-slate-700 shrink-0">
                      {isVideo ? (
                        <Film className="h-5 w-5 text-teal-600" />
                      ) : isPdf ? (
                        <FileText className="h-5 w-5 text-coral-orange" />
                      ) : (
                        <FileText className="h-5 w-5 text-slate-600" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-slate-900 truncate" title={asset.filename}>
                        {asset.filename}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {formatBytes(asset.file_size_bytes)} · {asset.mime_type}
                      </p>
                      <p className="text-[11px] font-mono text-slate-400 mt-1 truncate" title={asset.file_key}>
                        {asset.file_key}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 flex items-center justify-between pt-3 border-t border-slate-100">
                    {asset.status === "READY" ? (
                      <Badge variant="success">Ready</Badge>
                    ) : asset.status === "PROCESSING" ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                        <Loader2 className="h-3 w-3 animate-spin text-amber-600" />
                        Processing...
                      </span>
                    ) : asset.status === "FAILED" ? (
                      <Badge variant="error">Failed</Badge>
                    ) : (
                      <Badge variant="outline">{asset.status}</Badge>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete media asset "${asset.filename}"? Reference checks will reject deletion if bound to a course.`
                          )
                        ) {
                          deleteMutation.mutate(asset.id);
                        }
                      }}
                      className="text-slate-400 hover:text-rose-600 p-1.5 rounded transition-colors"
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
  );
}
