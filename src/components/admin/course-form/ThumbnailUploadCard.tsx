"use client";

import React, { useRef, useState } from "react";
import { Image as ImageIcon, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { resolveApiAssetUrl } from "@/lib/api/client";
import { parseApiError } from "@/lib/api/errors";
import { mediaApi } from "@/lib/api/media";
import { MAX_IMAGE_UPLOAD_BYTES, SUPPORTED_IMAGE_MIME_TYPES } from "@/types/media";

export interface ThumbnailUploadCardProps {
  thumbnailUrl: string;
  thumbnailMediaId: string | null;
  courseTitle: string;
  error?: string;
  onChange: (next: { thumbnailUrl: string; thumbnailMediaId: string | null }) => void;
}

const ACCEPTED_EXTENSIONS = ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";

export const ThumbnailUploadCard: React.FC<ThumbnailUploadCardProps> = ({
  thumbnailUrl,
  thumbnailMediaId,
  courseTitle,
  error,
  onChange,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [previewLoadFailed, setPreviewLoadFailed] = useState(false);

  const handleFileSelected = async (file: File | undefined | null) => {
    if (!file) return;
    setUploadError(null);
    setPreviewLoadFailed(false);

    const mime = (file.type || "").toLowerCase();
    if (!SUPPORTED_IMAGE_MIME_TYPES.includes(mime as (typeof SUPPORTED_IMAGE_MIME_TYPES)[number])) {
      setUploadError("Unsupported image format. Please choose a JPEG, PNG, or WebP file.");
      return;
    }

    if (file.size <= 0 || file.size > MAX_IMAGE_UPLOAD_BYTES) {
      setUploadError("Image size must be between 1 byte and 5 MB.");
      return;
    }

    setIsUploading(true);
    setUploadProgress(5);
    try {
      const asset = await mediaApi.uploadCourseThumbnail(file, (pct) => {
        setUploadProgress(pct);
      });
      const resolvedPath = asset.public_url || `/api/v1/media/public/${asset.id}`;
      onChange({
        thumbnailUrl: resolvedPath,
        thumbnailMediaId: asset.id,
      });
    } catch (err) {
      const parsed = parseApiError(err);
      setUploadError(parsed.message || "Thumbnail upload failed. Please try again.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const resolvedPreviewSrc = resolveApiAssetUrl(thumbnailUrl);
  const combinedError = uploadError || error;

  return (
    <div className="space-y-4">
      <input
        ref={fileInputRef}
        id="course-thumbnail-file-input"
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        className="sr-only"
        aria-label="Upload course thumbnail image"
        onChange={(e) => handleFileSelected(e.target.files?.[0])}
      />

      <div className="grid grid-cols-1 gap-5 md:grid-cols-12 md:items-start">
        {/* Live 16:9 Preview Area */}
        <div className="md:col-span-5">
          <div className="relative aspect-video w-full overflow-hidden rounded-2xl border border-slate-200 bg-brand-cream/60 flex items-center justify-center">
            {resolvedPreviewSrc && !previewLoadFailed ? (
              <img
                src={resolvedPreviewSrc}
                alt={courseTitle ? `${courseTitle} thumbnail preview` : "Course thumbnail preview"}
                className="h-full w-full object-cover"
                onError={() => setPreviewLoadFailed(true)}
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 p-6 text-center text-slate-400">
                <ImageIcon className="h-10 w-10 text-brand-teal/50" />
                <span className="text-xs font-medium text-slate-500">
                  {previewLoadFailed
                    ? "Preview image could not be loaded"
                    : "No cover thumbnail selected"}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Upload Dropzone & Controls */}
        <div className="space-y-3 md:col-span-7">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              handleFileSelected(e.dataTransfer.files?.[0]);
            }}
            className={`rounded-2xl border-2 border-dashed p-5 transition-colors ${
              isDragging
                ? "border-brand-teal bg-brand-mint/30"
                : "border-slate-200 bg-slate-50/70"
            }`}
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 rounded-xl bg-brand-mint p-2.5 text-brand-teal">
                  <UploadCloud className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">
                    {thumbnailUrl ? "Replace course thumbnail" : "Upload course thumbnail"}
                  </p>
                  <p className="text-xs text-slate-500">
                    JPEG, PNG, or WebP up to 5 MB. Recommended 1280×720 (16:9).
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant={thumbnailUrl ? "outline" : "secondary"}
                  size="sm"
                  disabled={isUploading}
                  onClick={() => fileInputRef.current?.click()}
                  className="min-h-[44px]"
                >
                  {thumbnailUrl ? (
                    <>
                      <RefreshCw className="mr-1.5 h-4 w-4" />
                      Replace Image
                    </>
                  ) : (
                    <>
                      <UploadCloud className="mr-1.5 h-4 w-4" />
                      Choose Image
                    </>
                  )}
                </Button>

                {thumbnailUrl && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isUploading}
                    onClick={() => {
                      setUploadError(null);
                      setPreviewLoadFailed(false);
                      onChange({ thumbnailUrl: "", thumbnailMediaId: null });
                    }}
                    className="min-h-[44px] text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  >
                    <Trash2 className="mr-1.5 h-4 w-4" />
                    Remove
                  </Button>
                )}
              </div>
            </div>

            {isUploading && (
              <div className="mt-4 space-y-1.5">
                <div className="flex items-center justify-between text-xs font-medium text-brand-teal">
                  <span>Uploading and verifying image…</span>
                  <span>{uploadProgress}%</span>
                </div>
                <progress
                  value={uploadProgress}
                  max={100}
                  aria-label="Course thumbnail upload progress"
                  className="h-2 w-full overflow-hidden rounded-full [&::-webkit-progress-bar]:bg-slate-200 [&::-webkit-progress-value]:bg-brand-teal [&::-moz-progress-bar]:bg-brand-teal"
                />
              </div>
            )}
          </div>

          <Input
            id="course-thumbnail-url"
            label="Or paste external image URL (optional)"
            placeholder="https://cdn.example.com/courses/cover.webp"
            value={thumbnailUrl}
            onChange={(e) => {
              setUploadError(null);
              setPreviewLoadFailed(false);
              const val = e.target.value;
              onChange({
                thumbnailUrl: val,
                thumbnailMediaId: val.startsWith("/api/v1/media/public/") ? thumbnailMediaId : null,
              });
            }}
            helperText={
              thumbnailMediaId
                ? "Linked to your verified uploaded media asset."
                : "Upload a file above or specify a direct HTTPS image URL."
            }
            error={combinedError}
          />
        </div>
      </div>
    </div>
  );
};
